"""รูปแบบการติดตั้ง public / onprem: ปิด Google/LINE, จำกัดการสมัครตามโดเมน, ค่าคอนฟิกสาธารณะ, SMTP ภายในองค์กร"""
import importlib
import itertools

import pytest

from app.core import config as config_module
from app.core.config import settings
from app.services import mailer
from tests.test_signing_phase3 import _box, _create, outbox  # noqa: F401 (fixture)

_seq = itertools.count(1)


def _register(client, email):
    return client.post("/auth/register", json={"email": email, "password": "Passw0rd123", "accepted_tos": True})


def _reload_config():
    """reload config ด้วย env ปัจจุบัน แล้วคืน Settings ใหม่ — คืนค่าโมดูลเดิมทุกครั้ง
    (โมดูลอื่น import settings ตัวเดิมไว้แล้ว ห้ามให้ test อื่นได้ object ใหม่)"""
    saved = dict(vars(config_module))
    try:
        return importlib.reload(config_module).Settings()
    finally:
        vars(config_module).clear()
        vars(config_module).update(saved)


def _fresh_settings(monkeypatch, **env):
    """สร้าง Settings ใหม่จาก env (ค่า default ของ onprem คำนวณตอน import)"""
    for key in ("DEPLOYMENT_PROFILE", "AUTH_GOOGLE_ENABLED", "AUTH_LINE_ENABLED", "ALLOWED_EMAIL_DOMAINS",
                "ALLOW_SELF_REGISTRATION", "GOOGLE_CLIENT_ID", "LINE_LOGIN_CHANNEL_ID", "LINE_LOGIN_CHANNEL_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return _reload_config()


def test_onprem_profile_turns_off_google_and_line_by_default(monkeypatch):
    creds = {"GOOGLE_CLIENT_ID": "x.apps.googleusercontent.com", "LINE_LOGIN_CHANNEL_ID": "1",
             "LINE_LOGIN_CHANNEL_SECRET": "s"}
    public = _fresh_settings(monkeypatch, **creds)
    assert public.DEPLOYMENT_PROFILE == "public" and public.google_enabled and public.line_login_enabled

    onprem = _fresh_settings(monkeypatch, DEPLOYMENT_PROFILE="onprem", ALLOWED_EMAIL_DOMAINS="Corp.co.th, corp.com",
                             **creds)
    assert onprem.is_onprem and not onprem.google_enabled and not onprem.line_login_enabled
    assert onprem.ALLOWED_EMAIL_DOMAINS == ["corp.co.th", "corp.com"]

    # เปิดเองได้ถ้าต้องการ
    opted_in = _fresh_settings(monkeypatch, DEPLOYMENT_PROFILE="onprem", AUTH_GOOGLE_ENABLED="true", **creds)
    assert opted_in.google_enabled and not opted_in.line_login_enabled


def test_bad_profile_fails_fast(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "intranet")
    with pytest.raises(RuntimeError):
        _reload_config()


def test_public_config_endpoint(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "AUTH_GOOGLE_ENABLED", True)
    body = client.get("/config/public").json()
    assert body["profile"] == "public" and body["google_client_id"] == "abc.apps.googleusercontent.com"
    assert body["self_registration"] is True and body["allowed_email_domains"] == []

    monkeypatch.setattr(settings, "AUTH_GOOGLE_ENABLED", False)
    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAINS", ["corp.co.th"])
    body = client.get("/config/public").json()
    assert body["google_client_id"] is None and body["line_login"] is False
    assert body["allowed_email_domains"] == ["corp.co.th"]
    assert client.post("/auth/google", json={"credential": "x"}).status_code == 503


def test_public_config_offers_source_code(client, monkeypatch):
    """AGPL-3.0 ข้อ 13 — หน้าเว็บต้องบอกผู้ใช้ได้เสมอว่าซอร์สอยู่ที่ไหน"""
    body = client.get("/config/public").json()
    assert body["source_url"].startswith("https://") and body["license"] == "AGPL-3.0-or-later"
    monkeypatch.setattr(settings, "SOURCE_CODE_URL", "https://git.corp.co.th/pdf-editor")
    assert client.get("/config/public").json()["source_url"] == "https://git.corp.co.th/pdf-editor"


def test_register_restricted_to_company_domain(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAINS", ["corp.co.th"])
    r = _register(client, f"outsider{next(_seq)}@gmail.com")
    assert r.status_code == 403 and "@corp.co.th" in r.json()["detail"]
    assert _register(client, f"staff{next(_seq)}@CORP.co.th").status_code == 200


def test_self_registration_off_allows_initial_admin_only(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_SELF_REGISTRATION", False)
    boss = f"boss{next(_seq)}@corp.co.th"
    monkeypatch.setattr(settings, "INITIAL_ADMIN_EMAILS", boss)
    assert _register(client, f"someone{next(_seq)}@corp.co.th").status_code == 403
    r = _register(client, boss)
    assert r.status_code == 200 and r.json()["is_admin"] is True


def test_invited_signer_can_register_outside_domain(client, make_user, upload, outbox, monkeypatch):  # noqa: F811
    _, owner = make_user()
    guest = f"partner{next(_seq)}@vendor.example"
    assert _create(client, owner, upload, [{"email": guest, "sign_type": "electronic", **_box(0)}]).status_code == 200
    monkeypatch.setattr(settings, "ALLOWED_EMAIL_DOMAINS", ["corp.co.th"])
    monkeypatch.setattr(settings, "ALLOW_SELF_REGISTRATION", False)
    assert _register(client, guest).status_code == 200
    assert _register(client, f"other{next(_seq)}@vendor.example").status_code == 403


class _Relay:
    calls: list = []

    def __init__(self, host, port, timeout=None, **kw):
        _Relay.calls.append(("connect", host, port, type(self).__name__))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, **kw):
        _Relay.calls.append(("starttls", kw.get("context") is not None))

    def login(self, *a):
        _Relay.calls.append(("login",))

    def send_message(self, msg):
        _Relay.calls.append(("sent", msg["From"]))


class _RelaySSL(_Relay):
    pass


@pytest.fixture
def relay(monkeypatch):
    _Relay.calls = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", _Relay)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", _RelaySSL)
    monkeypatch.setattr(settings, "SMTP_SERVER", "mail.corp.local")
    monkeypatch.setattr(settings, "SMTP_USERNAME", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    monkeypatch.setattr(settings, "SMTP_FROM", "pdf@corp.co.th")
    monkeypatch.setattr(settings, "SMTP_AUTH", "")
    monkeypatch.setattr(settings, "SMTP_SECURITY", "")
    return _Relay.calls


def _send():
    return mailer._send_now(mailer.Mail(to="a@corp.co.th", subject="s", text="t", html="<p>t</p>"))


def test_internal_relay_without_login(relay, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PORT", 25)
    monkeypatch.setattr(settings, "SMTP_SECURITY", "none")
    assert settings.smtp_configured and not settings.smtp_auth
    assert _send() is True
    assert relay[0] == ("connect", "mail.corp.local", 25, "_Relay")
    assert not any(c[0] in ("login", "starttls") for c in relay)
    assert "pdf@corp.co.th" in str(relay[-1][1])


def test_relay_starttls_without_login_and_ssl_mode(relay, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    assert settings.smtp_security == "starttls"  # ค่าเดิม SMTP_USE_TLS=true
    assert _send() is True
    assert ("starttls", True) in relay and ("login",) not in relay

    relay.clear()
    monkeypatch.setattr(settings, "SMTP_SECURITY", "ssl")
    monkeypatch.setattr(settings, "SMTP_AUTH", "true")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "svc-pdf")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    assert _send() is True
    assert relay[0][3] == "_RelaySSL" and ("login",) in relay


def test_no_from_and_no_login_stays_simulated(relay, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_FROM", None)
    assert not settings.smtp_configured
    assert _send() is False and relay == []
