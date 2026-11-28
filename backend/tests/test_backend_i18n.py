"""เทสต์ระบบแปลภาษาฝั่ง Backend (app.core.i18n, email_service, signing_emails, donation_service)"""
from app.core import i18n
from app.services import email_service


def test_backend_i18n_keys_in_sync():
    base_keys = set(i18n._MESSAGES["th"].keys())
    for lang in i18n.SUPPORTED_LANGUAGES:
        assert set(i18n._MESSAGES[lang].keys()) == base_keys


def test_backend_i18n_normalize_and_translate():
    assert i18n.normalize_lang("en-US,en;q=0.9") == "en"
    assert i18n.normalize_lang("th-TH") == "th"
    assert i18n.normalize_lang("fr-FR") == "fr"
    assert i18n.normalize_lang("ko-KR") == "ko"
    assert i18n.normalize_lang("ar-SA") == "ar"
    assert i18n.normalize_lang("xx-XX") == "th"
    assert i18n.t("en", "email.reset.button") == "Reset Password"
    assert i18n.t("th", "email.reset.button") == "ตั้งรหัสผ่านใหม่"


def test_email_service_renders_english_when_lang_en(monkeypatch):
    sent = []
    monkeypatch.setattr(email_service.mailer, "send_now", lambda mail: sent.append(mail) or True)
    ok = email_service.send_reset_password_email("alice@example.com", "https://example.com/reset", lang="en")
    assert ok is True
    assert len(sent) == 1
    assert "Reset Password" in sent[0].subject
    assert "Hello," in sent[0].text
