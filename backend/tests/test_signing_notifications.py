"""เฟส 2: อีเมลแจ้งเตือนการลงนาม, ปุ่มส่งเตือน, วันครบกำหนด และการปิดรับอีเมล"""
import datetime as dt
from email.utils import parseaddr

import pytest

from app.core.config import settings
from app.services import mailer
from tests.conftest import make_pdf_bytes
from tests.test_signing import _email, _file_id, _sign_electronic


@pytest.fixture
def outbox(monkeypatch):
    sent: list[mailer.Mail] = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


def _create(client, owner, signers, upload, **extra):
    sid = upload(owner, make_pdf_bytes(pages=1, text="Memo"))
    steps = [
        {"email": _email(client, h), "sign_type": "electronic", "page": 0,
         "x0": 50 + i * 170, "y0": 600, "x1": 200 + i * 170, "y1": 660}
        for i, h in enumerate(signers)
    ]
    return client.post("/signing/requests", headers=owner,
                       json={"file_id": _file_id(client, owner, sid), "title": "Memo", "steps": steps, **extra})


@pytest.fixture
def two_signers(client, make_user, upload, outbox):
    _, owner = make_user()
    signers = [make_user()[1] for _ in range(2)]
    r = _create(client, owner, signers, upload)
    assert r.status_code == 200, r.text
    return owner, signers, r.json()["id"]


def _to(outbox, client, headers):
    email = _email(client, headers)
    return [m for m in outbox if m.to == email]


def test_turn_emails_follow_the_sequence_and_completion(client, two_signers, outbox):
    owner, signers, rid = two_signers
    owner_email = _email(client, owner)

    first = _to(outbox, client, signers[0])
    assert len(first) == 1 and first[0].subject.startswith("ถึงคิวคุณลงนาม")
    assert first[0].reply_to == owner_email  # ตอบกลับถึงผู้ส่งตัวจริง
    assert f"/signing/{rid}" in first[0].text and f"/signing/{rid}" in first[0].html
    msg = mailer.build_message(first[0])
    display, address = parseaddr(str(msg["From"]))
    assert display.endswith(f"ผ่าน {settings.APP_NAME}")
    assert msg["Reply-To"] == owner_email
    assert not _to(outbox, client, signers[1])  # ยังไม่ถึงคิว

    outbox.clear()
    assert _sign_electronic(client, signers[0], rid).status_code == 200
    assert [m.subject for m in _to(outbox, client, signers[1])] == ["ถึงคิวคุณลงนาม: Memo"]
    assert not _to(outbox, client, owner)  # ความคืบหน้าระหว่างทาง → แจ้งในระบบอย่างเดียว

    outbox.clear()
    assert _sign_electronic(client, signers[1], rid).status_code == 200
    done = _to(outbox, client, owner)
    assert len(done) == 1 and done[0].subject.startswith("ลงนามครบทุกคนแล้ว")
    assert done[0].reply_to == _email(client, signers[1])


def test_reject_and_cancel_emails(client, make_user, upload, outbox):
    _, owner = make_user()
    signers = [make_user()[1] for _ in range(2)]
    rid = _create(client, owner, signers, upload).json()["id"]
    outbox.clear()
    r = client.post(f"/signing/requests/{rid}/reject", headers=signers[0], json={"reason": "ตัวเลขผิด"})
    assert r.status_code == 200
    rejected = _to(outbox, client, owner)
    assert len(rejected) == 1 and rejected[0].subject.startswith("มีผู้ปฏิเสธ")
    assert "ตัวเลขผิด" in rejected[0].text

    rid2 = _create(client, owner, signers, upload).json()["id"]
    outbox.clear()
    assert client.post(f"/signing/requests/{rid2}/cancel", headers=owner).status_code == 200
    cancelled = _to(outbox, client, signers[0])
    assert len(cancelled) == 1 and cancelled[0].subject.startswith("ยกเลิกคำขอลงนาม")


def test_email_opt_out_keeps_in_app_notifications(client, make_user, upload, outbox):
    _, owner = make_user()
    _, signer = make_user()
    assert client.get("/signing/preferences", headers=signer).json() == {"email_notifications": True}
    r = client.put("/signing/preferences", headers=signer, json={"email_notifications": False})
    assert r.json() == {"email_notifications": False}

    rid = _create(client, owner, [signer], upload).json()["id"]
    assert not _to(outbox, client, signer)
    items = client.get("/notifications", headers=signer).json()["items"]
    assert any(n["request_id"] == rid and n["kind"] == "sign_turn" for n in items)


def test_remind_is_owner_only_and_rate_limited(client, two_signers, outbox):
    owner, signers, rid = two_signers
    outbox.clear()
    assert client.post(f"/signing/requests/{rid}/remind", headers=signers[0]).status_code == 403

    r = client.post(f"/signing/requests/{rid}/remind", headers=owner)
    assert r.status_code == 200, r.text
    reminders = _to(outbox, client, signers[0])
    assert len(reminders) == 1 and reminders[0].subject.startswith("เตือน")

    again = client.post(f"/signing/requests/{rid}/remind", headers=owner)
    assert again.status_code == 429 and "นาที" in again.json()["detail"]
    data = client.get(f"/signing/requests/{rid}", headers=owner).json()
    assert data["last_reminded_at"] is not None
    assert any(e["action"] == "reminded" for e in data["events"])


def test_due_date_validation_and_serialization(client, make_user, upload, outbox):
    _, owner = make_user()
    _, signer = make_user()
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
    r = _create(client, owner, [signer], upload, due_at=past)
    assert r.status_code == 400 and "อนาคต" in r.json()["detail"]

    due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)
    r = _create(client, owner, [signer], upload, due_at=due.isoformat())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["due_at"] is not None and data["overdue"] is False
    turn = _to(outbox, client, signer)[-1]
    assert "ครบกำหนด" in turn.text


def test_due_soon_and_overdue_reminders_are_sent_once(client, make_user, upload, outbox):
    from app.db.database import SessionLocal
    from app.models.domain import SigningRequest
    from app.services import signing_service

    _, owner = make_user()
    _, signer = make_user()
    due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)
    rid = _create(client, owner, [signer], upload, due_at=due.isoformat()).json()["id"]
    outbox.clear()

    def run(now):
        db = SessionLocal()
        try:
            signing_service.process_due_dates(db, now=now)
        finally:
            db.close()

    run(dt.datetime.now(dt.timezone.utc))  # ยังไกล → ไม่มีอะไร
    assert not [m for m in outbox if f"/signing/{rid}" in m.text]

    soon = due - dt.timedelta(hours=2)
    run(soon)
    run(soon)
    mine = [m for m in outbox if f"/signing/{rid}" in m.text]
    assert [m.to for m in mine] == [_email(client, signer)]
    assert "ใกล้ครบกำหนด" in mine[0].text

    outbox.clear()
    late = due + dt.timedelta(hours=1)
    run(late)
    run(late)
    mine = [m for m in outbox if f"/signing/{rid}" in m.text]
    assert sorted(m.subject.split(":")[0] for m in mine) == sorted(["เลยกำหนดลงนาม", "เตือน"])
    owner_mail = next(m for m in mine if m.to == _email(client, owner))
    assert owner_mail.subject.startswith("เลยกำหนดลงนาม")

    db = SessionLocal()
    try:
        sr = db.get(SigningRequest, rid)
        assert sr.overdue_notified_at is not None and sr.due_soon_notified_at is not None
    finally:
        db.close()


def test_turn_close_to_due_date_skips_immediate_due_soon(client, make_user, upload, outbox):
    from app.db.database import SessionLocal
    from app.services import signing_service

    _, owner = make_user()
    _, signer = make_user()
    due = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)
    rid = _create(client, owner, [signer], upload, due_at=due.isoformat()).json()["id"]
    outbox.clear()
    db = SessionLocal()
    try:
        signing_service.process_due_dates(db)
    finally:
        db.close()
    assert not [m for m in outbox if f"/signing/{rid}" in m.text]  # อีเมล "ถึงคิว" บอกวันครบกำหนดไปแล้ว


def test_mailer_simulates_without_smtp(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMTP_USERNAME", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    caplog.set_level("INFO", logger="mailer")
    ok = mailer._send_now(mailer.Mail(to="a@example.com", subject="ทดสอบ", text="hi", html="<p>hi</p>"))
    assert ok is False and "[EMAIL SIMULATION]" in caplog.text
