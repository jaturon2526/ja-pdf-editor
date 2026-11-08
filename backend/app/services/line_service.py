"""แจ้งเตือนการลงนามผ่าน LINE Official Account (Messaging API)

ผูกบัญชี (ไม่ต้องมี LINE Login):
1. ผู้ใช้กด "เชื่อมต่อ LINE" ในหน้าความปลอดภัย → ได้รหัสใช้ครั้งเดียว (อายุ 10 นาที) + ลิงก์/QR ที่เปิดแชท OA พร้อมรหัส
2. ผู้ใช้ส่งรหัสในแชท → LINE ส่ง webhook มาที่ POST /line/webhook (ตรวจ X-Line-Signature ด้วย channel secret)
3. รหัสตรง → บันทึก line_user_id แล้วตอบกลับด้วย reply token (reply ไม่นับโควตา)

ส่งแจ้งเตือน: push message (นับโควตา — แพ็กเกจฟรี 300/เดือน) — นับเองใน Redis ตามเดือนเวลาญี่ปุ่น (LINE ตัดรอบตาม JST)
ถึงเพดาน LINE_MONTHLY_LIMIT / LINE ตอบ error → เรียก fallback (ส่งอีเมลแทน)
ไม่ log ข้อความ/โทเคน — log แค่ชนิดและผลลัพธ์
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.domain import User

logger = logging.getLogger("line")

LINK_CODE_TTL_SECONDS = 600
LINK_CODE_PREFIX = "JA-"
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ไม่มี 0/O/1/I ที่สับสนกัน
_CODE_RE = re.compile(r"JA-?([A-Z2-9]{6})", re.IGNORECASE)
MAX_FAILED_CODES_PER_HOUR = 10

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="line")


class LineApiError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(f"LINE API {status} {message}".strip())
        self.status = status


# ---------------------------------------------------------------- ที่เก็บชั่วคราว (Redis หรือหน่วยความจำ)


class _MemoryStore:
    def __init__(self):
        self._data: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()

    def _alive(self, key):
        item = self._data.get(key)
        if item is None or item[0] < time.monotonic():
            self._data.pop(key, None)
            return None
        return item

    def set(self, key: str, value: bytes, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)

    def pop(self, key: str) -> Optional[bytes]:
        with self._lock:
            item = self._alive(key)
            self._data.pop(key, None)
        return item[1] if item else None

    def incr(self, key: str, ttl: int, amount: int = 1) -> int:
        with self._lock:
            item = self._alive(key)
            value = int(item[1]) + amount if item else amount
            expires = item[0] if item else time.monotonic() + ttl
            self._data[key] = (expires, str(value).encode())
        return value

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            item = self._alive(key)
        return item[1] if item else None

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_memory = _MemoryStore()


def _set(key: str, value: bytes, ttl: int) -> None:
    r = get_redis()
    if r is not None:
        r.set(f"line:{key}", value, ex=ttl)
    else:
        _memory.set(key, value, ttl)


def _pop(key: str) -> Optional[bytes]:
    r = get_redis()
    if r is None:
        return _memory.pop(key)
    pipe = r.pipeline()
    pipe.get(f"line:{key}")
    pipe.delete(f"line:{key}")
    return pipe.execute()[0]


def _incr(key: str, ttl: int, amount: int = 1) -> int:
    r = get_redis()
    if r is None:
        return _memory.incr(key, ttl, amount)
    pipe = r.pipeline()
    pipe.incrby(f"line:{key}", amount)
    pipe.expire(f"line:{key}", ttl, nx=True)
    return int(pipe.execute()[0])


def _get_int(key: str) -> int:
    r = get_redis()
    raw = r.get(f"line:{key}") if r is not None else _memory.get(key)
    return int(raw) if raw else 0


# ---------------------------------------------------------------- เรียก LINE API


def _api(method: str, path: str, body: Optional[dict] = None, timeout: int = 10) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{settings.LINE_API_BASE.rstrip('/')}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {settings.LINE_CHANNEL_ACCESS_TOKEN}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — URL มาจาก config
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read() or b"{}").get("message", "")
        except Exception:
            pass
        raise LineApiError(exc.code, detail) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LineApiError(0, str(exc)) from None
    return json.loads(raw) if raw else {}


# เทสต์แทนที่ตัวนี้เพื่อจำลอง LINE API
call_api: Callable[..., dict] = _api


def reply(reply_token: str, text: str) -> None:
    """ตอบกลับในแชท (ไม่นับโควตา) — ล้มเหลวก็ไม่เป็นไร"""
    if not reply_token:
        return
    try:
        call_api("POST", "/v2/bot/message/reply",
                 {"replyToken": reply_token, "messages": [{"type": "text", "text": text[:5000]}]})
    except LineApiError as exc:
        logger.warning("ตอบกลับ LINE ไม่สำเร็จ: %s", exc)


def fetch_display_name(line_user_id: str) -> Optional[str]:
    try:
        return call_api("GET", f"/v2/bot/profile/{quote(line_user_id)}").get("displayName")
    except LineApiError as exc:
        logger.info("อ่านโปรไฟล์ LINE ไม่สำเร็จ: %s", exc)
        return None


# ---------------------------------------------------------------- โควตา push รายเดือน


def _month_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return "push:" + now.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y%m")


_MONTH_TTL = 40 * 24 * 3600


def pushes_this_month() -> int:
    return _get_int(_month_key())


def _reserve_push() -> bool:
    if _incr(_month_key(), _MONTH_TTL) > settings.LINE_MONTHLY_LIMIT:
        _incr(_month_key(), _MONTH_TTL, -1)
        return False
    return True


def _release_push() -> None:
    _incr(_month_key(), _MONTH_TTL, -1)


def _mark_quota_full() -> None:
    used = pushes_this_month()
    if used < settings.LINE_MONTHLY_LIMIT:
        _incr(_month_key(), _MONTH_TTL, settings.LINE_MONTHLY_LIMIT - used)


def push_now(line_user_id: str, messages: list[dict]) -> bool:
    """ส่ง push ทันที คืน True ถ้าสำเร็จ (False = โควตาเต็ม/LINE ผิดพลาด → ผู้เรียกส่งช่องทางอื่นแทน)"""
    if not settings.line_enabled:
        return False
    if not _reserve_push():
        logger.warning("โควตา LINE เดือนนี้ครบ %s ข้อความแล้ว — ส่งอีเมลแทน", settings.LINE_MONTHLY_LIMIT)
        return False
    try:
        call_api("POST", "/v2/bot/message/push", {"to": line_user_id, "messages": messages})
    except LineApiError as exc:
        if exc.status == 429:
            _mark_quota_full()
            logger.warning("LINE ตอบ 429 (โควตาหมด/ส่งถี่เกิน) — ส่งอีเมลแทน")
        else:
            _release_push()
            logger.warning("ส่ง LINE ไม่สำเร็จ: %s", exc)
        return False
    from app.services import quota_service  # นับรายวันสำหรับกราฟหน้าโควต้า

    quota_service.record(quota_service.LINE)
    return True


def _run_in_background(fn: Callable[[], object]) -> None:
    _executor.submit(fn)


# เทสต์แทนที่ด้วย lambda fn: fn() เพื่อให้ทำงานทันที
run: Callable[[Callable[[], object]], object] = _run_in_background


def push(line_user_id: str, messages: list[dict], fallback: Optional[Callable[[], object]] = None) -> None:
    """ส่งเบื้องหลัง — ไม่สำเร็จแล้วเรียก fallback (เช่น ส่งอีเมล) ไม่ raise"""

    def job():
        try:
            ok = push_now(line_user_id, messages)
        except Exception:  # pragma: no cover
            logger.exception("ส่ง LINE ผิดพลาด")
            ok = False
        if not ok and fallback is not None:
            fallback()

    try:
        run(job)
    except Exception:  # pragma: no cover
        logger.exception("เข้าคิว LINE ไม่สำเร็จ")
        if fallback is not None:
            fallback()


# ---------------------------------------------------------------- ข้อความแจ้งเตือน (Flex)

_COLORS = {"sign_rejected": "#dc2626", "sign_cancelled": "#64748b", "sign_completed": "#16a34a",
           "sign_overdue": "#ea580c"}


def signing_message(kind: str, title: str, details: list[str], url: str, button: str) -> dict:
    color = _COLORS.get(kind, "#2563eb")
    body = [
        {"type": "text", "text": settings.APP_NAME, "size": "xs", "color": "#94a3b8", "weight": "bold"},
        {"type": "text", "text": title[:300], "wrap": True, "weight": "bold", "size": "md", "color": "#0f172a",
         "margin": "md"},
    ]
    for line in details[:4]:
        body.append({"type": "text", "text": line[:200], "wrap": True, "size": "sm", "color": "#475569",
                     "margin": "sm"})
    return {
        "type": "flex",
        "altText": title[:390],
        "contents": {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "contents": body, "paddingAll": "18px"},
            "footer": {"type": "box", "layout": "vertical", "contents": [
                {"type": "button", "style": "primary", "color": color, "height": "sm",
                 "action": {"type": "uri", "label": button[:40], "uri": url}},
            ]},
        },
    }


# ---------------------------------------------------------------- ผูก / ยกเลิกการผูก


def add_friend_url() -> str:
    basic = settings.LINE_OA_BASIC_ID.strip()
    return f"https://line.me/R/ti/p/{quote(basic)}" if basic else ""


def _new_code() -> str:
    return LINK_CODE_PREFIX + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def create_link_code(user: User) -> dict:
    code = _new_code()
    _set(f"link:{code[len(LINK_CODE_PREFIX):]}", str(user.id).encode(), LINK_CODE_TTL_SECONDS)
    basic = settings.LINE_OA_BASIC_ID.strip()
    # เปิดแชท OA พร้อมข้อความ = รหัส (ถ้ายังไม่เป็นเพื่อน LINE จะให้เพิ่มเพื่อนก่อน)
    chat_url = f"https://line.me/R/oaMessage/{quote(basic)}/?{quote(code)}" if basic else ""
    return {"code": code, "expires_in": LINK_CODE_TTL_SECONDS, "chat_url": chat_url, "add_friend_url": add_friend_url(),
            "qr_svg": _qr_svg(chat_url) if chat_url else None}


def _qr_svg(data: str) -> Optional[str]:
    try:
        import segno

        return segno.make(data, error="m").svg_data_uri(scale=6, border=2)
    except Exception:  # pragma: no cover — ไม่มี segno ก็ยังใช้ลิงก์ได้
        logger.warning("สร้าง QR ไม่สำเร็จ", exc_info=True)
        return None


def link(db: Session, user: User, line_user_id: str) -> None:
    # LINE หนึ่งบัญชีผูกได้กับผู้ใช้เดียว — ผูกใหม่ = ย้ายจากบัญชีเดิม
    for other in db.query(User).filter(User.line_user_id == line_user_id, User.id != user.id).all():
        _clear(other)
    db.flush()
    user.line_user_id = line_user_id
    user.line_display_name = fetch_display_name(line_user_id)
    user.line_linked_at = datetime.now(timezone.utc)
    user.line_notifications = True
    db.commit()


def _clear(user: User) -> None:
    user.line_user_id = None
    user.line_display_name = None
    user.line_linked_at = None


def unlink(db: Session, user: User) -> None:
    _clear(user)
    db.commit()


def set_notifications(db: Session, user: User, enabled: bool) -> None:
    user.line_notifications = bool(enabled)
    db.commit()


def status(user: User) -> dict:
    data = {
        "enabled": settings.line_enabled,
        "linked": bool(user.line_user_id),
        "display_name": user.line_display_name,
        "linked_at": user.line_linked_at.isoformat() if user.line_linked_at else None,
        "notifications": bool(user.line_notifications),
        "add_friend_url": add_friend_url(),
        "login": {"enabled": settings.line_login_enabled, "linked": bool(user.line_login_id)},
    }
    if user.is_admin and settings.line_enabled:
        data["quota"] = {"used": pushes_this_month(), "limit": settings.LINE_MONTHLY_LIMIT}
    return data


def uses_line(user: User) -> bool:
    return settings.line_enabled and bool(user.line_user_id) and bool(user.line_notifications)


# ---------------------------------------------------------------- webhook


def verify_signature(body: bytes, signature: str) -> bool:
    if not settings.LINE_CHANNEL_SECRET or not signature:
        return False
    digest = hmac.new(settings.LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature.strip())


HELP_TEXT = ("สวัสดีครับ นี่คือบัญชีแจ้งเตือนของ JA PDF Editor\n"
             "รับแจ้งเตือนการลงนามเอกสารทาง LINE: เข้า ja-pdf.com → เมนูโปรไฟล์ → ความปลอดภัย → "
             "\"เชื่อมต่อ LINE\" แล้วส่งรหัสที่ได้ในแชทนี้")


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return (name[:2] + "***@" + domain) if domain else email


def _handle_text(db: Session, line_user_id: str, text: str, reply_token: str) -> None:
    match = _CODE_RE.search(text.upper())
    if not match:
        reply(reply_token, HELP_TEXT)
        return
    fail_key = f"fail:{line_user_id}"
    if _get_int(fail_key) >= MAX_FAILED_CODES_PER_HOUR:
        reply(reply_token, "ลองรหัสผิดหลายครั้งเกินไป กรุณารอ 1 ชั่วโมงแล้วลองใหม่")
        return
    raw = _pop(f"link:{match.group(1).upper()}")
    user = db.get(User, int(raw)) if raw else None
    if user is None or not user.is_active:
        _incr(fail_key, 3600)
        reply(reply_token, "รหัสไม่ถูกต้องหรือหมดอายุแล้ว (รหัสใช้ได้ 10 นาที) — กด \"เชื่อมต่อ LINE\" ที่หน้าเว็บเพื่อรับรหัสใหม่")
        return
    link(db, user, line_user_id)
    logger.info("ผูก LINE กับผู้ใช้ %s แล้ว", user.id)
    reply(reply_token, f"เชื่อมต่อกับบัญชี {_mask_email(user.email)} เรียบร้อยแล้ว ✅\n"
                       "ต่อไปการแจ้งเตือนการลงนามเอกสารจะส่งมาที่แชทนี้แทนอีเมล\n"
                       "ปิดหรือยกเลิกได้ที่หน้า \"ความปลอดภัย\" บนเว็บ")


def handle_events(db: Session, payload: dict) -> int:
    """ประมวลผล webhook events คืนจำนวนที่จัดการ (events ว่าง = ปุ่ม Verify ใน console)"""
    handled = 0
    for event in payload.get("events") or []:
        source = event.get("source") or {}
        line_user_id = source.get("userId")
        if source.get("type") != "user" or not line_user_id:
            continue
        kind = event.get("type")
        token = event.get("replyToken", "")
        if kind == "follow":
            reply(token, HELP_TEXT)
        elif kind == "unfollow":  # ผู้ใช้บล็อก OA → ส่งไม่ได้แล้ว ยกเลิกการผูก (กลับไปใช้อีเมล)
            for user in db.query(User).filter(User.line_user_id == line_user_id).all():
                _clear(user)
            db.commit()
        elif kind == "message" and (event.get("message") or {}).get("type") == "text":
            _handle_text(db, line_user_id, event["message"].get("text", ""), token)
        else:
            continue
        handled += 1
    return handled


def reset_for_testing() -> None:
    _memory.clear()
