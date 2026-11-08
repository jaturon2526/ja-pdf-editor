"""รีวิวระบบลงนาม (v1.26.6): รูปลายเซ็นเสีย/ว่าง, สถานะหลังยกเลิก, IP ในหลักฐาน, SSRF ของ AIA, เวลาบนตรา, ชื่อไฟล์"""
import datetime as dt
import io

import pytest
from PIL import Image, ImageDraw

from tests.signing_helpers import make_p12
from tests.test_signing import _email, _png, _sign_digital, three_signers  # noqa: F401
from app.services import signing_pdf, signing_service


def _img(img, fmt="PNG", **kw) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


def _sign_e(client, headers, rid, data, extra_headers=None):
    return client.post(f"/signing/requests/{rid}/sign", headers={**headers, **(extra_headers or {})},
                       data={"sign_type": "electronic"}, files={"signature_image": ("s.png", data, "image/png")})


@pytest.mark.parametrize("data,msg", [
    (b"not an image", "ไม่ถูกต้อง"),
    (_img(Image.new("RGB", (300, 100), "white")), "ว่างเปล่า"),
    (_img(Image.new("RGBA", (300, 100), (0, 0, 0, 0))), "ว่างเปล่า"),
])
def test_bad_signature_image_rejected_not_silently_signed(client, three_signers, data, msg):
    owner, signers, rid = three_signers
    assert _sign_digital(client, signers[0], rid).status_code == 200
    r = _sign_e(client, signers[1], rid, data)
    assert r.status_code == 400 and msg in r.json()["detail"]
    step = client.get(f"/signing/requests/{rid}", headers=owner).json()["steps"][1]
    assert step["status"] == "pending"  # ยังไม่ถือว่าลงนาม


def test_normalize_signature_image_exif_and_size():
    img = Image.new("RGB", (200, 80), "white")
    ImageDraw.Draw(img).line([(10, 40), (190, 40)], fill="black", width=5)
    exif = Image.Exif()
    exif[0x0112] = 6  # หมุน 90° (รูปถ่ายแนวตั้งจากมือถือ)
    out = Image.open(io.BytesIO(signing_pdf.normalize_signature_image(_img(img, "JPEG", exif=exif))))
    assert out.size == (80, 200) and out.mode == "RGBA"
    with pytest.raises(signing_pdf.SigningPdfError, match="ใหญ่เกินไป"):
        signing_pdf.normalize_signature_image(_img(Image.new("1", (6000, 5000), 1)))


def test_cancelled_request_steps_show_skipped(client, three_signers):
    owner, signers, rid = three_signers
    assert client.post(f"/signing/requests/{rid}/cancel", headers=owner).status_code == 200
    data = client.get(f"/signing/requests/{rid}", headers=owner).json()
    assert [s["status"] for s in data["steps"]] == ["skipped", "skipped", "skipped"]
    assert data["created_at"].endswith("+00:00")


def test_event_ip_not_spoofable_via_forwarded_header(client, three_signers):
    owner, signers, rid = three_signers
    r = client.post(f"/signing/requests/{rid}/sign", headers={**signers[0], "X-Forwarded-For": "6.6.6.6, 203.0.113.9"},
                    data={"sign_type": "digital", "pfx_password": "p12-pass"},
                    files={"pfx_file": ("me.p12", make_p12("A", "a@example.com"), "application/x-pkcs12")})
    assert r.status_code == 200
    _sign_e(client, signers[1], rid, _png(), {"X-Real-IP": "198.51.100.7", "X-Forwarded-For": "6.6.6.6"})
    from app.db.database import SessionLocal
    from app.models.domain import SigningEvent

    db = SessionLocal()
    try:
        ips = [e.ip for e in db.query(SigningEvent).filter(SigningEvent.request_id == rid,
                                                            SigningEvent.action == "signed").order_by(SigningEvent.id)]
    finally:
        db.close()
    assert ips == ["203.0.113.9", "198.51.100.7"]


@pytest.mark.parametrize("url", ["http://127.0.0.1/ca.cer", "http://169.254.169.254/latest/meta-data",
                                 "http://10.0.0.5/x.crt", "http://localhost:6379/", "ftp://example.com/a.cer",
                                 "http://[::1]/a.cer"])
def test_aia_fetch_refuses_internal_addresses(url):
    with pytest.raises(signing_pdf.SigningPdfError):
        signing_pdf._fetch_url(url)


def test_stamp_time_uses_app_timezone(monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(signing_service.settings, "APP_TIMEZONE", "Asia/Bangkok")
    expected = dt.datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H")
    assert signing_service.local_now_text().startswith(expected)


def test_completed_file_name_unique(client, make_user, upload):
    from tests.conftest import make_pdf_bytes
    from tests.test_signing import _file_id

    _, owner = make_user()
    _, signer = make_user()
    sid = upload(owner, make_pdf_bytes(pages=1, text="x"))
    fid = _file_id(client, owner, sid)
    for _ in range(2):
        rid = client.post("/signing/requests", headers=owner, json={
            "file_id": fid, "title": "สัญญา", "steps": [{"email": _email(client, signer), "sign_type": "electronic",
                                                         "page": 0, "x0": 50, "y0": 600, "x1": 200, "y1": 660}]}).json()["id"]
        assert _sign_e(client, signer, rid, _png()).json()["status"] == "completed"
    names = sorted(f["filename"] for f in client.get("/pdf/files", headers=owner).json()["files"])
    assert "สัญญา (ลงนามครบแล้ว).pdf" in names and "สัญญา (ลงนามครบแล้ว) (2).pdf" in names
