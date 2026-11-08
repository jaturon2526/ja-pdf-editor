"""อัปโหลดไฟล์ Office จาก Dashboard และเมนูสร้างจาก Office: แปลงเป็น PDF แล้วเก็บเป็น PDF ในเอกสารของฉัน
+ ลิงก์ดาวน์โหลดไฟล์ตัวอย่างเอกสารอัตโนมัติในหน้าคู่มือ"""
import io
import shutil

import docx
import fitz
import pytest

from app.api.pdf import files as files_api


def _docx(text: str = "Hello Office") -> bytes:
    d = docx.Document()
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.fixture
def fake_convert(monkeypatch):
    calls = []

    async def _convert(data, name, user_id=None):
        calls.append(name)
        pdf = fitz.open()
        pdf.new_page().insert_text((72, 72), "converted " + name)
        return pdf.tobytes()

    monkeypatch.setattr(files_api, "convert_office_to_pdf_bytes", _convert)
    return calls


def _my_files(client, headers):
    return client.get("/pdf/files", headers=headers).json()["files"]


@pytest.mark.parametrize("endpoint", ["/pdf/upload", "/pdf/convert-office"])
def test_office_file_is_converted_and_stored_as_pdf(client, make_user, fake_convert, endpoint):
    from app.core.session import session_manager

    _, headers = make_user()
    r = client.post(endpoint, headers=headers, files={"file": ("รายงาน ประจำเดือน.docx", _docx(), "application/octet-stream")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["filename"] == "รายงาน ประจำเดือน.pdf" and body["page_count"] == 1
    assert fake_convert == ["รายงาน ประจำเดือน.docx"]
    stored = [f for f in _my_files(client, headers) if f["filename"] == "รายงาน ประจำเดือน.pdf"]
    assert len(stored) == 1                                    # เก็บไว้ในเอกสารของฉันเป็น PDF
    session = session_manager.get(body["session_id"])
    assert "converted" in session.doc[0].get_text()
    assert session.history                                     # มี baseline ของ undo แล้ว


def test_upload_rejects_unsupported_types(client, make_user, fake_convert):
    _, headers = make_user()
    r = client.post("/pdf/upload", headers=headers, files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and "Office" in r.json()["detail"]
    r = client.post("/pdf/convert-office", headers=headers, files={"file": ("x.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 400
    assert fake_convert == []


def test_failed_conversion_does_not_store_a_file(client, make_user, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("LibreOffice ล่ม")

    monkeypatch.setattr(files_api, "convert_office_to_pdf_bytes", _boom)
    _, headers = make_user()
    before = len(_my_files(client, headers))
    r = client.post("/pdf/upload", headers=headers, files={"file": ("a.xlsx", b"PK..", "application/octet-stream")})
    assert r.status_code == 400 and "แปลงไฟล์ Office" in r.json()["detail"]
    assert len(_my_files(client, headers)) == before


@pytest.mark.skipif(not shutil.which("libreoffice"), reason="ไม่มี LibreOffice")
def test_real_libreoffice_conversion_keeps_thai_text(client, make_user):
    from app.core.session import session_manager

    _, headers = make_user()
    r = client.post("/pdf/upload", headers=headers, files={"file": ("thai.docx", _docx("หนังสือรับรองการทำงาน"), "x")})
    assert r.status_code == 200, r.text
    text = session_manager.get(r.json()["session_id"]).doc[0].get_text()
    assert "หนังสือรับรอง" in text.replace(" ", "")


@pytest.mark.parametrize("name", ["template.docx", "data.json", "template_flat.docx", "data_flat.xlsx", "data_flat.csv"])
def test_autogen_sample_downloads_without_login(client, name):
    r = client.get(f"/autogen/samples/{name}")
    assert r.status_code == 200 and len(r.content) > 50
    assert "attachment" in r.headers["content-disposition"] and name in r.headers["content-disposition"]


@pytest.mark.parametrize("name", ["../app/main.py", "secret.env", "template.doc"])
def test_autogen_sample_only_serves_listed_files(client, name):
    assert client.get(f"/autogen/samples/{name}").status_code == 404


def test_docker_image_includes_the_sample_files():
    # image ของ backend COPY เฉพาะโฟลเดอร์ที่ระบุ — ไม่มีบรรทัดนี้ ลิงก์ในคู่มือได้ 404 บนเซิร์ฟเวอร์ (เทสต์ในเครื่องผ่านเพราะเห็นไฟล์จาก repo)
    from pathlib import Path

    from app.api import routes_autogen

    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert "COPY sample_autogen ./sample_autogen" in dockerfile
    assert routes_autogen.SAMPLES_DIR == Path(__file__).resolve().parents[1] / "sample_autogen"
