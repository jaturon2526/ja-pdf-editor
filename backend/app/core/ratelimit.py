"""จำกัดความถี่คำขอที่อ่อนไหว — กันเดารหัสผ่าน (login) และกันยิงอีเมลรัว ๆ (ลืมรหัสผ่าน / ส่งอีเมลยืนยันซ้ำ / สมัคร)

นับแบบหน้าต่างเวลาคงที่ (fixed window): key → จำนวนครั้ง หมดอายุเมื่อครบหน้าต่าง
- มี Redis → นับใน Redis (ทุก worker/pod เห็นตัวเลขเดียวกัน) key `rl:<ชื่อ>:<ค่า>`
- ไม่มี Redis → นับในหน่วยความจำของ process (โหมด worker เดียว / เทสต์)

ใช้คู่กับ nginx `limit_req` (frontend/nginx.conf) ที่จำกัดความถี่ต่อ IP ชั้นนอก — ชั้นนี้จำกัด "ต่อบัญชี"
ซึ่ง nginx ทำไม่ได้ และนับเฉพาะครั้งที่ผิด (login ถูกไม่ถูกนับ ผู้ใช้จริงไม่โดนล็อกเพราะเข้าบ่อย)
"""
from __future__ import annotations

import hashlib
import ipaddress
import threading
import time

from fastapi import HTTPException, Request

from app.core.redis_client import get_redis

_mem: dict[str, tuple[int, float]] = {}
_mem_lock = threading.Lock()


def _key(name: str, ident: str) -> str:
    # ไม่เก็บอีเมล/IP ตรง ๆ ใน Redis
    return f"rl:{name}:{hashlib.sha256(ident.strip().lower().encode()).hexdigest()[:32]}"


def count(name: str, ident: str) -> tuple[int, int]:
    """(จำนวนครั้งในหน้าต่างปัจจุบัน, วินาทีที่เหลือก่อนรีเซ็ต)"""
    key = _key(name, ident)
    r = get_redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.get(key)
            pipe.ttl(key)
            n, ttl = pipe.execute()
            return int(n or 0), max(int(ttl or 0), 0)
        except Exception:  # noqa: BLE001 — Redis ล่มไม่ควรทำให้ login ไม่ได้
            return 0, 0
    with _mem_lock:
        n, until = _mem.get(key, (0, 0.0))
        now = time.monotonic()
        if until <= now:
            return 0, 0
        return n, int(until - now) + 1


def hit(name: str, ident: str, window: int) -> int:
    """นับเพิ่ม 1 ครั้ง คืนจำนวนหลังนับ (ครั้งแรกของหน้าต่างตั้งเวลาหมดอายุ = window วินาที)"""
    key = _key(name, ident)
    r = get_redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            n, _ = pipe.execute()
            return int(n)
        except Exception:  # noqa: BLE001
            return 0
    with _mem_lock:
        now = time.monotonic()
        n, until = _mem.get(key, (0, 0.0))
        if until <= now:
            n, until = 0, now + window
        _mem[key] = (n + 1, until)
        if len(_mem) > 50_000:  # กันหน่วยความจำโต — ทิ้งที่หมดอายุ
            for k in [k for k, (_, u) in _mem.items() if u <= now]:
                _mem.pop(k, None)
        return n + 1


def reset(name: str, ident: str) -> None:
    key = _key(name, ident)
    r = get_redis()
    if r is not None:
        try:
            r.delete(key)
        except Exception:  # noqa: BLE001
            pass
        return
    with _mem_lock:
        _mem.pop(key, None)


def _minutes(seconds: int) -> int:
    return max(1, (seconds + 59) // 60)


def too_many(message: str, retry_after: int) -> HTTPException:
    return HTTPException(status_code=429, detail=f"{message} กรุณาลองใหม่ในอีก {_minutes(retry_after)} นาที",
                         headers={"Retry-After": str(max(retry_after, 1))})


def ensure_below(name: str, ident: str, limit: int, message: str) -> None:
    """ยังไม่ถึงเพดาน → ผ่าน · ถึงแล้ว → 429 พร้อมเวลาที่ต้องรอ"""
    if not ident:
        return
    n, ttl = count(name, ident)
    if n >= limit:
        raise too_many(message, ttl)


def client_ip(request: Request) -> str:
    """IP ผู้ใช้: nginx ของเราตั้ง X-Real-IP เป็น IP จริงเสมอ (ทับค่าที่ผู้ใช้ส่งมา) — ไม่มี (เรียกตรง/เทสต์) ใช้ IP ที่ต่อเข้ามา"""
    for raw in (request.headers.get("x-real-ip", ""), request.client.host if request.client else ""):
        try:
            return str(ipaddress.ip_address(raw.strip()))
        except ValueError:
            continue
    return ""
