"""SEC-04: access token ใน HttpOnly cookie + CSRF (double-submit) — Bearer เดิมยังใช้ได้"""
import pytest

from app.core.auth_cookies import CSRF_COOKIE, SESSION_COOKIE

COOKIE_MODE = {"X-Auth-Mode": "cookie"}


@pytest.fixture
def cookie_login(client, make_user):
    """login แบบหน้าเว็บ → คืน (client ที่ถือ cookie, ค่า csrf)"""
    uid, h = make_user()
    email = client.get("/auth/me", headers=h).json()["email"]
    client.cookies.clear()
    r = client.post("/auth/login", data={"username": email, "password": "password123"}, headers=COOKIE_MODE)
    assert r.status_code == 200, r.text
    return r


def test_cookie_login_hides_token_and_sets_flags(cookie_login, client):
    r = cookie_login
    assert "access_token" not in r.json() and r.json()["token_type"] == "cookie"
    raw = r.headers.get_list("set-cookie")
    session = next(c for c in raw if c.startswith(f"{SESSION_COOKIE}="))
    csrf = next(c for c in raw if c.startswith(f"{CSRF_COOKIE}="))
    assert "HttpOnly" in session and "samesite=lax" in session.lower() and "Path=/" in session
    assert "HttpOnly" not in csrf  # หน้าเว็บต้องอ่านได้เพื่อส่งกลับใน header
    assert "Secure" not in session  # FRONTEND_URL ของเทสต์เป็น http — on-prem แบบ http ต้องใช้ได้
    assert int(r.headers["content-length"]) == len(r.content)


def test_cookie_auth_get_works_and_unsafe_needs_csrf(cookie_login, client):
    assert client.get("/auth/me").status_code == 200
    body = {"display_name": "ทดสอบ"}
    r = client.put("/auth/profile", json=body)
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]
    r = client.put("/auth/profile", json=body, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    r = client.put("/auth/profile", json=body, headers={"X-CSRF-Token": client.cookies[CSRF_COOKIE]})
    assert r.status_code == 200, r.text


def test_logout_revokes_cookie_session_and_clears_cookies(cookie_login, client):
    csrf = client.cookies[CSRF_COOKIE]
    token = client.cookies[SESSION_COOKIE]
    # ไม่มี CSRF (เช่นเว็บอื่นยิงมา) → ไม่ตัด session
    client.post("/auth/logout")
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf)
    assert client.get("/auth/me").status_code == 200
    r = client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert any(c.startswith(f"{SESSION_COOKIE}=") and "Max-Age=0" in c for c in r.headers.get_list("set-cookie"))
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/auth/me").status_code == 401  # token เดิมถูกตัดแล้ว


def test_bearer_still_works_without_csrf(client, make_user):
    _, h = make_user()
    client.cookies.clear()
    assert client.put("/auth/profile", json={"display_name": "x"}, headers=h).status_code == 200
    r = client.post("/auth/login", data={"username": client.get("/auth/me", headers=h).json()["email"],
                                         "password": "password123"})
    assert r.json()["token_type"] == "bearer" and r.json()["access_token"]  # ไม่ขอ cookie = แบบเดิม
    assert SESSION_COOKIE not in r.cookies


def test_legacy_local_storage_token_moves_to_cookie(client, make_user):
    _, h = make_user()
    client.cookies.clear()
    assert client.post("/auth/session/cookie").status_code == 401
    r = client.post("/auth/session/cookie", headers=h)
    assert r.status_code == 200 and client.cookies.get(SESSION_COOKIE) == h["Authorization"].split()[1]
    assert client.get("/auth/me").status_code == 200  # ใช้ cookie ได้ทันที (token/jti เดิม)


def test_cookie_mode_error_body_untouched(client):
    r = client.post("/auth/login", data={"username": "nobody@example.com", "password": "x"}, headers=COOKIE_MODE)
    assert r.status_code == 401 and r.json()["detail"]
    assert SESSION_COOKIE not in r.cookies


def test_line_login_in_cookie_mode(client, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from app.core.config import settings
    from app.services import line_login_service, line_service
    from tests.test_line_login import FakeLineLogin

    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_ID", "2000000000")
    monkeypatch.setattr(settings, "LINE_LOGIN_CHANNEL_SECRET", "c" * 32)
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "")
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
    fake = FakeLineLogin()
    monkeypatch.setattr(line_login_service, "call", fake)
    line_service.reset_for_testing()
    state = parse_qs(urlparse(client.post("/auth/line/start").json()["url"]).query)["state"][0]
    fake.profile = {"sub": "U" + "c" * 32, "name": "คุณไลน์", "email": "cookie-line@example.com"}
    r = client.post("/auth/line/callback", json={"code": "c1", "state": state}, headers=COOKIE_MODE)
    assert r.status_code == 200 and r.json() == {"status": "login", "token_type": "cookie"}
    assert client.get("/auth/me").json()["email"] == "cookie-line@example.com"
    line_service.reset_for_testing()
