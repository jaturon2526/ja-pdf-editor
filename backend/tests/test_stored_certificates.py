"""ใบรับรองที่เก็บไว้บนระบบ: ตรวจรหัสก่อนเก็บ, ไม่เก็บรหัส, ใช้เซ็นด้วย id + รหัส, ลบต้องยืนยันรหัส, กันเดารหัส"""
import fitz
import pytest

from app.db.database import SessionLocal
from app.models.domain import UserCertificate
from app.services import certificate_store
from tests.conftest import make_pdf_bytes
from tests.signing_helpers import make_p12
from tests.test_sign_editor import _p12

PW = "p12-pass"


def _upload_cert(client, h, data=None, pw=PW, label=None):
    form = {"password": pw}
    if label:
        form["label"] = label
    return client.post("/signature/certificates", headers=h, data=form,
                       files={"file": ("me.p12", data or make_p12("สมชาย ใจดี", "s@example.com"), "application/x-pkcs12")})


def test_upload_verifies_password_and_stores_metadata_without_password(client, make_user):
    uid, h = make_user()
    data = make_p12("สมชาย ใจดี", "s@example.com")
    assert _upload_cert(client, h, data, pw="wrong").status_code == 400
    assert client.get("/signature/certificates", headers=h).json() == []

    r = _upload_cert(client, h, data, label="ใบงาน")
    assert r.status_code == 201, r.text
    cert = r.json()
    assert cert["label"] == "ใบงาน" and cert["subject_cn"] == "สมชาย ใจดี" and cert["issuer_cn"] == "สมชาย ใจดี"
    assert cert["self_signed"] and not cert["expired"] and cert["valid_from"] and cert["valid_to"] and cert["created_at"]
    assert "pfx" not in str(cert).lower() and PW not in str(cert)

    db = SessionLocal()
    try:
        row = db.query(UserCertificate).filter_by(user_id=uid).one()
        blob = bytes(row.pfx_encrypted)
        assert blob != data and data not in blob  # เข้ารหัสซ้ำ ไม่ใช่ไฟล์เดิม
        assert PW.encode() not in blob and all(PW not in str(v) for v in row.__dict__.values())
    finally:
        db.close()

    listed = client.get("/signature/certificates", headers=h).json()
    assert [c["id"] for c in listed] == [cert["id"]]
    assert _upload_cert(client, h, data).status_code == 409  # ใบเดิมซ้ำ


@pytest.mark.parametrize("data,pw,msg", [
    (lambda: _p12(-60, -1), "pw", "หมดอายุ"),
    (lambda: _p12(5, 60), "pw", "ยังไม่ถึง"),
    (lambda: b"not a p12", "pw", "เปิดไฟล์ใบรับรองไม่สำเร็จ"),
])
def test_upload_rejects_unusable_certificates(client, make_user, data, pw, msg):
    _, h = make_user()
    r = _upload_cert(client, h, data(), pw=pw)
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_limit_per_user(client, make_user, monkeypatch):
    monkeypatch.setattr(certificate_store, "MAX_PER_USER", 2)
    _, h = make_user()
    for i in range(2):
        assert _upload_cert(client, h, make_p12(f"U{i}", "u@example.com")).status_code == 201
    r = _upload_cert(client, h, make_p12("U9", "u@example.com"))
    assert r.status_code == 400 and "สูงสุด 2" in r.json()["detail"]


def test_sign_in_editor_with_stored_certificate(client, make_user, upload):
    _, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    sid = upload(h)
    form = {"page_number": 0, "x0": 50, "y0": 50, "x1": 250, "y1": 120, "certificate_id": cid}
    assert client.post(f"/signature/{sid}/digital", headers=h, data={**form, "password": "nope"}).status_code == 400
    check = client.post("/signature/check-certificate", headers=h, data={"certificate_id": cid, "password": PW})
    assert check.status_code == 200 and check.json()["common_name"] == "สมชาย ใจดี"
    r = client.post(f"/signature/{sid}/digital", headers=h, data={**form, "password": PW})
    assert r.status_code == 200 and r.json()["signer_name"] == "สมชาย ใจดี", r.text
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    assert any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE for w in doc[0].widgets())
    assert client.get("/signature/certificates", headers=h).json()[0]["last_used_at"]


def test_certificate_belongs_to_owner_only(client, make_user, upload):
    _, owner = make_user()
    _, other = make_user()
    cid = _upload_cert(client, owner).json()["id"]
    sid = upload(other)
    r = client.post(f"/signature/{sid}/digital", headers=other, data={
        "page_number": 0, "x0": 50, "y0": 50, "x1": 250, "y1": 120, "certificate_id": cid, "password": PW})
    assert r.status_code == 404
    assert client.post(f"/signature/certificates/{cid}/delete", headers=other, json={"password": PW}).status_code == 404
    assert client.get("/signature/certificates", headers=other).json() == []


def test_delete_requires_password(client, make_user):
    _, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    assert client.post(f"/signature/certificates/{cid}/delete", headers=h, json={"password": "x"}).status_code == 400
    assert len(client.get("/signature/certificates", headers=h).json()) == 1
    assert client.post(f"/signature/certificates/{cid}/delete", headers=h, json={"password": PW}).status_code == 204
    assert client.get("/signature/certificates", headers=h).json() == []


def test_wrong_passwords_lock_temporarily(client, make_user, monkeypatch):
    monkeypatch.setattr(certificate_store, "WRONG_PASSWORD_MAX", 3)
    _, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    codes = [client.post("/signature/check-certificate", headers=h, data={"certificate_id": cid, "password": "x"}).status_code
             for _ in range(3)]
    assert codes == [400, 400, 400]
    r = client.post("/signature/check-certificate", headers=h, data={"certificate_id": cid, "password": PW})
    assert r.status_code == 429  # ถูกแล้วก็ต้องรอ


def test_secret_rotation_reports_reupload(client, make_user, monkeypatch):
    _, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    from app.core import security

    monkeypatch.setattr(security, "SECRET_KEY", "a-different-secret-" + "x" * 32)
    r = client.post("/signature/check-certificate", headers=h, data={"certificate_id": cid, "password": PW})
    assert r.status_code == 409 and "อัปโหลดใหม่" in r.json()["detail"]


def test_signing_request_with_stored_certificate(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    email = client.get("/auth/me", headers=signer).json()["email"]
    sid = upload(owner, make_pdf_bytes(pages=1, text="Contract"))
    from tests.test_signing import _file_id

    fid = _file_id(client, owner, sid)
    rid = client.post("/signing/requests", headers=owner, json={"file_id": fid, "title": "C", "steps": [
        {"email": email, "sign_type": "digital", "page": 0, "x0": 50, "y0": 600, "x1": 200, "y1": 660}]}).json()["id"]
    cid = _upload_cert(client, signer, make_p12("ผู้ลงนาม", email)).json()["id"]
    bad = client.post(f"/signing/requests/{rid}/sign", headers=signer,
                      data={"sign_type": "digital", "certificate_id": cid, "pfx_password": "wrong"})
    assert bad.status_code == 400
    r = client.post(f"/signing/requests/{rid}/sign", headers=signer,
                    data={"sign_type": "digital", "certificate_id": cid, "pfx_password": PW})
    assert r.status_code == 200, r.text


def test_account_deletion_removes_certificates(client, make_user):
    from tests.test_account_deletion import _delete

    uid, h = make_user()
    _upload_cert(client, h)
    assert client.get("/auth/account/deletion-summary", headers=h).json()["certificates"] == 1
    assert _delete(client, h).status_code == 200
    db = SessionLocal()
    try:
        assert db.query(UserCertificate).filter_by(user_id=uid).count() == 0
    finally:
        db.close()


def test_correct_password_resets_wrong_count(client, make_user, monkeypatch):
    monkeypatch.setattr(certificate_store, "WRONG_PASSWORD_MAX", 3)
    _, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    check = lambda pw: client.post("/signature/check-certificate", headers=h,
                                   data={"certificate_id": cid, "password": pw}).status_code
    assert [check("x"), check("x"), check(PW)] == [400, 400, 200]
    assert [check("x"), check("x"), check(PW)] == [400, 400, 200]  # นับใหม่หลังกรอกถูก


# ---------- ปลดล็อกด้วย passkey (WebAuthn PRF — รหัสถูกเข้ารหัสในเบราว์เซอร์ server ถอดไม่ได้) ----------

import os  # noqa: E402

from webauthn.helpers import bytes_to_base64url  # noqa: E402

from app.models.domain import CertificatePasskey  # noqa: E402
from tests.test_passkey import SoftAuthenticator, _register  # noqa: E402
from tests.test_passkey import _rp as _rp  # noqa: E402,F401 — RP ID = localhost

SALT = bytes_to_base64url(os.urandom(32))
WRAPPED = bytes_to_base64url(os.urandom(12 + 16 + len(PW)))  # ในเบราว์เซอร์ = AES-GCM ของรหัส (server ไม่สนเนื้อใน)


def _bind(client, h, cid, auth, pw=PW, **over):
    opts = client.post(f"/signature/certificates/{cid}/passkeys/options", headers=h)
    assert opts.status_code == 200, opts.text
    body = opts.json()
    assert body["options"]["allowCredentials"]  # จำกัดเฉพาะ passkey ของบัญชีนี้
    payload = {"flow_id": body["flow_id"], "credential": auth.get(body["options"]), "password": pw,
               "prf_salt": SALT, "wrapped": WRAPPED, **over}
    return client.post(f"/signature/certificates/{cid}/passkeys", headers=h, json=payload)


def test_bind_passkey_requires_passkey_and_correct_password(client, make_user):
    _, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    r = client.post(f"/signature/certificates/{cid}/passkeys/options", headers=h)
    assert r.status_code == 400 and "ยังไม่มี passkey" in r.json()["detail"]

    auth = SoftAuthenticator()
    assert _register(client, h, auth, "iPhone").status_code == 200
    assert _bind(client, h, cid, auth, pw="wrong").status_code == 400
    assert _bind(client, h, cid, auth, prf_salt="short").status_code == 400
    assert client.get("/signature/certificates", headers=h).json()[0]["passkeys"] == []

    r = _bind(client, h, cid, auth)
    assert r.status_code == 201, r.text
    [b] = r.json()["passkeys"]
    assert b["name"] == "iPhone" and b["rp_id"] == "localhost" and b["prf_salt"] == SALT and b["wrapped"] == WRAPPED
    assert b["credential_id"] == bytes_to_base64url(auth.cred_id)
    # ผูกซ้ำด้วย passkey เดิม = แทนที่ ไม่เพิ่มแถว
    assert len(_bind(client, h, cid, auth, wrapped=bytes_to_base64url(os.urandom(40))).json()["passkeys"]) == 1


def test_bind_rejects_other_users_passkey_and_certificate(client, make_user):
    _, owner = make_user()
    _, other = make_user()
    cid = _upload_cert(client, owner).json()["id"]
    auth_other = SoftAuthenticator()
    assert _register(client, other, auth_other).status_code == 200
    assert client.post(f"/signature/certificates/{cid}/passkeys/options", headers=other).status_code == 404

    assert _register(client, owner, SoftAuthenticator()).status_code == 200
    opts = client.post(f"/signature/certificates/{cid}/passkeys/options", headers=owner).json()
    r = client.post(f"/signature/certificates/{cid}/passkeys", headers=owner, json={
        "flow_id": opts["flow_id"], "credential": auth_other.get(opts["options"]), "password": PW,
        "prf_salt": SALT, "wrapped": WRAPPED})
    assert r.status_code == 400 and "ไม่ใช่ของบัญชี" in r.json()["detail"]


def test_unbind_and_cascades(client, make_user):
    uid, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    a1, a2 = SoftAuthenticator(), SoftAuthenticator()
    assert _register(client, h, a1, "Mac").status_code == 200
    assert _register(client, h, a2, "iPhone").status_code == 200
    _bind(client, h, cid, a1)
    bindings = _bind(client, h, cid, a2).json()["passkeys"]
    assert [b["name"] for b in bindings] == ["Mac", "iPhone"]

    # เลิกผูกทีละอัน
    r = client.delete(f"/signature/certificates/{cid}/passkeys/{bindings[0]['id']}", headers=h)
    assert r.status_code == 200 and [b["name"] for b in r.json()["passkeys"]] == ["iPhone"]

    # ลบ passkey ออกจากบัญชี → การผูกหายด้วย
    pk_id = next(p["id"] for p in client.get("/auth/passkeys", headers=h).json()["passkeys"] if p["name"] == "iPhone")
    assert client.delete(f"/auth/passkeys/{pk_id}", headers=h).status_code == 200
    assert client.get("/signature/certificates", headers=h).json()[0]["passkeys"] == []

    # ลบใบรับรอง → การผูกหายด้วย
    _bind(client, h, cid, a1)
    assert client.post(f"/signature/certificates/{cid}/delete", headers=h, json={"password": PW}).status_code == 204
    db = SessionLocal()
    try:
        assert db.query(CertificatePasskey).filter(CertificatePasskey.certificate_id == cid).count() == 0
    finally:
        db.close()


def test_account_deletion_removes_passkey_bindings(client, make_user):
    from tests.test_account_deletion import _delete

    _, h = make_user()
    cid = _upload_cert(client, h).json()["id"]
    auth = SoftAuthenticator()
    assert _register(client, h, auth).status_code == 200
    assert _bind(client, h, cid, auth).status_code == 201
    assert _delete(client, h).status_code == 200
    db = SessionLocal()
    try:
        assert db.query(CertificatePasskey).filter(CertificatePasskey.certificate_id == cid).count() == 0
    finally:
        db.close()
