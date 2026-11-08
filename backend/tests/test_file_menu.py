"""เมนูไฟล์: พิมพ์ (ไฟล์ที่ตั้งรหัสผ่าน/เปิดด้วยรหัสผ่าน), บันทึกสำเนา/เปลี่ยนชื่อ (ชื่อไฟล์ปลอดภัย ไม่ซ้ำ)"""
import fitz
import pytest

from tests.conftest import make_pdf_bytes


def _encrypted_pdf(pw="pw1234"):
    d = fitz.open("pdf", make_pdf_bytes())
    return d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=pw, owner_pw=pw)


@pytest.mark.parametrize("layout", ["auto", "as_shown"])
def test_print_is_never_encrypted(client, make_user, upload, layout):
    _, h = make_user()
    sid = upload(h, name="doc.pdf")
    assert client.post(f"/pdf/{sid}/add-password", headers=h, json={"password": "pw-1234"}).status_code == 200
    r = client.get(f"/pdf/{sid}/print", headers=h, params={"layout": layout})
    assert r.status_code == 200, r.text
    assert not fitz.open("pdf", r.content).needs_pass  # เดิม (auto): ไฟล์เข้ารหัส พิมพ์ใน iframe ไม่ได้


def test_print_document_opened_with_password(client, make_user):
    _, h = make_user()
    r = client.post("/pdf/upload", headers=h, files={"file": ("lock.pdf", _encrypted_pdf(), "application/pdf")})
    sid = r.json()["session_id"]
    assert client.post(f"/pdf/{sid}/unlock", headers=h, json={"password": "pw1234"}).json()["status"] != "invalid_password"
    for layout in ("auto", "as_shown"):
        r = client.get(f"/pdf/{sid}/print", headers=h, params={"layout": layout})
        assert r.status_code == 200, r.text
        assert not fitz.open("pdf", r.content).needs_pass


def _files(client, h):
    return {f["filename"] for f in client.get("/pdf/files", headers=h).json()["files"]}


def test_save_as_copy_cleans_and_dedupes_name(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, name="doc.pdf")
    for _ in range(2):
        r = client.post(f"/pdf/{sid}/save-as-copy", headers=h, json={"filename": 'ส/ัญญา:"ใหม่"?.PDF'})
        assert r.status_code == 200, r.text
    names = _files(client, h)
    assert "ส ัญญา ใหม่.pdf" in names and "ส ัญญา ใหม่ (2).pdf" in names
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=h, json={"filename": "  /  "})
    assert r.status_code == 400


def test_rename_cleans_and_dedupes(client, make_user, upload):
    _, h = make_user()
    upload(h, name="a.pdf")
    upload(h, name="b.pdf")
    files = client.get("/pdf/files", headers=h).json()["files"]
    b = next(f for f in files if f["filename"] == "b.pdf")
    r = client.put(f"/pdf/files/{b['id']}/rename", headers=h, json={"filename": "a"})
    assert r.status_code == 200
    assert r.json()["filename"] == "a (2).pdf"  # เดิม: สองไฟล์ชื่อ a.pdf
    r = client.put(f"/pdf/files/{b['id']}/rename", headers=h, json={"filename": "a (2).pdf"})
    assert r.json()["filename"] == "a (2).pdf"  # ชื่อเดิมของตัวเอง ไม่เติมเลขซ้ำ
    r = client.put(f"/pdf/files/{b['id']}/rename", headers=h, json={"filename": "../../etc/x"})
    assert "/" not in r.json()["filename"] and r.json()["filename"].endswith("etc x.pdf")
