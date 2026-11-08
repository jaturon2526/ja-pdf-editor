"""แจ้งเตือนการลงนามทาง LINE: ผูกบัญชีด้วยรหัสผ่าน webhook, ส่งแทนอีเมล, fallback, โควตา"""
import base64
import hashlib
import hmac
import json

import pytest

from app.core.config import settings
from app.services import line_service, mailer
from tests.test_signing import _email, _sign_electronic
from tests.test_signing_notifications import _create, _to

SECRET = "s" * 32


class FakeLine:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.fail_status: int | None = None

    def __call__(self, method, path, body=None, timeout=10):
        self.calls.append((method, path, body))
        if path.startswith("/v2/bot/profile/"):
            return {"displayName": "คุณทดสอบ"}
        if path == "/v2/bot/message/push" and self.fail_status is not None:
            raise line_service.LineApiError(self.fail_status, "fail")
        return {}

    def pushes(self, to=None):
        return [b for m, p, b in self.calls if p == "/v2/bot/message/push" and (to is None or b["to"] == to)]

    def replies(self):
        return [b["messages"][0]["text"] for m, p, b in self.calls if p == "/v2/bot/message/reply"]


@pytest.fixture
def line(monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", SECRET)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "t" * 171)
    monkeypatch.setattr(settings, "LINE_OA_BASIC_ID", "@227hmohv")
    monkeypatch.setattr(settings, "LINE_MONTHLY_LIMIT", 280)
    fake = FakeLine()
    monkeypatch.setattr(line_service, "call_api", fake)
    monkeypatch.setattr(line_service, "run", lambda fn: fn())
    line_service.reset_for_testing()
    yield fake
    line_service.reset_for_testing()


@pytest.fixture
def outbox(monkeypatch):
    sent: list[mailer.Mail] = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


def _sig(body: bytes) -> str:
    return base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()


def _webhook(client, events, signature=None):
    body = json.dumps({"destination": "U0", "events": events}).encode()
    return client.post("/line/webhook", content=body,
                       headers={"X-Line-Signature": signature if signature is not None else _sig(body),
                                "Content-Type": "application/json"})


def _text(line_user_id, text, token="rt"):
    return {"type": "message", "replyToken": token, "source": {"type": "user", "userId": line_user_id},
            "message": {"type": "text", "id": "1", "text": text}}


def _link(client, headers, line_user_id):
    r = client.post("/line/link-code", headers=headers)
    assert r.status_code == 200, r.text
    assert _webhook(client, [_text(line_user_id, r.json()["code"])]).status_code == 200
    assert client.get("/line/status", headers=headers).json()["linked"] is True


def test_disabled_without_config(client, make_user):
    _, h = make_user()
    s = client.get("/line/status", headers=h).json()
    assert s["enabled"] is False and s["linked"] is False
    assert client.post("/line/link-code", headers=h).status_code == 503
    assert client.post("/line/webhook", content=b"{}").status_code == 503


def test_webhook_rejects_bad_signature_and_accepts_verify(client, line):
    assert _webhook(client, [], signature="bad").status_code == 401
    assert _webhook(client, [], signature="").status_code == 401
    assert _webhook(client, []).status_code == 200  # ปุ่ม Verify ใน console ส่ง events ว่าง


def test_link_with_code_then_unlink(client, make_user, line):
    _, h = make_user()
    r = client.post("/line/link-code", headers=h).json()
    assert r["code"].startswith("JA-") and len(r["code"]) == 9
    assert r["chat_url"].startswith("https://line.me/R/oaMessage/%40227hmohv/?JA-")
    assert r["qr_svg"].startswith("data:image/svg+xml")

    # follow → ตอบวิธีใช้ (reply ฟรี)
    assert _webhook(client, [{"type": "follow", "replyToken": "r0", "source": {"type": "user", "userId": "Uaaa"}}]).status_code == 200
    assert "เชื่อมต่อ LINE" in line.replies()[-1]

    # พิมพ์ตัวพิมพ์เล็ก/ไม่มีขีดก็ได้
    assert _webhook(client, [_text("Uaaa", "รหัส " + r["code"].lower().replace("-", ""))]).status_code == 200
    assert "เรียบร้อยแล้ว" in line.replies()[-1]
    s = client.get("/line/status", headers=h).json()
    assert s["linked"] and s["display_name"] == "คุณทดสอบ" and s["notifications"]

    # รหัสใช้ได้ครั้งเดียว
    _webhook(client, [_text("Ubbb", r["code"])])
    assert "ไม่ถูกต้องหรือหมดอายุ" in line.replies()[-1]

    assert client.put("/line/preferences", headers=h, json={"notifications": False}).json()["notifications"] is False
    assert client.delete("/line/link", headers=h).json()["linked"] is False


def test_failed_codes_are_rate_limited(client, line):
    for _ in range(line_service.MAX_FAILED_CODES_PER_HOUR):
        _webhook(client, [_text("Uspam", "JA-AAAAAA")])
    _webhook(client, [_text("Uspam", "JA-BBBBBB")])
    assert "หลายครั้งเกินไป" in line.replies()[-1]


def test_same_line_account_moves_to_new_user_and_unfollow_unlinks(client, make_user, line):
    _, a = make_user()
    _, b = make_user()
    _link(client, a, "Ushared")
    _link(client, b, "Ushared")
    assert client.get("/line/status", headers=a).json()["linked"] is False
    _webhook(client, [{"type": "unfollow", "source": {"type": "user", "userId": "Ushared"}}])
    assert client.get("/line/status", headers=b).json()["linked"] is False


def test_signing_notifications_go_to_line_instead_of_email(client, make_user, upload, line, outbox):
    _, owner = make_user()
    signers = [make_user()[1] for _ in range(2)]
    _link(client, owner, "Uowner")
    _link(client, signers[0], "Us1")
    r = _create(client, owner, signers, upload)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    # ผู้ลงนามคนแรกได้ LINE (ไม่ได้อีเมล) ปุ่มลิงก์ไปหน้าคำขอ
    pushes = line.pushes("Us1")
    assert len(pushes) == 1 and not _to(outbox, client, signers[0])
    msg = pushes[0]["messages"][0]
    assert msg["type"] == "flex" and msg["altText"].startswith("ถึงคิวคุณลงนาม")
    assert msg["contents"]["footer"]["contents"][0]["action"]["uri"].endswith(f"/signing/{rid}")

    assert _sign_electronic(client, signers[0], rid).status_code == 200
    assert _to(outbox, client, signers[1])  # คนที่ไม่ได้ผูก LINE ยังได้อีเมลตามเดิม
    assert not line.pushes("Uowner")  # ความคืบหน้า → ในระบบอย่างเดียว

    line.calls.clear()
    outbox.clear()
    assert _sign_electronic(client, signers[1], rid).status_code == 200
    assert [p["messages"][0]["altText"] for p in line.pushes("Uowner")] == ["\"Memo\" ลงนามครบทุกคนแล้ว"]
    assert not line.pushes("Us1")  # ลงนามครบ → LINE เฉพาะผู้ส่ง
    assert not _to(outbox, client, owner) and not _to(outbox, client, signers[0])
    assert _to(outbox, client, signers[1])  # ไม่ได้ผูก LINE → อีเมลตามเดิม


def test_line_failure_and_quota_fall_back_to_email(client, make_user, upload, line, outbox, monkeypatch):
    _, owner = make_user()
    _, signer = make_user()
    _link(client, signer, "Ufail")

    line.fail_status = 500
    assert _create(client, owner, [signer], upload).status_code == 200
    assert len(line.pushes("Ufail")) == 1
    assert len(_to(outbox, client, signer)) == 1  # LINE ล้ม → อีเมลแทน
    assert line_service.pushes_this_month() == 0  # ส่งไม่สำเร็จไม่นับ

    line.fail_status = None
    outbox.clear()
    monkeypatch.setattr(settings, "LINE_MONTHLY_LIMIT", 1)
    assert _create(client, owner, [signer], upload).status_code == 200
    assert line_service.pushes_this_month() == 1 and not _to(outbox, client, signer)
    line.calls.clear()
    assert _create(client, owner, [signer], upload).status_code == 200
    assert not line.pushes() and len(_to(outbox, client, signer)) == 1  # โควตาเต็ม → อีเมล

    # 429 จาก LINE = โควตาหมด
    monkeypatch.setattr(settings, "LINE_MONTHLY_LIMIT", 280)
    line.fail_status = 429
    outbox.clear()
    assert _create(client, owner, [signer], upload).status_code == 200
    assert line_service.pushes_this_month() == 280 and len(_to(outbox, client, signer)) == 1


def test_line_off_uses_email_and_admin_sees_quota(client, make_user, upload, line, outbox):
    _, owner = make_user()
    _, signer = make_user()
    _link(client, signer, "Uoff")
    client.put("/line/preferences", headers=signer, json={"notifications": False})
    assert _create(client, owner, [signer], upload).status_code == 200
    assert not line.pushes() and len(_to(outbox, client, signer)) == 1
    assert "quota" not in client.get("/line/status", headers=signer).json()

    from app.db.database import SessionLocal
    from app.models.domain import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == _email(client, owner)).one()
        u.is_admin = True
        db.commit()
    finally:
        db.close()
    assert client.get("/line/status", headers=owner).json()["quota"] == {"used": 0, "limit": 280}
