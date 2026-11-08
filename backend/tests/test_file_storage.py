"""ไฟล์ใน Dashboard: แปลง PDF→Word หาไฟล์เจอ, Save แล้วเปิดใหม่ต้องได้ฉบับที่บันทึก, ชื่อไทยยาวบันทึกได้"""
from tests.conftest import make_pdf_bytes
from pathlib import Path


def _file_id(client, headers, sid):
    files = client.get("/pdf/files", headers=headers).json()["files"]
    return next(f["id"] for f in files if f["session_id"] == sid)


def test_pdf_to_word_finds_uploaded_file(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers)
    r = client.post("/convert/pdf-to-word/async", headers=headers, json={"file_record_id": _file_id(client, headers, sid)})
    assert r.status_code == 200, r.text
    status = client.get(f"/convert/pdf-to-word/status/{r.json()['task_id']}", headers=headers).json()
    assert status["status"] == "completed", status
    dl = client.get(f"/convert/pdf-to-word/download/{r.json()['task_id']}", headers=headers)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"  # ไฟล์ .docx คือ zip


def test_pdf_to_word_from_editor_session_uses_saved_edits(client, make_user, upload):
    """Editor (เมนู เครื่องมือ > แปลงเป็น Word): ส่ง session_id — แปลงฉบับที่บันทึกล่าสุด และคนอื่นใช้ session ของเราไม่ได้"""
    import io

    from docx import Document

    _, headers = make_user()
    sid = upload(headers, make_pdf_bytes(text="Before edit"))
    assert client.post(f"/pdf/{sid}/save", headers=headers).status_code == 200
    r = client.post("/convert/pdf-to-word/async", headers=headers, json={"session_id": sid, "mode": "layout"})
    assert r.status_code == 200, r.text
    task_id = r.json()["task_id"]
    assert client.get(f"/convert/pdf-to-word/status/{task_id}", headers=headers).json()["status"] == "completed"
    doc = Document(io.BytesIO(client.get(f"/convert/pdf-to-word/download/{task_id}", headers=headers).content))
    assert any("Before edit" in p.text for p in doc.paragraphs)

    _, other = make_user()
    assert client.post("/convert/pdf-to-word/async", headers=other, json={"session_id": sid}).status_code == 404
    assert client.post("/convert/pdf-to-word/async", headers=headers, json={"mode": "layout"}).status_code == 422


def test_saved_edits_survive_reopen(client, make_user, upload):
    from app.core.session import session_manager

    _, headers = make_user()
    sid = upload(headers)
    file_id = _file_id(client, headers, sid)
    client.post(f"/pdf/{sid}/pages/rotate", headers=headers, json={"page_numbers": [0], "angle": 90})
    assert client.post(f"/pdf/{sid}/save", headers=headers).status_code == 200
    session_manager.close(sid)  # จำลอง session หมดอายุ/เซิร์ฟเวอร์รีสตาร์ท

    new_sid = client.post(f"/pdf/{sid}/open", headers=headers).json()["session_id"]
    s = session_manager.get(new_sid)
    with s.lock:
        assert s.doc[0].rect.width > s.doc[0].rect.height   # หมุนแล้ว (เข้าเนื้อหน้า — /Rotate 0)
    assert _file_id(client, headers, new_sid) == file_id


def test_long_thai_filename_can_be_saved_and_renamed(client, make_user):
    _, headers = make_user()
    name = "เอกสารประกอบการประชุมคณะกรรมการบริหารประจำปีงบประมาณสองพันห้าร้อยหกสิบเก้า" * 2 + ".pdf"
    r = client.post("/pdf/upload", headers=headers, files={"file": (name, make_pdf_bytes(), "application/pdf")})
    sid = r.json()["session_id"]
    assert client.post(f"/pdf/{sid}/save", headers=headers).status_code == 200
    file_id = _file_id(client, headers, sid)
    assert client.put(f"/pdf/files/{file_id}/rename", headers=headers, json={"filename": "ชื่อใหม่"}).status_code == 200
    r = client.post("/convert/pdf-to-word/async", headers=headers, json={"file_record_id": file_id})
    assert client.get(f"/convert/pdf-to-word/status/{r.json()['task_id']}", headers=headers).json()["status"] == "completed"
    assert client.delete(f"/pdf/files/{file_id}", headers=headers).status_code == 200


def test_pdf_to_word_layout_mode(client, make_user, upload):
    """โหมดรักษาหน้าตา: ได้ .docx หน้าเท่าต้นฉบับ มีภาพพื้นหลังและข้อความแก้ไขได้ ไม่ใช้โควต้า AI"""
    import io
    import zipfile

    from docx import Document

    _, headers = make_user()
    sid = upload(headers, make_pdf_bytes(pages=2, text="Layout mode"))
    r = client.post("/convert/pdf-to-word/async", headers=headers,
                    json={"file_record_id": _file_id(client, headers, sid), "mode": "layout"})
    task_id = r.json()["task_id"]
    assert client.get(f"/convert/pdf-to-word/status/{task_id}", headers=headers).json()["status"] == "completed"
    data = client.get(f"/convert/pdf-to-word/download/{task_id}", headers=headers).content
    doc = Document(io.BytesIO(data))
    assert len(doc.sections) == 2
    assert any("Layout mode page 1" in p.text for p in doc.paragraphs)
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode()
    assert xml.count("<wp:anchor") == 2 and 'behindDoc="1"' in xml and "<w:framePr" in xml
    assert client.get("/auth/ai-quota", headers=headers).json()["system_requests_today"] == 0
    bad = client.post("/convert/pdf-to-word/async", headers=headers, json={"file_record_id": 1, "mode": "nope"})
    assert bad.status_code == 422


def test_conversion_output_lives_in_upload_dir(client, make_user, upload):
    """ไฟล์ผลลัพธ์ต้องอยู่ใน UPLOAD_DIR (volume ที่เขียนได้) — ไม่ใช่โฟลเดอร์แม่ซึ่งใน Docker เป็นของ root"""
    from app.core.config import settings
    from app.db.database import SessionLocal
    from app.models.domain import ConversionTask

    _, headers = make_user()
    sid = upload(headers, make_pdf_bytes(pages=1, text="Where"))
    r = client.post("/convert/pdf-to-word/async", headers=headers,
                    json={"file_record_id": _file_id(client, headers, sid), "mode": "layout"})
    with SessionLocal() as db:
        task = db.query(ConversionTask).filter(ConversionTask.id == r.json()["task_id"]).first()
        assert task.status == "completed"
        assert Path(task.result_file_path).resolve().is_relative_to(settings.UPLOAD_DIR.resolve())


def test_word_download_name_and_expiry(client, make_user, upload):
    import os
    import time
    from urllib.parse import unquote

    from app.core.config import settings
    from app.db.database import SessionLocal
    from app.services import file_storage

    _, headers = make_user()
    sid = upload(headers, name="Report.PDF")
    r = client.post("/convert/pdf-to-word/async", headers=headers, json={"file_record_id": _file_id(client, headers, sid)})
    task = r.json()["task_id"]
    dl = client.get(f"/convert/pdf-to-word/download/{task}", headers=headers)
    assert dl.status_code == 200
    assert unquote(dl.headers["content-disposition"]).endswith("Report.docx")  # เดิม "Report.PDF"
    # ไฟล์ผลลัพธ์เก่ากว่า 24 ชม. ถูกเก็บกวาด แล้วดาวน์โหลดแจ้งว่าหมดอายุ
    out = settings.UPLOAD_DIR / "_conversions" / f"{task}.docx"
    old = time.time() - 48 * 3600
    os.utime(out, (old, old))
    db = SessionLocal()
    try:
        file_storage.cleanup_unreferenced_files(db)
    finally:
        db.close()
    assert not out.exists()
    r = client.get(f"/convert/pdf-to-word/download/{task}", headers=headers)
    assert r.status_code == 410 and "หมดอายุ" in r.json()["detail"]


def test_sync_pdf_to_word_requires_login(client):
    r = client.post("/convert/pdf-to-word", files={"file": ("a.pdf", make_pdf_bytes(), "application/pdf")})
    assert r.status_code == 401
