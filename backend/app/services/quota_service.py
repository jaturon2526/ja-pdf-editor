"""โควต้า/เครดิตของบริการภายนอก สำหรับหน้าแอดมิน (/admin/quotas) + แจ้งเตือนแอดมินเมื่อใกล้เต็ม

แหล่งข้อมูล:
- LINE: ยอดจริงจาก LINE API (/v2/bot/message/quota, /quota/consumption — เรียกได้ไม่เสียโควต้า)
  ดึงไม่ได้ → ตัวนับของเรา (line_service.pushes_this_month)
- อีเมล (Brevo): เครดิตคงเหลือจาก Brevo API GET /v3/account (ต้องตั้ง BREVO_API_KEY แบบ Restricted:
  Transactional email + Account = Read) ไม่ตั้ง/ดึงไม่ได้ → ตัวนับของเรา (service_usage_daily)
- Gemini: ไม่มี API บอกเครดิตคงเหลือ → จำนวนคำขอวันนี้ (ai_usage) เทียบ GEMINI_DAILY_REQUEST_LIMIT (ถ้าตั้ง)
- ดิสก์ (/data) และขนาดฐานข้อมูล
- สถานะเซิร์ฟเวอร์: RAM / CPU (โหลดเฉลี่ย 5 นาที) ทั้งเครื่อง · หน่วยความจำ Redis · เวลาสำรองข้อมูลล่าสุด
  (สคริปต์ backup เขียนเวลาไว้ที่ /data/.last-backup และ /data/.last-offsite-backup — ดู scripts/onprem/deploy.sh backup)
ผลจาก API ภายนอก cache 10 นาที · งานเบื้องหลังเรียกทุก QUOTA_CHECK_INTERVAL_MINUTES (ทำให้ Brevo key
ไม่หมดอายุเพราะไม่ถูกใช้ 90 วัน) และแจ้งเตือนแอดมินวันละไม่เกิน 1 ครั้งต่อบริการ
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import get_redis
from app.db.database import SessionLocal
from app.models.domain import AIUsageDaily, ServiceUsageDaily, User
from app.services import ai_usage

logger = logging.getLogger("quota")

EMAIL = "email"
LINE = "line"
CACHE_SECONDS = 600
HISTORY_DAYS = 30


def today() -> date:
    return ai_usage.today()


# ---------------------------------------------------------------- ตัวนับรายวัน


def record(service: str, by: int = 1) -> None:
    """นับการใช้บริการ 1 ครั้ง (ไม่ raise — การนับล้มเหลวต้องไม่ทำให้การส่งล้ม)"""
    try:
        with SessionLocal() as db:
            _increment(db, service, by, today())
    except Exception:
        logger.warning("บันทึกการใช้ %s ไม่สำเร็จ", service, exc_info=True)


def _increment(db: Session, service: str, by: int, day: date) -> None:
    stmt = (update(ServiceUsageDaily)
            .where(ServiceUsageDaily.usage_date == day, ServiceUsageDaily.service == service)
            .values(count=ServiceUsageDaily.count + by))
    if db.execute(stmt).rowcount:
        db.commit()
        return
    db.add(ServiceUsageDaily(usage_date=day, service=service, count=by))
    try:
        db.commit()
    except IntegrityError:  # อีกคำขอสร้างแถวไปพร้อมกัน
        db.rollback()
        db.execute(stmt)
        db.commit()


def count_on(db: Session, service: str, day: Optional[date] = None) -> int:
    row = db.query(ServiceUsageDaily.count).filter_by(usage_date=day or today(), service=service).first()
    return int(row[0]) if row else 0


def history(db: Session, days: int = HISTORY_DAYS) -> list[dict]:
    end = today()
    start = end - timedelta(days=days - 1)
    rows = {(d, s): c for d, s, c in db.query(ServiceUsageDaily.usage_date, ServiceUsageDaily.service,
                                                   ServiceUsageDaily.count)
            .filter(ServiceUsageDaily.usage_date >= start).all()}
    ai = dict(db.query(AIUsageDaily.usage_date, func.sum(AIUsageDaily.count))
              .filter(AIUsageDaily.usage_date >= start, AIUsageDaily.kind == ai_usage.AI_REQUEST)
              .group_by(AIUsageDaily.usage_date).all())
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append({"date": d.isoformat(), "ai": int(ai.get(d) or 0),
                    EMAIL: int(rows.get((d, EMAIL), 0)), LINE: int(rows.get((d, LINE), 0))})
    return out


# ---------------------------------------------------------------- เรียก API ภายนอก (cache)

_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def _cached(key: str, fn: Callable[[], object], refresh: bool):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
    if hit and not refresh and hit[0] > now:
        return hit[1]
    value = fn()
    with _cache_lock:
        _cache[key] = (now + CACHE_SECONDS, value)
    return value


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


class ApiError(Exception):
    pass


def _brevo_get(path: str) -> dict:
    req = urllib.request.Request(f"{settings.BREVO_API_BASE.rstrip('/')}{path}",
                                 headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — URL มาจาก config
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read() or b"{}").get("message", "")
        except Exception:
            pass
        if exc.code in (401, 403):
            raise ApiError(f"Brevo ปฏิเสธ API key ({exc.code}) — key อาจหมดอายุ/ถูกลบ/สิทธิ์ไม่พอ {detail}".strip()) from None
        raise ApiError(f"Brevo API {exc.code} {detail}".strip()) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(f"ติดต่อ Brevo ไม่ได้: {exc}") from None


# เทสต์แทนที่ตัวนี้
brevo_get: Callable[[str], dict] = _brevo_get


def _line_quota() -> dict:
    from app.services import line_service

    quota = line_service.call_api("GET", "/v2/bot/message/quota")
    used = line_service.call_api("GET", "/v2/bot/message/quota/consumption")
    return {"type": quota.get("type"), "value": quota.get("value"), "used": used.get("totalUsage")}


# ---------------------------------------------------------------- สร้างรายการโควต้า


def _status(used: Optional[float], limit: Optional[float]) -> tuple[Optional[float], str]:
    if used is None or not limit:
        return None, "info"
    pct = round(used * 100.0 / limit, 1)
    if pct >= 100:
        return pct, "full"
    if pct >= settings.QUOTA_ALERT_PERCENT:
        return pct, "warn"
    return pct, "ok"


def _item(key, name, used, limit, unit, period, *, source, resets_at=None, link=None, note=None, error=None,
          extra=None) -> dict:
    pct, status = _status(used, limit)
    if error and source == "internal":
        status = "error" if status in ("ok", "info") else status
    return {
        "key": key, "name": name, "used": used, "limit": limit,
        "remaining": (max(0, limit - used) if (limit and used is not None) else None),
        "unit": unit, "period": period, "percent": pct, "status": status, "source": source,
        "resets_at": resets_at, "link": link, "note": note, "error": error, "extra": extra or {},
    }


def _next_month_jst() -> str:
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    first = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return first.astimezone(timezone.utc).isoformat()


def _tomorrow_local() -> str:
    tz = ZoneInfo(settings.APP_TIMEZONE)
    start = datetime.combine(today() + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    return start.astimezone(timezone.utc).isoformat()


def _line_item(refresh: bool) -> Optional[dict]:
    if not settings.line_enabled:
        return None
    from app.services import line_service

    internal = line_service.pushes_this_month()
    link = "https://manager.line.biz/"
    try:
        q = _cached("line", _line_quota, refresh)
        limit = q["value"] if q.get("type") == "limited" else None
        used = q["used"] if q.get("used") is not None else internal
        return _item("line", "LINE (ข้อความ push)", used, limit, "ข้อความ", "month", source="api",
                     resets_at=_next_month_jst(), link=link,
                     note=f"ระบบส่งเอง {internal} · ส่งอีเมลแทนเมื่อถึง {settings.LINE_MONTHLY_LIMIT}",
                     extra={"internal": internal, "system_limit": settings.LINE_MONTHLY_LIMIT})
    except Exception as exc:
        return _item("line", "LINE (ข้อความ push)", internal, settings.LINE_MONTHLY_LIMIT, "ข้อความ", "month",
                     source="internal", resets_at=_next_month_jst(), link=link,
                     error=f"ดึงยอดจาก LINE ไม่ได้ — แสดงตัวนับของระบบ ({exc})")


def uses_brevo() -> bool:
    return bool(settings.BREVO_API_KEY) or "brevo.com" in (settings.SMTP_SERVER or "").lower()


def _email_item(db: Session, refresh: bool) -> Optional[dict]:
    # ไม่ได้ตั้ง SMTP (ส่งอีเมลจริงไม่ได้) → ไม่แสดง · SMTP องค์กร → นับจำนวนอย่างเดียว ไม่มีเพดานของ Brevo
    if not settings.smtp_configured:
        return None
    sent_today = count_on(db, EMAIL)
    if not uses_brevo():
        return _item("email", "อีเมล (SMTP)", sent_today, None, "ฉบับ", "day", source="internal",
                     resets_at=_tomorrow_local(),
                     note=f"ส่งผ่าน {settings.SMTP_SERVER}:{settings.SMTP_PORT} · นับจากระบบเอง (ไม่มีเพดานรายวัน)",
                     extra={"internal": sent_today})
    link = "https://app.brevo.com/"
    limit = settings.BREVO_DAILY_LIMIT
    if not settings.BREVO_API_KEY:
        return _item("email", "อีเมล (Brevo)", sent_today, limit, "ฉบับ", "day", source="internal",
                     resets_at=_tomorrow_local(), link=link,
                     note="นับจากระบบเอง (ไม่ได้ตั้ง BREVO_API_KEY)", extra={"internal": sent_today})
    try:
        account = _cached("brevo", lambda: brevo_get("/v3/account"), refresh)
        plans = [p for p in account.get("plan") or [] if p.get("type") != "sms"]
        plan = plans[0] if plans else {}
        remaining = plan.get("credits")
        if remaining is None:
            raise ApiError("ไม่พบข้อมูลเครดิตในบัญชี Brevo")
        if plan.get("type") == "free":
            used = max(0, limit - int(remaining))
            return _item("email", "อีเมล (Brevo)", used, limit, "ฉบับ", "day", source="api", link=link,
                         note=f"แพ็กเกจฟรี · ระบบส่งเอง {sent_today} วันนี้ · รีเซ็ตทุกวันตามรอบของ Brevo",
                         extra={"internal": sent_today, "plan": "free"})
        item = _item("email", "อีเมล (Brevo)", None, None, "ฉบับ", "plan", source="api", link=link,
                     note=f"แพ็กเกจ {plan.get('type')} · เหลือ {int(remaining):,} เครดิต",
                     extra={"internal": sent_today, "plan": plan.get("type")})
        item["remaining"] = int(remaining)
        return item
    except Exception as exc:
        return _item("email", "อีเมล (Brevo)", sent_today, limit, "ฉบับ", "day", source="internal",
                     resets_at=_tomorrow_local(), link=link, error=str(exc), extra={"internal": sent_today})


AI_USAGE_LINKS = {
    "gemini": ("https://aistudio.google.com/usage", "Google ไม่มี API บอกเครดิตคงเหลือ ดูยอดจริงที่ AI Studio"),
    "anthropic": ("https://console.anthropic.com/usage", "ดูเครดิต/ค่าใช้จ่ายจริงที่ Claude Console"),
    "openai": ("https://platform.openai.com/usage", "ดูค่าใช้จ่ายจริงที่หน้า Usage ของผู้ให้บริการ"),
}


def _ai_item(db: Session) -> Optional[dict]:
    from app.services import ai_client

    requests_today = ai_usage.total(db, [ai_usage.AI_REQUEST])
    conversions = ai_usage.total(db, [ai_usage.SYSTEM_CONVERSION])
    personal = ai_usage.total(db, [ai_usage.PERSONAL_REQUEST])
    cfg = ai_client.system_config()
    if cfg is None and not settings.AI_USER_KEYS_ENABLED:
        return None  # ไม่มี AI ของระบบ และปิด key ส่วนตัว — ไม่มีอะไรให้นับ
    limit = settings.GEMINI_DAILY_REQUEST_LIMIT or None
    name = f"{cfg.label} (คำขอวันนี้)" if cfg else "AI — key ส่วนตัวผู้ใช้ (คำขอวันนี้)"
    note = f"แปลงด้วย AI ของระบบ {conversions} ครั้ง · key ส่วนตัวผู้ใช้ {personal} คำขอ"
    if cfg:
        note += f" · จำกัด {settings.AI_SYSTEM_DAILY_LIMIT} ครั้ง/ผู้ใช้/วัน"
        if cfg.model:
            note += f" · รุ่น {cfg.model}"
    else:
        note += " · ระบบยังไม่ได้ตั้ง AI_PROVIDER / AI_API_KEY"
    link, hint = AI_USAGE_LINKS.get(cfg.provider if cfg else "", (None, ""))
    if cfg and cfg.provider == "openai" and cfg.base_url:
        link = None  # API ขององค์กร/Azure — ไม่มีหน้า usage กลาง
    if not limit and hint and link:
        note += f" · {hint}"
    return _item("ai", name, requests_today, limit, "คำขอ", "day", source="internal",
                 resets_at=_tomorrow_local(), link=link, note=note,
                 extra={"system_conversions": conversions, "personal_requests": personal,
                        "provider": cfg.provider if cfg else None})


def _disk_item() -> Optional[dict]:
    try:
        path = settings.UPLOAD_DIR if settings.UPLOAD_DIR.exists() else settings.UPLOAD_DIR.parent
        usage = shutil.disk_usage(path)
    except Exception:
        return None
    return _item("disk", "พื้นที่ดิสก์เซิร์ฟเวอร์", usage.used, usage.total, "bytes", "-", source="system",
                 note="ดิสก์ที่เก็บไฟล์ผู้ใช้ (/data)")


BACKUP_MARKERS = ((".last-backup", "backup", "สำรองข้อมูลล่าสุด (ในเครื่อง)"),
                  (".last-offsite-backup", "backup-offsite", "สำรองข้อมูลล่าสุด (นอกเครื่อง)"))


def _meminfo() -> dict[str, int]:
    out = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, _, rest = line.partition(":")
            out[key] = int(rest.split()[0]) * 1024
    return out


def _memory_item() -> Optional[dict]:
    try:
        info = _meminfo()
        total, avail = info["MemTotal"], info.get("MemAvailable", info.get("MemFree", 0))
    except Exception:
        return None
    return _item("memory", "หน่วยความจำ (RAM) เครื่อง", total - avail, total, "bytes", "-", source="system",
                 note="รวมทุกโปรแกรมบนเครื่อง · ใกล้เต็ม = ลด BACKEND_WORKERS หรือเพิ่ม RAM")


def _cpu_item() -> Optional[dict]:
    import os

    try:
        load5 = os.getloadavg()[1]
        cpus = os.cpu_count() or 1
    except (OSError, AttributeError):
        return None
    return _item("cpu", "การใช้ CPU (เฉลี่ย 5 นาที)", round(load5 * 100), cpus * 100, "%", "-", source="system",
                 note=f"{cpus} core · 100% = 1 core เต็ม · สูงต่อเนื่อง = เครื่องรับคนพร้อมกันได้ใกล้เพดาน")


def _redis_item() -> Optional[dict]:
    if not settings.REDIS_URL:
        return None
    r = get_redis()
    if r is None:
        return _item("redis", "Redis (แคช/session)", None, None, "bytes", "-", source="internal",
                     error="เชื่อมต่อ Redis ไม่ได้ — ระบบใช้หน่วยความจำของแต่ละ worker แทน (เอกสารอาจหลุดเมื่อสลับ worker)")
    try:
        info = r.info("memory")
    except Exception as exc:
        return _item("redis", "Redis (แคช/session)", None, None, "bytes", "-", source="internal",
                     error=f"อ่านสถานะ Redis ไม่ได้: {exc}")
    used, cap = int(info.get("used_memory", 0)), int(info.get("maxmemory", 0)) or None
    return _item("redis", "Redis (แคช/session)", used, cap, "bytes", "-", source="system",
                 note="ใกล้เต็ม = ขยาย REDIS_MAXMEMORY ใน .env.prod")


def _backup_items() -> list[dict]:
    root = settings.UPLOAD_DIR.parent
    items = []
    for fname, key, name in BACKUP_MARKERS:
        path = root / fname
        try:
            stamp = datetime.fromisoformat(path.read_text().split()[0].replace("Z", "+00:00"))
        except FileNotFoundError:
            if key == "backup":  # นอกเครื่องไม่บังคับ — แสดงเมื่อมีสคริปต์เขียนแล้วเท่านั้น
                items.append(_item(key, name, None, None, "ชม. ที่แล้ว", "-", source="system",
                                   note="ยังไม่พบประวัติการสำรองข้อมูล — ตั้งสำรองอัตโนมัติรายวัน: ./deploy.sh backup-schedule"))
            continue
        except Exception:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        hours = max(0, int((datetime.now(timezone.utc) - stamp).total_seconds() // 3600))
        item = _item(key, name, hours, None, "ชม. ที่แล้ว", "-", source="system",
                     note=f"ครั้งล่าสุด {stamp.astimezone(ZoneInfo(settings.APP_TIMEZONE)).strftime('%d/%m/%Y %H:%M')} น.")
        item["status"] = "ok"
        if hours > settings.BACKUP_MAX_AGE_HOURS:
            item["status"], item["status_label"] = "warn", "ขาดหาย"
            item["alert"] = f"⚠️ {name}: ไม่มีการสำรองข้อมูลมา {hours} ชั่วโมง (เกิน {settings.BACKUP_MAX_AGE_HOURS} ชม.) — ตรวจ cron/สคริปต์สำรองข้อมูล"
        items.append(item)
    return items


def _db_item(db: Session) -> Optional[dict]:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return None
    try:
        size = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
    except Exception:
        db.rollback()
        return None
    return _item("database", "ฐานข้อมูล", int(size or 0), None, "bytes", "-", source="system")


def snapshot(db: Session, refresh: bool = False) -> list[dict]:
    items = [_line_item(refresh), _email_item(db, refresh), _ai_item(db), _disk_item(), _db_item(db),
             _memory_item(), _cpu_item(), _redis_item(), *_backup_items()]
    return [i for i in items if i is not None]


def chart_series() -> list[str]:
    """แท็บของกราฟ 30 วัน — เฉพาะบริการที่เปิดใช้"""
    series = ["ai"]
    if settings.smtp_configured:
        series.append("email")
    if settings.line_enabled:
        series.append("line")
    return series


# ---------------------------------------------------------------- แจ้งเตือนแอดมิน

_claims: dict[str, float] = {}
_claims_lock = threading.Lock()


def _claim(key: str, ttl: int = 2 * 24 * 3600) -> bool:
    """จองสิทธิ์ส่งแจ้งเตือน (ครั้งเดียวต่อ key) — Redis SET NX หรือหน่วยความจำ"""
    r = get_redis()
    if r is not None:
        return bool(r.set(f"quota:alert:{key}", b"1", nx=True, ex=ttl))
    now = time.monotonic()
    with _claims_lock:
        if _claims.get(key, 0) > now:
            return False
        _claims[key] = now + ttl
        return True


def reset_for_testing() -> None:
    clear_cache()
    with _claims_lock:
        _claims.clear()


def _fmt(value, unit) -> str:
    if value is None:
        return "-"
    if unit == "bytes":
        for suffix in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024:
                return f"{value:.1f} {suffix}" if suffix != "B" else f"{int(value)} B"
            value /= 1024
        return f"{value:.1f} PB"
    return f"{int(value):,} {unit}"


def alert_message(item: dict) -> Optional[str]:
    if item.get("alert"):
        return item["alert"]
    if item["status"] in ("warn", "full"):
        level = "เต็มแล้ว" if item["status"] == "full" else f"ใช้ไป {item['percent']:g}%"
        return (f"⚠️ โควต้า {item['name']} {level} "
                f"({_fmt(item['used'], item['unit'])} จาก {_fmt(item['limit'], item['unit'])})")
    if item["status"] == "error" or item.get("error"):
        return f"⚠️ {item['name']}: {item['error']}"
    return None


def _notify_admins(db: Session, message: str, details: list[str]) -> int:
    from app.services import line_service, mailer

    url = f"{settings.FRONTEND_URL.rstrip('/')}/admin"
    admins = db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True)).all()
    for admin in admins:
        lines = [message, *details, "", f"ดูรายละเอียด: {url}"]
        mail = mailer.Mail(to=admin.email, subject=message[:150], text="\n".join(lines),
                           html="".join(f"<p>{_esc(x)}</p>" for x in lines if x))
        if line_service.uses_line(admin):
            card = line_service.signing_message("sign_overdue", message, details, url, "เปิดหน้าโควต้า")
            line_service.push(admin.line_user_id, [card], fallback=lambda m=mail: mailer.send(m))
        else:
            mailer.send(mail)
    return len(admins)


def _esc(value: str) -> str:
    import html

    return html.escape(value)


def check_and_alert(db: Session) -> int:
    """ตรวจโควต้า (ดึง API ใหม่) แล้วแจ้งแอดมิน — แต่ละบริการ/สถานะ วันละไม่เกิน 1 ครั้ง คืนจำนวนที่แจ้ง"""
    sent = 0
    for item in snapshot(db, refresh=True):
        message = alert_message(item)
        if not message:
            continue
        kind = "quota" if item["status"] in ("warn", "full") else "error"
        if not _claim(f"{item['key']}:{kind}:{today().isoformat()}"):
            continue
        details = [x for x in (item.get("note"),) if x]
        logger.warning("แจ้งแอดมิน: %s", message)
        _notify_admins(db, message, details)
        sent += 1
    return sent
