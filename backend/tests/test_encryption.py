"""เข้ารหัส PDF: AES-256 (ค่าเริ่มต้น PDF 1.7 + Adobe Extension Level 8) / AES-128 (โปรแกรมรุ่นเก่า), รหัสภาษาไทย, PDF/A"""
import io

import fitz
import pikepdf
import pytest

from tests.conftest import make_pdf_bytes
from tests.test_file_signature_status import _file_id


def _download(client, headers, sid) -> bytes:
    r = client.get(f"/pdf/{sid}/download", headers=headers)
    assert r.status_code == 200, r.text
    return r.content


def _pdfa_bytes() -> bytes:
    pdf = pikepdf.open(io.BytesIO(make_pdf_bytes(pages=1, text="Archive")))
    with pdf.open_metadata() as meta:
        meta["pdfaid:part"] = "2"
        meta["pdfaid:conformance"] = "B"
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


@pytest.mark.parametrize("password", ["Secret-123", "รหัสลับ๑๒๓"])
def test_default_aes256_is_conforming_pdf17(client, make_user, upload, password):
    _, h = make_user()
    sid = upload(h)
    r = client.post(f"/pdf/{sid}/add-password", headers=h, json={"password": password})
    assert r.status_code == 200, r.text
    data = _download(client, h, sid)
    assert data.startswith(b"%PDF-1.7")
    with pikepdf.open(io.BytesIO(data), password=password) as pdf:
        assert pdf.encryption.R == 6 and pdf.extension_level == 8   # AES-256 ต้องมี Adobe Extension Level 8 ใน PDF 1.7
    doc = fitz.open("pdf", data)
    assert doc.needs_pass and doc.authenticate(password)
    props = client.get(f"/pdf/{sid}/properties", headers=h).json()
    assert props["is_encrypted"] and props["encryption"] == "aes256"


def test_aes128_compat_mode(client, make_user, upload):
    _, h = make_user()
    sid = upload(h)
    assert client.post(f"/pdf/{sid}/add-password", headers=h,
                       json={"password": "Old-Reader-1", "encryption": "aes128"}).status_code == 200
    data = _download(client, h, sid)
    with pikepdf.open(io.BytesIO(data), password="Old-Reader-1") as pdf:
        assert pdf.encryption.R == 4 and pdf.pdf_version == "1.7"
    assert fitz.open("pdf", data).authenticate("Old-Reader-1")


@pytest.mark.parametrize("password,msg", [("รหัสไทย", "ภาษาไทย"), ("x" * 33, "32")])
def test_aes128_rejects_unsupported_passwords(client, make_user, upload, password, msg):
    _, h = make_user()
    sid = upload(h)
    r = client.post(f"/pdf/{sid}/add-password", headers=h, json={"password": password, "encryption": "aes128"})
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_encrypting_pdfa_removes_claim_and_properties_report_it(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _pdfa_bytes())
    assert client.get(f"/pdf/{sid}/properties", headers=h).json()["pdfa"] == "PDF/A-2b"
    fid = _file_id(client, h, sid)
    assert client.get(f"/pdf/files/{fid}/signature-status", headers=h).json()["pdfa"] == "PDF/A-2b"
    client.post(f"/pdf/{sid}/add-password", headers=h, json={"password": "pw-123"})
    with pikepdf.open(io.BytesIO(_download(client, h, sid)), password="pw-123") as pdf:
        meta = pdf.open_metadata()
        assert "pdfaid:part" not in meta   # ไม่อ้าง PDF/A ทั้งที่เข้ารหัส (PDF/A ห้ามเข้ารหัส)


def test_quick_encrypt_modes(client, make_user, upload):
    _, h = make_user()
    fid = _file_id(client, h, upload(h, name="a.pdf"))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=h,
                    json={"action": "encrypt", "new_password": "รหัสไทย", "encryption": "aes128"})
    assert r.status_code == 400 and "ภาษาไทย" in r.json()["detail"]
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=h,
                    json={"action": "encrypt", "new_password": "pass-128", "encryption": "aes128"})
    assert r.status_code == 200, r.text
    data = client.get(f"/pdf/files/{r.json()['file']['id']}/download", headers=h).content
    with pikepdf.open(io.BytesIO(data), password="pass-128") as pdf:
        assert pdf.encryption.R == 4


def test_save_copy_old_version_with_thai_password_gives_clear_error(client, make_user, upload):
    _, h = make_user()
    sid = upload(h)
    client.post(f"/pdf/{sid}/add-password", headers=h, json={"password": "รหัสไทย"})
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=h, json={"filename": "old", "pdf_version": "1.4"})
    assert r.status_code == 400 and "PDF 1.7" in r.json()["detail"]
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=h, json={"filename": "new", "pdf_version": "1.7"})
    assert r.status_code == 200, r.text
    data = client.get(f"/pdf/files/{r.json()['new_id']}/download", headers=h).content
    with pikepdf.open(io.BytesIO(data), password="รหัสไทย") as pdf:
        assert pdf.encryption.R == 6 and pdf.pdf_version == "1.7" and pdf.extension_level == 8
