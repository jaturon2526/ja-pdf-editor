"""ลบบัญชีผู้ใช้: ยืนยันตัวตน, ไฟล์/ข้อมูลถูกลบ, คำขอลงนามที่ส่งเอง/ที่เป็นผู้ลงนามให้คนอื่น, แอดมินคนสุดท้าย"""
import pytest

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.domain import FileRecord, SigningRequest, SigningStep, User
from app.services import file_storage, mailer
from tests.test_signing import _email, _sign_electronic
from tests.test_signing_notifications import _create


@pytest.fixture
def outbox(monkeypatch):
    sent: list[mailer.Mail] = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


def _delete(client, headers, email=None, password="password123"):
    return client.post("/auth/account/delete", headers=headers,
                       json={"confirm_email": email if email is not None else _email(client, headers), "password": password})


def _user_id(headers, client):
    return client.get("/auth/me", headers=headers).json()["id"]


def test_requires_matching_email_and_password(client, make_user):
    _, h = make_user()
    assert _delete(client, h, email="someone@else.com").status_code == 400
    assert _delete(client, h, password="wrong").status_code == 400
    assert client.get("/auth/me", headers=h).status_code == 200  # ยังอยู่


def test_deletes_files_and_account(client, make_user, upload, outbox):
    uid, h = make_user()
    email = _email(client, h)
    sid = upload(h)
    with SessionLocal() as db:
        record = db.query(FileRecord).filter_by(user_id=uid).one()
        paths = file_storage.all_existing_paths(record)
    assert paths
    fonts_dir = settings.UPLOAD_DIR / "users" / str(uid) / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    (fonts_dir / "x.ttf").write_bytes(b"font")

    s = client.get("/auth/account/deletion-summary", headers=h).json()
    assert s["files"] == 1 and s["email"] == email and s["is_last_admin"] is False

    r = _delete(client, h)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    assert all(not p.exists() for p in paths)
    assert not fonts_dir.exists()
    with SessionLocal() as db:
        assert db.get(User, uid) is None
        assert db.query(FileRecord).filter_by(user_id=uid).count() == 0
    assert client.get("/auth/me", headers=h).status_code == 401
    assert client.post("/auth/login", data={"username": email, "password": "password123"}).status_code == 401
    assert client.get(f"/pdf/{sid}/info", headers=h).status_code in (401, 404)
    assert any(m.to == email and "ถูกลบแล้ว" in m.subject for m in outbox)


def test_owner_requests_are_cancelled_and_removed(client, make_user, upload, outbox):
    uid, owner = make_user()
    _, signer = make_user()
    rid = _create(client, owner, [signer], upload).json()["id"]
    outbox.clear()
    assert _delete(client, owner).status_code == 200
    signer_email = _email(client, signer)
    assert any(m.to == signer_email and m.subject.startswith("ยกเลิกคำขอลงนาม") for m in outbox)
    with SessionLocal() as db:
        assert db.get(SigningRequest, rid) is None
        assert db.query(SigningStep).filter_by(request_id=rid).count() == 0
    assert client.get(f"/signing/requests/{rid}", headers=signer).status_code == 404
    # แจ้งเตือนในระบบของผู้ลงนามยังอยู่ (ไม่หายไปพร้อมคำขอ)
    titles = [n["title"] for n in client.get("/notifications", headers=signer).json()["items"]]
    assert any("ยกเลิกคำขอลงนาม" in t for t in titles)


def test_pending_signer_rejects_and_signed_history_is_kept(client, make_user, upload, outbox):
    _, owner = make_user()
    sid1, signer1 = make_user()
    _, signer2 = make_user()
    signer1_email = _email(client, signer1)
    rid = _create(client, owner, [signer1, signer2], upload).json()["id"]
    assert _sign_electronic(client, signer1, rid).status_code == 200  # signer1 ลงนามแล้ว
    pending = _create(client, owner, [signer2, signer1], upload).json()["id"]  # signer1 ยังไม่ถึงคิว

    s = client.get("/auth/account/deletion-summary", headers=signer1).json()
    assert s["pending_as_signer"] == 1 and s["signed_for_others"] == 1
    outbox.clear()
    assert _delete(client, signer1).status_code == 200

    owner_email = _email(client, owner)
    data = client.get(f"/signing/requests/{pending}", headers=owner).json()
    assert data["status"] == "rejected"
    assert any(m.to == owner_email and "ปฏิเสธ" in m.subject for m in outbox)

    done = client.get(f"/signing/requests/{rid}", headers=owner).json()
    step = next(st for st in done["steps"] if st["order"] == 1)
    assert step["status"] == "signed" and step["signer"]["deleted"] is True
    assert signer1_email in step["signer"]["name"] and "ลบบัญชีแล้ว" in step["signer"]["name"]
    with SessionLocal() as db:
        assert db.query(SigningStep).filter_by(signer_user_id=sid1).count() == 0

    # คำขอเดิมยังลงนามต่อจนครบได้ และหนังสือรับรองยังมีชื่อผู้ลงนามที่ลบบัญชีไป
    assert _sign_electronic(client, signer2, rid).status_code == 200
    ev = client.get(f"/signing/requests/{rid}/evidence", headers=owner)
    assert ev.status_code == 200 and ev.content[:4] == b"%PDF"


def test_last_admin_cannot_delete(client, make_user):
    with SessionLocal() as db:
        for u in db.query(User).filter(User.is_admin.is_(True)).all():
            u.is_admin = False
        db.commit()
    uid, h = make_user()
    with SessionLocal() as db:
        db.get(User, uid).is_admin = True
        db.commit()
    assert client.get("/auth/account/deletion-summary", headers=h).json()["is_last_admin"] is True
    r = _delete(client, h)
    assert r.status_code == 409 and "ผู้ดูแลระบบคนสุดท้าย" in r.json()["detail"]
    with SessionLocal() as db:
        db.get(User, uid).is_admin = False
        db.commit()


def test_passkey_options_need_a_passkey(client, make_user):
    _, h = make_user()
    r = client.post("/auth/account/delete/passkey-options", headers=h)
    assert r.status_code == 400 and "passkey" in r.json()["detail"]
