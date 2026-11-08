"""ลายเซ็นในหน้าแก้ไข: ตรวจใบรับรองก่อนวางตำแหน่ง, ใบหมดอายุ, ตำแหน่งบนหน้าที่หมุน/CropBox, เอกสารที่ตั้งรหัสผ่าน"""
import base64
import datetime as dt
import io

import fitz
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from PIL import Image

from tests.conftest import make_pdf_bytes
from tests.signing_helpers import make_p12


def _p12(days_from=-1, days_to=30, pw="pw"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "สมชาย ทดสอบ")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now + dt.timedelta(days=days_from)).not_valid_after(now + dt.timedelta(days=days_to))
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"x", key, cert, None, serialization.BestAvailableEncryption(pw.encode()))


def _check(client, h, data, pw):
    return client.post("/signature/check-certificate", headers=h, data={"password": pw},
                       files={"file": ("me.p12", data, "application/x-pkcs12")})


def test_check_certificate(client, make_user):
    _, h = make_user()
    r = _check(client, h, make_p12("Somchai", "s@example.com"), "p12-pass")
    assert r.status_code == 200, r.text
    assert r.json()["common_name"] == "Somchai" and r.json()["warnings"]  # self-signed + ใกล้หมดอายุ
    assert _check(client, h, make_p12("S", "s@example.com"), "wrong").status_code == 400
    assert "หมดอายุ" in _check(client, h, _p12(-60, -1), "pw").json()["detail"]
    assert "ยังไม่ถึง" in _check(client, h, _p12(5, 60), "pw").json()["detail"]
    assert _check(client, h, b"not a p12", "pw").status_code == 400


def _sign(client, h, sid, rect, pw="p12-pass", data=None):
    return client.post(f"/signature/{sid}/digital", headers=h, data={
        "page_number": 0, "x0": rect[0], "y0": rect[1], "x1": rect[2], "y1": rect[3], "password": pw},
        files={"file": ("me.p12", data or make_p12("Somchai", "s@example.com"), "application/x-pkcs12")})


def _widget_rect(client, h, sid):
    out = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    w = next(out[0].widgets())
    return out[0], fitz.Rect(w.rect)


@pytest.mark.parametrize("variant", ["plain", "rotated", "cropbox"])
def test_signature_lands_where_placed(client, make_user, upload, variant):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    if variant == "rotated":
        p.set_rotation(90)
    if variant == "cropbox":
        p.set_mediabox(fitz.Rect(0, 0, 700, 900))
        p.set_cropbox(fitz.Rect(50, 30, 645, 872))
    _, h = make_user()
    sid = upload(h, d.tobytes(), name="doc.pdf")
    rect = (100, 400, 300, 480)
    r = _sign(client, h, sid, rect)
    assert r.status_code == 200, r.text
    page, wr = _widget_rect(client, h, sid)
    # widget.rect ของ PyMuPDF เป็นพิกัดหน้าแบบไม่หมุน — แปลงเป็นพิกัดบนจอก่อนเทียบ
    shown = wr * page.rotation_matrix
    assert abs(shown.x0 - 100) < 1 and abs(shown.y0 - 400) < 1 and abs(shown.x1 - 300) < 1, (variant, shown)


def test_digital_sign_refused_when_password_set(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(), name="doc.pdf")
    assert client.post(f"/pdf/{sid}/add-password", headers=h, json={"password": "pw-1234"}).status_code == 200
    r = _sign(client, h, sid, (100, 600, 300, 680))
    assert r.status_code == 400 and "ลบรหัสผ่าน" in r.json()["detail"]


def test_expired_certificate_refused_at_sign(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(), name="doc.pdf")
    r = _sign(client, h, sid, (100, 600, 300, 680), pw="pw", data=_p12(-60, -1))
    assert r.status_code == 400 and "หมดอายุ" in r.json()["detail"]


def test_electronic_after_digital_keeps_digital_status(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(), name="doc.pdf")
    assert _sign(client, h, sid, (100, 600, 300, 680)).status_code == 200
    buf = io.BytesIO()
    Image.new("RGBA", (60, 20), (0, 0, 0, 255)).save(buf, "PNG")
    r = client.post(f"/signature/{sid}/electronic", headers=h, json={
        "page_number": 0, "rect": {"x0": 100, "y0": 100, "x1": 200, "y1": 140},
        "image_base64": base64.b64encode(buf.getvalue()).decode()})
    assert r.status_code == 200, r.text
    assert client.get(f"/pdf/{sid}/info", headers=h).json()["signature_type"] == "digital"


def test_sign_file_with_nonstandard_xref(client, make_user):
    """ไฟล์ที่ xref ผิดมาตรฐาน ("0000000000 65536 f") — เดิมเซ็นไม่ได้ "Illegal generation 65536" """
    from pathlib import Path

    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature

    data = (Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "fixtures" / "sample.pdf").read_bytes()
    assert b"0000000000 65536 f" in data
    _, h = make_user()
    sid = client.post("/pdf/upload", headers=h, files={"file": ("s.pdf", data, "application/pdf")}).json()["session_id"]
    r = _sign(client, h, sid, (300, 700, 500, 780))
    assert r.status_code == 200, r.text
    out = client.get(f"/pdf/{sid}/download", headers=h).content
    sig = PdfFileReader(io.BytesIO(out)).embedded_signatures[0]
    status = validate_pdf_signature(sig)
    assert status.intact and status.valid
