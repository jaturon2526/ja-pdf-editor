"""access token ใน HttpOnly cookie (SEC-04) — JavaScript อ่าน token ไม่ได้ ถึงหน้าเว็บมีช่อง XSS ก็ขโมยไปใช้ที่อื่นไม่ได้

- `ja_session` = access token (JWT เดิม) · HttpOnly · SameSite=Lax · Secure เมื่อเว็บเป็น https
- `ja_csrf` = ค่าสุ่มที่ JavaScript อ่านได้ — คำขอที่แก้ข้อมูล (ไม่ใช่ GET/HEAD/OPTIONS) ที่ยืนยันตัวด้วย cookie ต้องส่ง
  ค่าเดียวกันมาใน header `X-CSRF-Token` (double-submit: เว็บอื่นอ่าน cookie ของเราไม่ได้ จึงปลอมคำขอไม่ได้)
  — SameSite=Lax กันอีกชั้นอยู่แล้ว · หน้าเว็บใช้ "มี ja_csrf" เป็นสัญญาณว่า login อยู่ (ตัวจริงตรวจที่ /auth/me)
- `Authorization: Bearer` ยังใช้ได้เหมือนเดิม (load test, Swagger, สคริปต์) และไม่ต้องมี CSRF token
- หน้าเว็บขอแบบ cookie ด้วย header `X-Auth-Mode: cookie` ตอน login → `AuthCookieMiddleware` ย้าย access_token จาก
  body ไปใส่ cookie (ครอบทุกทางที่ออก token: รหัสผ่าน / Google / Passkey / LINE) ไม่ต้องแก้ทีละ route
"""
from __future__ import annotations

import hmac
import json
import secrets

from fastapi import HTTPException, Request
from starlette.responses import Response

from app.core.config import settings

SESSION_COOKIE = "ja_session"
CSRF_COOKIE = "ja_csrf"
CSRF_HEADER = "x-csrf-token"
MODE_HEADER = "x-auth-mode"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def cookie_secure() -> bool:
    """AUTH_COOKIE_SECURE: auto (ดีฟอลต์ — https ตาม FRONTEND_URL) | true | false"""
    mode = (settings.AUTH_COOKIE_SECURE or "auto").strip().lower()
    if mode in ("1", "true", "yes", "on"):
        return True
    if mode in ("0", "false", "no", "off"):
        return False
    return settings.FRONTEND_URL.lower().startswith("https://")


def set_auth_cookies(response: Response, token: str) -> None:
    from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES

    max_age = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    secure = cookie_secure()
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, path="/", httponly=True, secure=secure,
                        samesite="lax")
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), max_age=max_age, path="/", httponly=False,
                        secure=secure, samesite="lax")


def clear_auth_cookies(response: Response) -> None:
    secure = cookie_secure()
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", httponly=False, secure=secure, samesite="lax")


def bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer " and auth[7:].strip():
        return auth[7:].strip()
    return None


def csrf_ok(request: Request) -> bool:
    if request.method.upper() in SAFE_METHODS:
        return True
    expected = request.cookies.get(CSRF_COOKIE) or ""
    sent = request.headers.get(CSRF_HEADER) or ""
    return bool(expected) and hmac.compare_digest(expected, sent)


def request_token(request: Request, *, enforce_csrf: bool = True) -> str | None:
    """token ของคำขอนี้: Bearer ก่อน แล้วค่อย cookie (cookie + คำขอที่แก้ข้อมูล ต้องผ่าน CSRF — ไม่ผ่าน = 403)"""
    token = bearer_token(request)
    if token:
        return token
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    if not csrf_ok(request):
        if enforce_csrf:
            raise HTTPException(status_code=403, detail="คำขอไม่ผ่านการตรวจความปลอดภัย (CSRF) — รีเฟรชหน้าแล้วลองใหม่")
        return None
    return token


class AuthCookieMiddleware:
    """คำขอที่มี `X-Auth-Mode: cookie` และคำตอบ JSON 2xx มี access_token → ย้าย token ไปใส่ cookie, ตัดออกจาก body"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _wants_cookie(scope):
            await self.app(scope, receive, send)
            return
        start: dict | None = None
        chunks: list[bytes] = []

        async def capture(message):
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            await _send_rewritten(send, start, b"".join(chunks))

        await self.app(scope, receive, capture)


def _wants_cookie(scope) -> bool:
    for name, value in scope.get("headers") or ():
        if name == MODE_HEADER.encode() and value.strip().lower() == b"cookie":
            return True
    return False


async def _send_rewritten(send, start: dict, body: bytes) -> None:
    headers = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"]
    content_type = next((v for k, v in headers if k.lower() == b"content-type"), b"")
    if 200 <= start["status"] < 300 and content_type.startswith(b"application/json"):
        try:
            data = json.loads(body or b"null")
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("access_token"), str):
            cookies = Response()
            set_auth_cookies(cookies, data.pop("access_token"))
            data["token_type"] = "cookie"
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers += [(k, v) for k, v in cookies.raw_headers if k.lower() == b"set-cookie"]
    headers.append((b"content-length", str(len(body)).encode()))
    await send({**start, "headers": headers})
    await send({"type": "http.response.body", "body": body})
