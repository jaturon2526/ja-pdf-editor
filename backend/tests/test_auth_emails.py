"""อีเมลยืนยันอีเมล/ตั้งรหัสผ่านใหม่ต้องใช้ผู้ส่ง SMTP_FROM (เดิมใช้ SMTP_USERNAME — Brevo login เป็น xxx@smtp-brevo.com ส่งไม่ได้)"""
from email.utils import parseaddr

import pytest

from app.core.config import settings
from app.services import mailer


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, **kw):
        pass

    def login(self, user, password):
        self.user = user

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def brevo(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_SERVER", "smtp-relay.brevo.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "abc123@smtp-brevo.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "k" * 90)
    monkeypatch.setattr(settings, "SMTP_FROM", "no-reply@ja-pdf.com")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent = []
    return FakeSMTP.sent


def _email(client, headers):
    return client.get("/auth/me", headers=headers).json()["email"]


def test_reset_password_email_uses_smtp_from(client, make_user, brevo):
    _, h = make_user()
    email = _email(client, h)
    r = client.post("/auth/forgot-password", json={"email": email})
    assert r.status_code == 200, r.text
    assert len(brevo) == 1
    msg = brevo[0]
    assert parseaddr(str(msg["From"]))[1] == "no-reply@ja-pdf.com"
    assert msg["To"] == email
    assert "/reset-password?token=" in msg.get_body(("plain",)).get_content()


def test_resend_verification_uses_smtp_from(client, brevo):
    r = client.post("/auth/register", json={"email": "newbie@example.com", "password": "Passw0rd123",
                                            "accepted_tos": True})
    assert r.status_code == 200, r.text
    assert client.post("/auth/resend-verification", json={"email": "newbie@example.com"}).status_code == 200
    assert len(brevo) == 2
    for msg in brevo:
        assert parseaddr(str(msg["From"]))[1] == "no-reply@ja-pdf.com"
        assert "/api/auth/verify-email?token=" in msg.get_body(("html",)).get_content()


def test_resend_verification_reports_failure(client, brevo, monkeypatch):
    client.post("/auth/register", json={"email": "fail@example.com", "password": "Passw0rd123", "accepted_tos": True})

    def boom(*a, **k):
        raise OSError("smtp down")

    monkeypatch.setattr(mailer.smtplib, "SMTP", boom)
    assert client.post("/auth/resend-verification", json={"email": "fail@example.com"}).status_code == 500


@pytest.mark.parametrize("port,expect_ssl,expect_starttls", [(465, True, False), (587, False, True)])
def test_smtp_port_465_uses_ssl(monkeypatch, port, expect_ssl, expect_starttls):
    import smtplib

    calls = []

    class Fake:
        def __init__(self, host, p, timeout=None, **kw):
            calls.append(("ssl" if self.__class__.__name__ == "FakeSSL" else "plain", p))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, **kw):
            calls.append("starttls")

        def login(self, *a):
            pass

        def send_message(self, msg):
            calls.append("sent")

    class FakeSSL(Fake):
        pass

    monkeypatch.setattr(smtplib, "SMTP", Fake)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSSL)
    monkeypatch.setattr(settings, "SMTP_PORT", port)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "u@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    assert mailer._send_now(mailer.Mail(to="a@example.com", subject="s", text="t", html="<p>t</p>")) is True
    assert calls[0] == ("ssl" if expect_ssl else "plain", port)
    assert ("starttls" in calls) is expect_starttls
