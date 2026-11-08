"""Passkey (WebAuthn) — ลงทะเบียน / เข้าสู่ระบบ / จัดการ ด้วย authenticator จำลอง (ES256, attestation "none")"""
import hashlib
import json
import os
import struct

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url

from app.services import passkey_service

ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def _rp(monkeypatch):
    monkeypatch.setattr(passkey_service.settings, "WEBAUTHN_RP_ID", "localhost")
    monkeypatch.setattr(passkey_service.settings, "WEBAUTHN_ORIGINS", ORIGIN)


class SoftAuthenticator:
    """authenticator จำลองแบบ platform passkey (discoverable, user verification)"""

    def __init__(self, rp_id="localhost", origin=ORIGIN):
        self.rp_id = rp_id
        self.origin = origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(32)
        self.user_handle = None
        self.count = 0

    def _auth_data(self, flags, attested=b""):
        return hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", self.count) + attested

    def _client_data(self, typ, challenge):
        return json.dumps({"type": typ, "challenge": challenge, "origin": self.origin, "crossOrigin": False}).encode()

    def create(self, options):
        self.user_handle = options["user"]["id"]
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        attested = b"\x00" * 16 + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose
        auth_data = self._auth_data(0x01 | 0x04 | 0x08 | 0x10 | 0x40, attested)  # UP UV BE BS AT
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cid = bytes_to_base64url(self.cred_id)
        return {
            "id": cid, "rawId": cid, "type": "public-key", "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(self._client_data("webauthn.create", options["challenge"])),
                "attestationObject": bytes_to_base64url(att),
                "transports": ["internal", "hybrid"],
            },
        }

    def get(self, options, user_handle=None):
        self.count += 1
        auth_data = self._auth_data(0x01 | 0x04 | 0x08 | 0x10)
        client = self._client_data("webauthn.get", options["challenge"])
        sig = self.key.sign(auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        cid = bytes_to_base64url(self.cred_id)
        return {
            "id": cid, "rawId": cid, "type": "public-key", "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(client),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(sig),
                "userHandle": user_handle if user_handle is not None else self.user_handle,
            },
        }


def _register(client, headers, auth, name="MacBook"):
    opts = client.post("/auth/passkeys/register/options", headers=headers)
    assert opts.status_code == 200, opts.text
    body = opts.json()
    assert body["options"]["rp"]["id"] == "localhost"
    assert body["options"]["authenticatorSelection"]["residentKey"] == "required"
    return client.post("/auth/passkeys/register/verify", headers=headers,
                       json={"flow_id": body["flow_id"], "credential": auth.create(body["options"]), "name": name})


def _login(client, auth, **kw):
    body = client.post("/auth/passkeys/login/options").json()
    assert "allowCredentials" not in body["options"] or body["options"]["allowCredentials"] == []
    return client.post("/auth/passkeys/login/verify", json={"flow_id": body["flow_id"], "credential": auth.get(body["options"], **kw)})


def test_register_then_login_issues_token(client, make_user):
    uid, headers = make_user()
    auth = SoftAuthenticator()
    r = _register(client, headers, auth)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "MacBook" and r.json()["backed_up"] is True

    r = _login(client, auth)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["id"] == uid
    listed = client.get("/auth/passkeys", headers=headers).json()["passkeys"]
    assert len(listed) == 1 and listed[0]["last_used_at"]


def test_challenge_is_single_use(client, make_user):
    _, headers = make_user()
    auth = SoftAuthenticator()
    assert _register(client, headers, auth).status_code == 200
    body = client.post("/auth/passkeys/login/options").json()
    payload = {"flow_id": body["flow_id"], "credential": auth.get(body["options"])}
    assert client.post("/auth/passkeys/login/verify", json=payload).status_code == 200
    replay = client.post("/auth/passkeys/login/verify", json=payload)
    assert replay.status_code == 401 and "หมดอายุ" in replay.json()["detail"]


def test_wrong_origin_is_rejected(client, make_user):
    _, headers = make_user()
    evil = SoftAuthenticator(origin="https://evil.example")
    r = _register(client, headers, evil)
    assert r.status_code == 400


def test_signature_from_other_key_is_rejected(client, make_user):
    _, headers = make_user()
    auth = SoftAuthenticator()
    assert _register(client, headers, auth).status_code == 200
    auth.key = ec.generate_private_key(ec.SECP256R1())  # คนอื่นปลอม credential id เดิม
    assert _login(client, auth).status_code == 401


def test_user_handle_mismatch_is_rejected(client, make_user):
    _, headers = make_user()
    auth = SoftAuthenticator()
    assert _register(client, headers, auth).status_code == 200
    assert _login(client, auth, user_handle=bytes_to_base64url(b"x" * 32)).status_code == 401


def test_same_user_handle_for_all_passkeys(client, make_user):
    _, headers = make_user()
    a, b = SoftAuthenticator(), SoftAuthenticator()
    assert _register(client, headers, a, "iPhone").status_code == 200
    opts = client.post("/auth/passkeys/register/options", headers=headers).json()["options"]
    assert opts["user"]["id"] == a.user_handle
    assert [c["id"] for c in opts["excludeCredentials"]] == [bytes_to_base64url(a.cred_id)]
    assert _register(client, headers, b, "Mac").status_code == 200


def test_rename_and_delete_only_own(client, make_user):
    _, owner = make_user()
    _, other = make_user()
    auth = SoftAuthenticator()
    pid = _register(client, owner, auth).json()["id"]
    assert client.patch(f"/auth/passkeys/{pid}", headers=other, json={"name": "x"}).status_code == 404
    assert client.delete(f"/auth/passkeys/{pid}", headers=other).status_code == 404
    r = client.patch(f"/auth/passkeys/{pid}", headers=owner, json={"name": "  Mac   ที่ทำงาน "})
    assert r.json()["name"] == "Mac ที่ทำงาน"
    assert client.delete(f"/auth/passkeys/{pid}", headers=owner).status_code == 200
    assert client.get("/auth/passkeys", headers=owner).json()["passkeys"] == []
    # ลบแล้วเข้าสู่ระบบไม่ได้
    r = _login(client, auth)
    assert r.status_code == 401 and "ไม่พบ passkey" in r.json()["detail"]


def test_inactive_user_cannot_login(client, make_user):
    from app.db.database import SessionLocal
    from app.models.domain import User

    uid, headers = make_user()
    auth = SoftAuthenticator()
    assert _register(client, headers, auth).status_code == 200
    db = SessionLocal()
    try:
        db.query(User).filter(User.id == uid).update({"is_active": False})
        db.commit()
    finally:
        db.close()
    assert _login(client, auth).status_code == 401


def test_endpoints_require_login(client):
    assert client.get("/auth/passkeys").status_code == 401
    assert client.post("/auth/passkeys/register/options").status_code == 401
    assert client.post("/auth/passkeys/login/options").status_code == 200


def test_rp_id_and_origins_follow_frontend_url(monkeypatch):
    s = passkey_service.settings
    monkeypatch.setattr(s, "WEBAUTHN_RP_ID", "")
    monkeypatch.setattr(s, "WEBAUTHN_ORIGINS", "")
    monkeypatch.setattr(s, "FRONTEND_URL", "https://ja-pdf.com/")
    monkeypatch.setattr(s, "ALLOWED_ORIGINS", ["https://ja-pdf.com", "https://www.ja-pdf.com"])
    assert passkey_service.rp_id() == "ja-pdf.com"
    assert passkey_service.expected_origins() == ["https://ja-pdf.com", "https://www.ja-pdf.com"]


def test_localhost_accepts_any_port_but_not_other_hosts(client, make_user, monkeypatch):
    """dev/CI: FRONTEND_URL เป็นพอร์ตหนึ่ง แต่หน้าเว็บเปิดจากอีกพอร์ต (เช่น nginx 8080) ต้องใช้ได้"""
    monkeypatch.setattr(passkey_service.settings, "WEBAUTHN_ORIGINS", "http://localhost:5173")
    _, headers = make_user()
    auth = SoftAuthenticator(origin="http://localhost:8080")
    assert _register(client, headers, auth).status_code == 200
    assert _login(client, auth).status_code == 200
    _, other = make_user()
    assert _register(client, other, SoftAuthenticator(origin="http://localhost.evil.com:8080")).status_code == 400


def test_production_rp_does_not_accept_localhost(monkeypatch):
    monkeypatch.setattr(passkey_service.settings, "WEBAUTHN_RP_ID", "ja-pdf.com")
    monkeypatch.setattr(passkey_service.settings, "WEBAUTHN_ORIGINS", "https://ja-pdf.com")
    import base64
    import json as _json
    cdj = base64.urlsafe_b64encode(_json.dumps({"origin": "http://localhost:8080"}).encode()).decode().rstrip("=")
    assert passkey_service._origins_for({"response": {"clientDataJSON": cdj}}) == ["https://ja-pdf.com"]
