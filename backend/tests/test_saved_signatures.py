"""Tests for Saved Signature Images protected by Passkey (v1.48.0)."""
import base64

from app.db.database import SessionLocal
from app.models.domain import Passkey
from app.services import passkey_service


def _seed_passkey(user_id: int, name: str = "MacBook Touch ID") -> Passkey:
    db = SessionLocal()
    try:
        cred_id = base64.urlsafe_b64encode(f"cred-{user_id}-{name}".encode("utf-8")).decode("ascii").rstrip("=")
        pk = Passkey(
            user_id=user_id,
            credential_id=cred_id,
            public_key=b"\x01\x02\x03\x04",
            sign_count=0,
            user_handle=f"handle-{user_id}",
            transports="internal,hybrid",
            name=name,
        )
        db.add(pk)
        db.commit()
        db.refresh(pk)
        return pk
    finally:
        db.close()


def test_saved_signatures_crud_and_isolation(client, make_user, monkeypatch):
    u1, h1 = make_user("sig1@example.com")
    _u2, h2 = make_user("sig2@example.com")

    # Initially empty
    assert client.get("/signature/saved", headers=h1).json() == []
    # Options fails when user has no passkey
    assert client.post("/signature/saved/options", headers=h1).status_code == 400

    pk = _seed_passkey(u1)
    r_opt = client.post("/signature/saved/options", headers=h1)
    assert r_opt.status_code == 200, r_opt.text
    flow_id = r_opt.json()["flow_id"]

    monkeypatch.setattr(passkey_service, "verify_for_user", lambda db, user, purpose, fid, cred: pk)

    fake_cipher = base64.b64encode(b"0123456789ab" + b"encrypted-png-payload-bytes-1234").decode("ascii")
    r_create = client.post(
        "/signature/saved",
        json={
            "label": "ลายเซ็นทางการ",
            "prf_salt": "aB12cD34eF56gH78iJ90kL12mN34oP56qR78sT90uVw",  # pragma: allowlist secret
            "encrypted_png_b64": fake_cipher,
            "flow_id": flow_id,
            "credential": {"id": pk.credential_id},
        },
        headers=h1,
    )
    assert r_create.status_code == 201, r_create.text
    created = r_create.json()
    assert created["label"] == "ลายเซ็นทางการ"
    assert created["passkey_name"] == "MacBook Touch ID"
    assert "encrypted_png_b64" not in created

    # List returns metadata only
    listed = client.get("/signature/saved", headers=h1).json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    # Get blob returns ciphertext for owner, 404 for other user
    r_blob = client.get(f"/signature/saved/{created['id']}/blob", headers=h1)
    assert r_blob.status_code == 200
    assert r_blob.json()["encrypted_png_b64"] == fake_cipher
    assert client.get(f"/signature/saved/{created['id']}/blob", headers=h2).status_code == 404

    # Other user cannot delete
    assert client.delete(f"/signature/saved/{created['id']}", headers=h2).status_code == 404

    # Owner deletes
    assert client.delete(f"/signature/saved/{created['id']}", headers=h1).status_code == 204
    assert client.get("/signature/saved", headers=h1).json() == []


def test_saved_signature_validation(client, make_user, monkeypatch):
    u, h = make_user("sigval@example.com")
    pk = _seed_passkey(u)
    monkeypatch.setattr(passkey_service, "verify_for_user", lambda db, user, purpose, fid, cred: pk)

    # Invalid salt
    r_bad_salt = client.post(
        "/signature/saved",
        json={
            "label": "bad",
            "prf_salt": "short",
            "encrypted_png_b64": base64.b64encode(b"x" * 64).decode("ascii"),
            "flow_id": "f1",
            "credential": {"id": pk.credential_id},
        },
        headers=h,
    )
    assert r_bad_salt.status_code == 400

    # Too-short ciphertext (< 28 bytes = 12 IV + 16 GCM tag)
    r_short = client.post(
        "/signature/saved",
        json={
            "label": "short",
            "prf_salt": "aB12cD34eF56gH78iJ90kL12mN34oP56qR78sT90uVw",  # pragma: allowlist secret
            "encrypted_png_b64": base64.b64encode(b"tiny").decode("ascii"),
            "flow_id": "f1",
            "credential": {"id": pk.credential_id},
        },
        headers=h,
    )
    assert r_short.status_code == 400
