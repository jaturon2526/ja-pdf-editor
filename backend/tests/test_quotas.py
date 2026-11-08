"""หน้าโควต้า/เครดิตของแอดมิน: ตัวนับรายวัน, ยอดจาก Brevo/LINE API, fallback และแจ้งเตือนแอดมินเมื่อใกล้เต็ม"""
import pytest

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.domain import User
from app.services import line_service, mailer, quota_service
from tests.test_auth_emails import FakeSMTP


@pytest.fixture(autouse=True)
def _reset():
    quota_service.reset_for_testing()
    line_service.reset_for_testing()
    yield
    quota_service.reset_for_testing()


@pytest.fixture
def outbox(monkeypatch):
    sent: list[mailer.Mail] = []
    monkeypatch.setattr(mailer, "deliver", sent.append)
    return sent


@pytest.fixture
def admin(client, make_user):
    uid, headers = make_user()
    with SessionLocal() as db:
        user = db.get(User, uid)
        user.is_admin = True
        email = user.email
        db.commit()
    return headers, email


@pytest.fixture
def brevo_smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_SERVER", "smtp-relay.brevo.com")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "login@smtp-brevo.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "k" * 90)
    monkeypatch.setattr(settings, "SMTP_AUTH", "")


def _items(client, headers, **params):
    r = client.get("/admin/quotas", headers=headers, params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    return {i["key"]: i for i in body["items"]}, body


def test_requires_admin(client, make_user):
    _, h = make_user()
    assert client.get("/admin/quotas", headers=h).status_code == 403


def test_daily_counters_and_history(client, admin, brevo_smtp, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "AIza-test")
    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "AI_API_KEY", "")
    with SessionLocal() as db:
        before_email = quota_service.count_on(db, "email")
        before_line = quota_service.count_on(db, "line")
    quota_service.record("email")
    quota_service.record("email")
    quota_service.record("line")
    items, body = _items(client, admin[0])
    assert len(body["history"]) == 30
    last = body["history"][-1]
    assert last["email"] == before_email + 2 and last["line"] == before_line + 1
    assert body["alert_percent"] == settings.QUOTA_ALERT_PERCENT
    # ไม่มี BREVO_API_KEY → ตัวนับของระบบ
    assert items["email"]["source"] == "internal" and items["email"]["limit"] == settings.BREVO_DAILY_LIMIT
    assert items["email"]["used"] == before_email + 2
    assert items["ai"]["used"] >= 0 and items["ai"]["link"].startswith("https://aistudio.google.com")
    assert items["disk"]["limit"] > 0
    assert "line" not in items  # LINE ไม่ได้เปิด
    assert body["series"] == ["ai", "email"]


def test_email_card_follows_smtp_setup_and_ai_card_follows_provider(client, admin, monkeypatch):
    for k, v in {"SMTP_USERNAME": None, "SMTP_PASSWORD": None, "SMTP_FROM": None, "SMTP_AUTH": "",
                 "BREVO_API_KEY": "", "AI_PROVIDER": "", "AI_API_KEY": "", "GEMINI_API_KEY": None,
                 "AI_USER_KEYS_ENABLED": True}.items():
        monkeypatch.setattr(settings, k, v)
    items, body = _items(client, admin[0])
    assert "email" not in items and body["series"] == ["ai"]  # ไม่ได้ตั้ง SMTP — ไม่มีการ์ดอีเมล
    assert items["ai"]["name"].startswith("AI — key ส่วนตัว")

    # SMTP ขององค์กร (relay ไม่ login) — ไม่มีเพดาน Brevo ไม่แจ้งเตือน
    monkeypatch.setattr(settings, "SMTP_SERVER", "webmail.corp.co.th")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_FROM", "pdf@corp.co.th")
    monkeypatch.setattr(settings, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "AI_API_KEY", "sk-ant-x")
    monkeypatch.setattr(settings, "AI_MODEL", "claude-test")
    items, body = _items(client, admin[0])
    email = items["email"]
    assert email["name"] == "อีเมล (SMTP)" and email["limit"] is None and email["status"] == "info"
    assert "webmail.corp.co.th:587" in email["note"] and "brevo" not in (email["link"] or "")
    assert body["series"] == ["ai", "email"]
    ai = items["ai"]
    assert ai["name"] == "Anthropic Claude (คำขอวันนี้)" and ai["link"].startswith("https://console.anthropic.com")
    assert "claude-test" in ai["note"]

    monkeypatch.setattr(settings, "AI_PROVIDER", "")
    monkeypatch.setattr(settings, "AI_API_KEY", "")
    monkeypatch.setattr(settings, "AI_USER_KEYS_ENABLED", False)
    items, _ = _items(client, admin[0])
    assert "ai" not in items  # ไม่มี AI เลย


def test_successful_smtp_send_is_counted(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USERNAME", "login@smtp-brevo.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "k" * 90)
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    with SessionLocal() as db:
        before = quota_service.count_on(db, "email")
    assert mailer.send_now(mailer.Mail(to="x@example.com", subject="s", text="t", html="<p>t</p>"))
    with SessionLocal() as db:
        assert quota_service.count_on(db, "email") == before + 1


def test_brevo_api_credits_and_error(client, admin, brevo_smtp, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    calls = []

    def fake_get(path):
        calls.append(path)
        return {"plan": [{"type": "free", "creditsType": "sendLimit", "credits": 60}]}

    monkeypatch.setattr(quota_service, "brevo_get", fake_get)
    items, _ = _items(client, admin[0])
    email = items["email"]
    assert email["source"] == "api" and email["used"] == 240 and email["remaining"] == 60
    assert email["percent"] == 80.0 and email["status"] == "warn"
    _items(client, admin[0])
    assert calls == ["/v3/account"]  # cache 10 นาที
    _items(client, admin[0], refresh="true")
    assert len(calls) == 2

    def broken(path):
        raise quota_service.ApiError("Brevo ปฏิเสธ API key (401)")

    monkeypatch.setattr(quota_service, "brevo_get", broken)
    items, _ = _items(client, admin[0], refresh="true")
    assert items["email"]["source"] == "internal" and "401" in items["email"]["error"]
    assert items["email"]["status"] == "error"


def test_line_quota_from_api(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_SECRET", "s" * 32)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "t" * 171)

    def fake(method, path, body=None, timeout=10):
        return {"/v2/bot/message/quota": {"type": "limited", "value": 300},
                "/v2/bot/message/quota/consumption": {"totalUsage": 250}}[path]

    monkeypatch.setattr(line_service, "call_api", fake)
    items, _ = _items(client, admin[0])
    line = items["line"]
    assert (line["used"], line["limit"], line["remaining"], line["status"]) == (250, 300, 50, "warn")
    assert line["source"] == "api" and line["resets_at"]


def test_alerts_admins_once_per_day(client, admin, outbox, brevo_smtp, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(quota_service, "brevo_get",
                        lambda path: {"plan": [{"type": "free", "creditsType": "sendLimit", "credits": 0}]})
    _, email = admin
    with SessionLocal() as db:
        assert quota_service.check_and_alert(db) >= 1
    mine = [m for m in outbox if m.to == email and "อีเมล (Brevo)" in m.subject]
    assert len(mine) == 1 and "เต็มแล้ว" in mine[0].subject and "/admin" in mine[0].text
    with SessionLocal() as db:
        quota_service.check_and_alert(db)
    assert len([m for m in outbox if m.to == email and "อีเมล (Brevo)" in m.subject]) == 1


# ---------------------------------------------------------------- สถานะเซิร์ฟเวอร์ (RAM / CPU / Redis / สำรองข้อมูล)


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", uploads)
    return tmp_path


def test_server_status_items(client, admin, data_root, monkeypatch):
    monkeypatch.setattr(quota_service, "_meminfo", lambda: {"MemTotal": 8 * 1024 ** 3, "MemAvailable": 1024 ** 3})
    monkeypatch.setattr("os.getloadavg", lambda: (1.0, 3.6, 2.0))
    monkeypatch.setattr("os.cpu_count", lambda: 4)
    items, _ = _items(client, admin[0])
    mem, cpu = items["memory"], items["cpu"]
    assert (mem["used"], mem["limit"], mem["status"]) == (7 * 1024 ** 3, 8 * 1024 ** 3, "warn")  # 87.5%
    assert (cpu["used"], cpu["limit"], cpu["unit"], cpu["status"]) == (360, 400, "%", "warn")
    assert "4 core" in cpu["note"]
    # ไม่เคยสำรอง → แสดงวิธีตั้ง · นอกเครื่องไม่แสดงจนกว่าจะมีสคริปต์เขียนเวลา
    assert items["backup"]["status"] == "info" and "backup-schedule" in items["backup"]["note"]
    assert "backup-offsite" not in items


def test_backup_freshness_and_alert(client, admin, outbox, data_root, monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    (data_root / ".last-backup").write_text((now - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
    (data_root / ".last-offsite-backup").write_text((now - timedelta(hours=50)).isoformat())
    items, _ = _items(client, admin[0])
    local, off = items["backup"], items["backup-offsite"]
    assert (local["used"], local["unit"], local["status"]) == (5, "ชม. ที่แล้ว", "ok")
    assert "ครั้งล่าสุด" in local["note"]
    assert (off["used"], off["status"], off["status_label"]) == (50, "warn", "ขาดหาย")

    _, email = admin
    with SessionLocal() as db:
        quota_service.check_and_alert(db)
        quota_service.check_and_alert(db)  # วันละครั้ง
    mine = [m for m in outbox if m.to == email and "นอกเครื่อง" in m.subject]
    assert len(mine) == 1 and "50 ชั่วโมง" in mine[0].subject


def test_redis_item_reports_unreachable(client, admin, monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(quota_service, "get_redis", lambda: None)
    items, _ = _items(client, admin[0])
    assert items["redis"]["status"] == "error" and "Redis" in items["redis"]["error"]
