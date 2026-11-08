"""เข้าสู่ระบบด้วย LINE: สร้าง/เข้าบัญชีจากอีเมลของ LINE, ไม่มีอีเมล → ยืนยันอีเมล, เชื่อมจากหน้าความปลอดภัย, ผูกแจ้งเตือน"""
import itertools
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.domain import User
from app.services import email_service, line_login_service, line_service

_seq = itertools.count(1)


class FakeLineLogin:
    def __init__(self):
        self.profile = {}
        self.friend = False
        self.verify_nonce = None
        self.fail_token = False
        self.calls = []

    def __call__(self, method, url, form=None, bearer=None, timeout=10):
        self.calls.append((method, url, form, bearer))
        if url.endswith("/oauth2/v2.1/token"):
            if self.fail_token:
                raise line_service.LineApiError(400, "invalid_grant")
            assert form["code_verifier"] and form["client_secret"] == "c" * 32
            return {"access_token": "at", "id_token": "idt"}
        if url.endswith("/oauth2/v2.1/verify"):
            self.verify_nonce = form["nonce"]
            return dict(self.profile)
        if url.endswith("/friendship/v1/status"):
            assert bearer == "at"
            return {"friendFlag": self.friend}
        raise AssertionError(url)


@pytest.fixture
def ll(monkeypatch):
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", "2000000000")
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_SECRET", "c" * 32)
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "")
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
    fake = FakeLineLogin()
    monkeypatch.setattr(line_login_service, "call", fake)
    line_service.reset_for_testing()
    yield fake
    line_service.reset_for_testing()


@pytest.fixture
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr(email_service, "send_line_login_confirm_email", lambda to, link: sent.append((to, link)) or True)
    return sent


def _sub():
    return f"U{next(_seq):032x}"


def _start(client, headers=None):
    path = "/auth/line/link-start" if headers else "/auth/line/start"
    r = client.post(path, headers=headers or {})
    assert r.status_code == 200, r.text
    q = parse_qs(urlparse(r.json()["url"]).query)
    assert q["state"][0] == r.json()["state"]
    return q


def _flow(client, fake, headers=None, **profile):
    q = _start(client, headers)
    fake.profile = {"sub": profile.pop("sub", None) or _sub(), "name": "คุณไลน์", **profile}
    r = client.post("/auth/line/callback", json={"code": "c1", "state": q["state"][0]})
    return q, r


def _user(**filters):
    db = SessionLocal()
    try:
        return db.query(User).filter_by(**filters).first()
    finally:
        db.close()


def test_disabled_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", "")
    assert client.get("/auth/line/config").json() == {"enabled": False}
    assert client.post("/auth/line/start").status_code == 503


def test_authorize_url_has_pkce_nonce_and_bot_prompt(client, ll, monkeypatch):
    q = _start(client)
    assert q["client_id"] == ["2000000000"]
    assert q["redirect_uri"] == [f"{settings.FRONTEND_URL.rstrip('/')}/auth/line/callback"]
    assert q["scope"] == ["profile openid email"] and q["code_challenge_method"] == ["S256"]
    assert "bot_prompt" not in q  # ไม่มี OA → ไม่ชวนเพิ่มเพื่อน
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "s" * 32)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "t")
    assert _start(client)["bot_prompt"] == ["aggressive"]


def test_new_user_from_line_email_then_login_again_by_sub(client, ll):
    email = f"line{next(_seq)}@example.com"
    q, r = _flow(client, ll, email=email, picture="https://p/x.png")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "login" and r.json()["access_token"]
    assert ll.verify_nonce == q["nonce"][0]
    user = _user(email=email)
    assert user.line_login_id and user.is_verified and user.display_name == "คุณไลน์"
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["email"] == email
    # ครั้งต่อไป LINE ไม่ส่งอีเมลมา ก็ยังเข้าบัญชีเดิมได้จาก sub
    _, r2 = _flow(client, ll, sub=user.line_login_id)
    assert r2.json()["status"] == "login"


def test_state_is_single_use_and_bad_code_fails(client, ll):
    q, r = _flow(client, ll, email=f"x{next(_seq)}@example.com")
    assert r.status_code == 200
    again = client.post("/auth/line/callback", json={"code": "c1", "state": q["state"][0]})
    assert again.status_code == 400
    ll.fail_token = True
    _, bad = _flow(client, ll, email=f"y{next(_seq)}@example.com")
    assert bad.status_code == 400 and "LINE" in bad.json()["detail"]


def test_existing_account_with_same_email_is_linked(client, ll, make_user):
    uid, _ = make_user()
    email = _user(id=uid).email
    _, r = _flow(client, ll, email=email.upper())
    assert r.json()["status"] == "login"
    assert _user(id=uid).line_login_id


def test_inactive_account_rejected(client, ll, make_user):
    uid, _ = make_user()
    db = SessionLocal()
    user = db.get(User, uid)
    user.is_active = False
    email = user.email
    db.commit()
    db.close()
    _, r = _flow(client, ll, email=email)
    assert r.status_code == 403


def test_no_email_requires_confirmation_in_same_browser(client, ll, mails, make_user):
    uid, _ = make_user()
    email = _user(id=uid).email
    _, r = _flow(client, ll)
    assert r.json()["status"] == "need_email"
    pending = r.json()["pending"]
    assert client.post("/auth/line/email", json={"pending": pending, "email": "bad"}).status_code == 400
    r = client.post("/auth/line/email", json={"pending": pending, "email": email})
    assert r.status_code == 200 and r.json()["status"] == "sent"
    to, link = mails[-1]
    assert to == email and "/auth/line/callback?confirm=" in link
    token = parse_qs(urlparse(link).query)["confirm"][0]
    # เปิดในเบราว์เซอร์อื่น (ไม่มี pending) → ไม่ให้ผ่าน แต่ลิงก์ยังใช้ได้ในเบราว์เซอร์ที่ถูก
    assert client.post("/auth/line/confirm", json={"token": token, "pending": "other"}).status_code == 403
    assert _user(id=uid).line_login_id is None
    ok = client.post("/auth/line/confirm", json={"token": token, "pending": pending})
    assert ok.status_code == 200 and ok.json()["status"] == "login"
    assert _user(id=uid).line_login_id
    assert client.post("/auth/line/confirm", json={"token": token, "pending": pending}).status_code == 400


def test_confirmation_email_limit(client, ll, mails):
    _, r = _flow(client, ll)
    pending = r.json()["pending"]
    for _ in range(line_login_service.MAX_CONFIRM_EMAILS):
        assert client.post("/auth/line/email", json={"pending": pending, "email": "a@example.com"}).status_code == 200
    assert client.post("/auth/line/email", json={"pending": pending, "email": "a@example.com"}).status_code == 429


def test_link_from_security_page_and_unlink(client, ll, make_user):
    uid, headers = make_user()
    assert client.get("/line/status", headers=headers).json()["login"] == {"enabled": True, "linked": False}
    sub = _sub()
    _, r = _flow(client, ll, headers=headers, sub=sub, email="different@example.com")
    assert r.json() == {"status": "linked"}
    assert _user(id=uid).line_login_id == sub
    assert client.get("/line/status", headers=headers).json()["login"]["linked"] is True
    # LINE เดียวกันเชื่อมอีกบัญชีไม่ได้
    _, other_headers = make_user()
    _, r = _flow(client, ll, headers=other_headers, sub=sub)
    assert r.status_code == 409
    r = client.delete("/auth/line/link", headers=headers)
    assert r.json()["linked"] is False and _user(id=uid).line_login_id is None


def test_friend_of_oa_gets_notifications_linked(client, ll, monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "s" * 32)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "t")
    monkeypatch.setattr(line_service, "fetch_display_name", lambda uid: "คุณไลน์")
    ll.friend = True
    email = f"friend{next(_seq)}@example.com"
    _, r = _flow(client, ll, email=email)
    assert r.json()["status"] == "login"
    user = _user(email=email)
    assert user.line_user_id == user.line_login_id and user.line_notifications
    # บล็อก OA (unfollow) ยกเลิกแค่แจ้งเตือน ยังเข้าสู่ระบบด้วย LINE ได้
    db = SessionLocal()
    line_service.handle_events(db, {"events": [{"type": "unfollow", "source": {"type": "user", "userId": user.line_login_id}}]})
    db.close()
    after = _user(email=email)
    assert after.line_user_id is None and after.line_login_id == user.line_login_id
    _, r = _flow(client, ll, sub=after.line_login_id)
    assert r.json()["status"] == "login"
