"""เฟส 3: ลงนามพร้อมกัน (stage), เชิญคนที่ยังไม่มีบัญชี, หลักฐานแนบท้าย, หน้าที่หมุน"""
import io

import fitz
import pytest

from app.services import mailer
from tests.conftest import make_pdf_bytes
from tests.test_signing import _email, _file_id, _sign_electronic


@pytest.fixture
def outbox(monkeypatch):
    sent: list[mailer.Mail] = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


def _box(i, page=0):
    return {"page": page, "x0": 40 + i * 130, "y0": 600, "x1": 160 + i * 130, "y1": 660}


def _create(client, owner, upload, steps, pdf=None):
    sid = upload(owner, pdf or make_pdf_bytes(pages=1, text="Agreement"))
    r = client.post("/signing/requests", headers=owner,
                    json={"file_id": _file_id(client, owner, sid), "title": "Agreement", "steps": steps})
    return r


def _make_named_user(client, email, verified=True, password="Passw0rd-123"):
    from app.core.security import get_password_hash
    from app.db.database import SessionLocal
    from app.models.domain import User

    db = SessionLocal()
    try:
        db.add(User(email=email, hashed_password=get_password_hash(password), is_verified=verified, is_active=True,
                    plan_type="premium", accepted_tos=True))
        db.commit()
    finally:
        db.close()
    return password


def _login(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_parallel_stage_waits_for_everyone(client, make_user, upload, outbox):
    _, owner = make_user()
    a, b, c = (make_user()[1] for _ in range(3))
    steps = [
        {"email": _email(client, a), "sign_type": "electronic", **_box(0)},
        {"email": _email(client, b), "sign_type": "electronic", "parallel": True, **_box(1)},
        {"email": _email(client, c), "sign_type": "electronic", **_box(2)},
    ]
    r = _create(client, owner, upload, steps)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert [s["stage"] for s in r.json()["steps"]] == [1, 1, 2]
    # A และ B ได้อีเมลถึงคิวพร้อมกัน, C ยังไม่ได้
    turn = {m.to for m in outbox if m.subject.startswith("ถึงคิวคุณลงนาม")}
    assert turn == {_email(client, a), _email(client, b)}

    assert client.get(f"/signing/requests/{rid}", headers=a).json()["my_turn"]
    assert client.get(f"/signing/requests/{rid}", headers=b).json()["my_turn"]
    assert _sign_electronic(client, c, rid).status_code == 409  # C ยังไม่ถึงขั้น

    assert _sign_electronic(client, b, rid).status_code == 200  # B เซ็นก่อน A ได้
    data = client.get(f"/signing/requests/{rid}", headers=owner).json()
    assert data["current_order"] == 1 and data["waiting_for"] == [_email(client, a)]
    assert _sign_electronic(client, c, rid).status_code == 409

    assert _sign_electronic(client, a, rid).status_code == 200
    assert client.get(f"/signing/requests/{rid}", headers=c).json()["my_turn"]
    assert _sign_electronic(client, c, rid).status_code == 200
    data = client.get(f"/signing/requests/{rid}", headers=owner).json()
    assert data["status"] == "completed"
    report = client.get(f"/signing/requests/{rid}/verify", headers=owner).json()["signatures"]
    assert len(report) == 3 and all(x["signed"] and x["intact"] and x["valid"] and x["modification_ok"] for x in report)


def test_invite_unregistered_signer_then_claim_on_login(client, make_user, upload, outbox):
    _, owner = make_user()
    _, second = make_user()
    invitee = "new.person@example.org"
    steps = [
        {"email": invitee.upper(), "sign_type": "electronic", **_box(0)},
        {"email": _email(client, second), "sign_type": "electronic", **_box(1)},
    ]
    r = _create(client, owner, upload, steps)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    first = r.json()["steps"][0]["signer"]
    assert first["invited"] and first["email"] == invitee and first["id"] is None

    invite = [m for m in outbox if m.to == invitee]
    assert len(invite) == 1 and invite[0].subject.startswith("คุณได้รับเชิญ")
    assert "register=1" in invite[0].text and "new.person%40example.org" in invite[0].text
    assert invite[0].reply_to == _email(client, owner)

    # ยังไม่ยืนยันอีเมล → ยังไม่ผูก
    pw = _make_named_user(client, invitee, verified=False)
    assert client.post("/auth/login", data={"username": invitee, "password": pw}).status_code == 401

    from app.db.database import SessionLocal
    from app.models.domain import User

    db = SessionLocal()
    try:
        db.query(User).filter(User.email == invitee).update({User.is_verified: True})
        db.commit()
    finally:
        db.close()
    headers = _login(client, invitee, pw)  # login แล้วผูกคำเชิญให้อัตโนมัติ
    data = client.get(f"/signing/requests/{rid}", headers=headers).json()
    assert data["my_turn"] and not data["steps"][0]["signer"]["invited"]
    assert any(e["action"] == "invite_accepted" for e in client.get(f"/signing/requests/{rid}", headers=owner).json()["events"])

    outbox.clear()
    assert _sign_electronic(client, headers, rid).status_code == 200
    assert [m.to for m in outbox if m.subject.startswith("ถึงคิวคุณลงนาม")] == [_email(client, second)]


def test_remind_resends_invite_to_unclaimed_signer(client, make_user, upload, outbox):
    _, owner = make_user()
    r = _create(client, owner, upload, [{"email": "later@example.org", "sign_type": "either", **_box(0)}])
    rid = r.json()["id"]
    outbox.clear()
    assert client.post(f"/signing/requests/{rid}/remind", headers=owner).status_code == 200
    assert [m.to for m in outbox] == ["later@example.org"]


def test_evidence_certificate_is_sealed_and_lists_everything(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **_box(0)}]).json()["id"]
    assert _sign_electronic(client, signer, rid).status_code == 200

    r = client.get(f"/signing/requests/{rid}/evidence", headers=signer)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"]
    with fitz.open("pdf", r.content) as doc:
        text = "".join(p.get_text() for p in doc)
    final = client.get(f"/signing/requests/{rid}", headers=owner).json()["events"][-1]["sha256_after"]
    assert "Agreement" in text and _email(client, signer) in text and final in text

    from app.services import signing_pdf

    report = signing_pdf.signature_report(r.content)
    assert report and report[0]["field_name"] == "EvidenceSeal" and report[0]["intact"] and report[0]["valid"]
    # คำขอจบแล้ว → ใช้ไฟล์เดิม (ค่า hash หลักฐานไม่เปลี่ยนทุกครั้งที่โหลด)
    assert client.get(f"/signing/requests/{rid}/evidence", headers=owner).content == r.content
    # คนนอกโหลดไม่ได้
    _, outsider = make_user()
    assert client.get(f"/signing/requests/{rid}/evidence", headers=outsider).status_code == 404


def test_rotated_page_box_lands_where_the_user_placed_it(client, make_user, upload):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Landscape view")
    page.set_rotation(90)  # ผู้ใช้เห็นเป็นแนวนอน 842 x 595
    pdf = doc.tobytes()
    _, owner = make_user()
    _, signer = make_user()
    box = {"page": 0, "x0": 600, "y0": 480, "x1": 800, "y1": 560}  # มุมขวาล่างของหน้าที่เห็น
    r = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **box}], pdf=pdf)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert _sign_electronic(client, signer, rid).status_code == 200

    signed = client.get(f"/signing/requests/{rid}/document", headers=owner).content
    with fitz.open("pdf", signed) as d:
        p = d[0]
        widget = next(iter(p.widgets()))
        shown = widget.rect * p.rotation_matrix
        assert abs(shown.x0 - 600) < 1 and abs(shown.y0 - 480) < 1 and abs(shown.x1 - 800) < 1 and abs(shown.y1 - 560) < 1
    report = client.get(f"/signing/requests/{rid}/verify", headers=owner).json()["signatures"]
    assert report[0]["intact"] and report[0]["valid"]


def test_legacy_google_password_cannot_log_in(client):
    email = "google-user@example.com"
    _make_named_user(client, email, password=f"google_sso_random_password_{email}")
    r = client.post("/auth/login", data={"username": email, "password": f"google_sso_random_password_{email}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# ตราลายเซ็นพื้นโปร่งใส + timestamp จาก TSA
# ---------------------------------------------------------------------------

def test_signature_stamp_has_transparent_background():
    from app.services import signing_pdf

    from tests.test_signing import _png

    img = signing_pdf._stamp_image(160, 60, ["signer@example.com", "ลงนาม 18/10/2026"], _png())
    assert img.mode == "RGBA"
    assert img.getpixel((2, img.height // 2))[3] == 0          # ขอบซ้ายกลาง: โปร่งใส (ไม่ใช่สีขาว)
    assert max(px[3] for px in img.getdata()) == 255           # มีเส้น/ตัวอักษรทึบอยู่จริง


def _dummy_tsa():
    import datetime as dt

    from asn1crypto import keys, x509 as asn1_x509
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    from pyhanko.sign.timestamps import DummyTimeStamper

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test TSA")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=30))
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
            .sign(key, hashes.SHA256()))
    return DummyTimeStamper(
        tsa_cert=asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER)),
        tsa_key=keys.PrivateKeyInfo.load(key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                                           serialization.NoEncryption())))


def test_tsa_timestamp_is_embedded_when_configured(client, make_user, upload, monkeypatch):
    from app.services import signing_pdf

    tsa = _dummy_tsa()
    monkeypatch.setattr(signing_pdf, "_timestamper", lambda: tsa)
    _, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **_box(0)}]).json()["id"]
    assert _sign_electronic(client, signer, rid).status_code == 200
    report = client.get(f"/signing/requests/{rid}/verify", headers=owner).json()["signatures"]
    assert report[0]["valid"] and report[0]["timestamp"]


def test_unreachable_tsa_falls_back_to_signing_without_timestamp(client, make_user, upload, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SIGNING_TSA_URL", "http://127.0.0.1:9/tsa")  # ไม่มีใครฟังพอร์ตนี้
    monkeypatch.setattr(settings, "SIGNING_TSA_TIMEOUT", 2)
    _, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic", **_box(0)}]).json()["id"]
    assert _sign_electronic(client, signer, rid).status_code == 200
    report = client.get(f"/signing/requests/{rid}/verify", headers=owner).json()["signatures"]
    assert report[0]["valid"] and report[0]["timestamp"] is None
