"""GET /pdf/files/{id}/signature-status — Dashboard เตือนก่อนใส่ลายน้ำ/เซ็นเซอร์ไฟล์ที่ลงนามแล้ว"""
from tests.test_signing import _email, _file_id, _sign_electronic
from tests.test_signing_phase3 import _box, _create


def test_plain_upload_is_not_signed(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner))
    r = client.get(f"/pdf/files/{fid}/signature-status", headers=owner)
    assert r.status_code == 200 and r.json() == {"signed": False, "count": 0, "pdfa": None}


def test_completed_signing_result_is_signed(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **_box(0)}]).json()["id"]
    assert _sign_electronic(client, signer, rid).status_code == 200
    result_id = client.get(f"/signing/requests/{rid}", headers=owner).json()["result_file_id"]
    body = client.get(f"/pdf/files/{result_id}/signature-status", headers=owner).json()
    assert body["signed"] is True and body["count"] == 1


def test_other_users_file_is_not_found(client, make_user, upload):
    _, owner = make_user()
    _, other = make_user()
    fid = _file_id(client, owner, upload(owner))
    assert client.get(f"/pdf/files/{fid}/signature-status", headers=other).status_code == 404


# ---------------------------------------------------------------------------
# POST /pdf/files/{id}/quick-action — ลายน้ำ / เซ็นเซอร์จาก Dashboard (สร้างไฟล์ใหม่ ไม่แตะไฟล์เดิม)
# ---------------------------------------------------------------------------
import fitz  # noqa: E402

from tests.conftest import make_pdf_bytes  # noqa: E402


def _files(client, headers):
    return client.get("/pdf/files", headers=headers).json()["files"]


def _download(client, headers, session_id):
    opened = client.post(f"/pdf/{session_id}/open", headers=headers).json()
    r = client.get(f"/pdf/{opened['session_id']}/download", headers=headers)
    assert r.status_code == 200, r.text
    return r.content


def _text(pdf_bytes):
    doc = fitz.open("pdf", pdf_bytes)
    try:
        return "".join(p.get_text() for p in doc)
    finally:
        doc.close()


def test_watermark_creates_new_file_and_keeps_original(client, make_user, upload):
    _, owner = make_user()
    sid = upload(owner, make_pdf_bytes(pages=2, text="Secret plan"), name="แผนงาน.pdf")
    fid = _file_id(client, owner, sid)
    original = next(f for f in _files(client, owner) if f["id"] == fid)

    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner,
                    json={"action": "watermark", "watermark": {"text": "CONFIDENTIAL", "opacity": 0.3}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["file"]["filename"] == "แผนงาน (ลายน้ำ).pdf"

    files = _files(client, owner)
    assert len(files) == 2
    assert next(f for f in files if f["id"] == fid)["updated_at"] == original["updated_at"]  # ไฟล์เดิมไม่ถูกแก้
    new_pdf = _download(client, owner, body["file"]["session_id"])
    assert fitz.open("pdf", new_pdf).page_count == 2


def test_redact_search_removes_text_in_copy(client, make_user, upload):
    _, owner = make_user()
    sid = upload(owner, make_pdf_bytes(pages=1, text="Account 123-456 belongs to Alice"))
    fid = _file_id(client, owner, sid)
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner,
                    json={"action": "redact_search", "keyword": "Alice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["count"] >= 1 and body["file"]["filename"].endswith("(เซ็นเซอร์).pdf")
    assert "Alice" not in _text(_download(client, owner, body["file"]["session_id"]))
    assert "Alice" in _text(_download(client, owner, sid))  # ต้นฉบับยังอยู่ครบ


def test_redact_search_not_found_creates_nothing(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, make_pdf_bytes(pages=1, text="Hello")))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner,
                    json={"action": "redact_search", "keyword": "Nowhere"})
    assert r.status_code == 200 and r.json() == {"status": "not_found", "count": 0, "image_pages": []}
    assert len(_files(client, owner)) == 1


def test_quick_action_password_protected_file(client, make_user, upload):
    _, owner = make_user()
    doc = fitz.open("pdf", make_pdf_bytes(pages=1, text="Locked"))
    locked = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="pw1234", user_pw="pw1234")
    doc.close()
    fid = _file_id(client, owner, upload(owner, locked))
    payload = {"action": "watermark", "watermark": {"text": "DRAFT"}}
    assert client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json=payload).status_code == 423
    assert client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={**payload, "password": "nope"}).status_code == 423
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={**payload, "password": "pw1234"})
    assert r.status_code == 200, r.text
    assert len(_files(client, owner)) == 2
    from app.services import file_storage

    stored = file_storage.upload_path(r.json()["file"]["session_id"]).read_bytes()
    assert fitz.open("pdf", stored).needs_pass  # ไฟล์ใหม่ยังล็อกด้วยรหัสผ่านเดิม


def test_quick_action_other_user_404(client, make_user, upload):
    _, owner = make_user()
    _, other = make_user()
    fid = _file_id(client, owner, upload(owner))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=other, json={"action": "redact_search", "keyword": "x"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# เมนู ☰: ดาวน์โหลด / คุณสมบัติเอกสาร / เข้ารหัส (โดยไม่ต้องเปิดไฟล์)
# ---------------------------------------------------------------------------
def _locked_pdf(password="pw1234"):
    doc = fitz.open("pdf", make_pdf_bytes(pages=1, text="Locked"))
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=password, user_pw=password)
    doc.close()
    return data


def test_download_stored_file(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, make_pdf_bytes(pages=3), name="รายงาน.pdf"))
    r = client.get(f"/pdf/files/{fid}/download", headers=owner)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert fitz.open("pdf", r.content).page_count == 3
    assert "filename*=utf-8''" in r.headers["content-disposition"].lower()  # ชื่อไทยส่งแบบ RFC 5987


def test_properties_of_stored_file(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, make_pdf_bytes(pages=2)))
    r = client.post(f"/pdf/files/{fid}/properties", headers=owner, json={})
    assert r.status_code == 200, r.text
    assert r.json()["page_count"] == 2


def test_properties_of_password_file_needs_password(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, _locked_pdf()))
    assert client.post(f"/pdf/files/{fid}/properties", headers=owner, json={}).status_code == 423
    r = client.post(f"/pdf/files/{fid}/properties", headers=owner, json={"password": "pw1234"})
    assert r.status_code == 200 and r.json()["is_encrypted"] is True


def test_encrypt_creates_protected_copy(client, make_user, upload):
    _, owner = make_user()
    sid = upload(owner, make_pdf_bytes(pages=1), name="สลิป.pdf")
    fid = _file_id(client, owner, sid)
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={"action": "encrypt", "new_password": "s3cret!"})
    assert r.status_code == 200, r.text
    new = r.json()["file"]
    assert new["filename"] == "สลิป (เข้ารหัส).pdf"
    from app.services import file_storage

    doc = fitz.open("pdf", file_storage.upload_path(new["session_id"]).read_bytes())
    assert doc.needs_pass and doc.authenticate("s3cret!")
    assert not fitz.open("pdf", client.get(f"/pdf/files/{fid}/download", headers=owner).content).needs_pass


def test_encrypt_signed_file_is_refused(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **_box(0)}]).json()["id"]
    assert _sign_electronic(client, signer, rid).status_code == 200
    result_id = client.get(f"/signing/requests/{rid}", headers=owner).json()["result_file_id"]
    before = len(_files(client, owner))
    r = client.post(f"/pdf/files/{result_id}/quick-action", headers=owner, json={"action": "encrypt", "new_password": "x1"})
    assert r.status_code == 400 and "ลงนาม" in r.json()["detail"]
    assert len(_files(client, owner)) == before
