"""ตัวกลางเรียก AI หลายค่าย — งานที่ใช้ AI (แก้คำไทยตอนแปลง PDF→Word, OCR คัดลอกพื้นที่) เรียกผ่านโมดูลนี้เท่านั้น

ค่ายที่รองรับ (AI_PROVIDER / ที่ผู้ใช้เลือกในหน้า "API Key สำหรับ AI"):
- gemini     Google Gemini (แพ็กเกจ google-genai — ดู gemini_client.py)
- anthropic  Anthropic Claude (Messages API — https://api.anthropic.com/v1/messages)
- openai     OpenAI และ API แบบเดียวกัน (Chat Completions): Azure OpenAI (endpoint /openai/v1), vLLM, Ollama,
             LiteLLM หรือ gateway ขององค์กร — ตั้ง base_url ได้

Anthropic/OpenAI เรียกผ่าน HTTP ตรง (urllib) ไม่เพิ่ม SDK — คำขอเดียวต่องาน ไม่ต้องการ connection pool

ค่าของระบบ: AI_PROVIDER + AI_API_KEY (+ AI_MODEL, AI_BASE_URL) — ไม่ตั้ง AI_PROVIDER = gemini กับ GEMINI_API_KEY (ค่าเดิม)
ค่าของผู้ใช้: users.ai_provider / ai_model / ai_base_url + encrypted_gemini_key (ชื่อคอลัมน์เดิม เก็บ key ของทุกค่าย)
"""
from __future__ import annotations

import base64
import io
import ipaddress
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("ai_client")

PROVIDERS: dict[str, str] = {
    "gemini": "Google Gemini",
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI / API แบบ OpenAI",
}
# รุ่นเริ่มต้นเมื่อไม่ได้ตั้ง model — รุ่นเร็ว/ราคาถูกของแต่ละค่าย (งานแก้คำ + OCR ไม่ต้องใช้รุ่นใหญ่)
DEFAULT_MODELS = {"anthropic": "claude-haiku-5-5"}
ANTHROPIC_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_BASE = "https://api.openai.com/v1"
REQUEST_TIMEOUT = 120  # วินาที
MAX_OUTPUT_TOKENS = 8192
_ERROR_DETAIL_CHARS = 300


class AINotConfigured(RuntimeError):
    """ไม่มีค่าตั้งค่าที่ใช้ได้ (ไม่มี key / ไม่ได้เลือกรุ่นของค่ายที่ต้องระบุรุ่น)"""


class AIError(RuntimeError):
    """ผู้ให้บริการตอบกลับเป็นข้อผิดพลาด — status = HTTP status (ถ้ามี)"""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status
        self.code = status


@dataclass(frozen=True)
class AIConfig:
    provider: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    source: str = "system"  # system | personal

    @property
    def label(self) -> str:
        return PROVIDERS.get(self.provider, self.provider)


def normalize_provider(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    aliases = {"claude": "anthropic", "google": "gemini", "azure": "openai", "openai-compatible": "openai"}
    v = aliases.get(v, v)
    return v if v in PROVIDERS else ""


# ---------------------------------------------------------------- ค่าตั้งค่า


def system_config() -> Optional[AIConfig]:
    """AI ของระบบ (key องค์กร) — None ถ้าไม่ได้ตั้ง"""
    provider = normalize_provider(settings.AI_PROVIDER) or "gemini"
    key = settings.AI_API_KEY or (settings.GEMINI_API_KEY if provider == "gemini" else "") or ""
    base_url = (settings.AI_BASE_URL or "").strip()
    # OpenAI-compatible ในเครือข่ายองค์กร (vLLM/Ollama) อาจไม่ใช้ key — ต้องมี base_url แทน
    if not key and not (provider == "openai" and base_url):
        return None
    return AIConfig(provider, key, (settings.AI_MODEL or "").strip(), base_url, "system")


def user_config(user) -> Optional[AIConfig]:
    """key ส่วนตัวของผู้ใช้ — None ถ้าไม่ได้ตั้ง / ถอดรหัสไม่ได้"""
    encrypted = getattr(user, "encrypted_gemini_key", None) if user is not None else None
    if not encrypted:
        return None
    from app.core.crypto import decrypt_api_key

    try:
        key = decrypt_api_key(encrypted, user)
    except Exception:
        logger.warning("ถอดรหัส API key ของผู้ใช้ %s ไม่ได้", getattr(user, "id", None))
        return None
    if not key:
        return None
    provider = normalize_provider(getattr(user, "ai_provider", None)) or "gemini"  # key เดิมก่อนมีตัวเลือกค่าย = Gemini
    base_url = (getattr(user, "ai_base_url", None) or "").strip()
    if key == "-":  # OpenAI-compatible ที่ไม่ใช้ key (ดู routes_auth.update_api_key)
        if not base_url:
            return None
        key = ""
    return AIConfig(provider, key, (getattr(user, "ai_model", None) or "").strip(), base_url, "personal")


def personal_config(user) -> Optional[AIConfig]:
    """key ส่วนตัวที่ใช้ได้จริง — None ถ้าผู้ดูแลปิด AI_USER_KEYS_ENABLED หรือผู้ใช้ไม่ได้ตั้ง"""
    return user_config(user) if settings.AI_USER_KEYS_ENABLED else None


def available_for(user) -> bool:
    """ผู้ใช้คนนี้มี AI ให้ใช้ไหม (AI ของระบบ หรือ key ส่วนตัว) — ไม่มี = ปิดฟีเจอร์ AI ทั้งหมด (หน้าเว็บซ่อน
    ตัวเลือก/กล่องโควต้า, งานแปลงใช้ตัวจัดรูปในเครื่องโดยไม่แจ้งว่า "AI ขัดข้อง")"""
    return bool(system_config() or personal_config(user))


def resolve_model(cfg: AIConfig) -> str:
    if cfg.model:
        return cfg.model
    if cfg.provider == "gemini":
        from app.services import gemini_client

        return gemini_client.latest_flash_model(cfg.api_key)
    if cfg.provider in DEFAULT_MODELS:
        return DEFAULT_MODELS[cfg.provider]
    raise AINotConfigured("ต้องระบุชื่อรุ่น (model) สำหรับ API แบบ OpenAI")


def validate_base_url(url: str, *, personal: bool) -> str:
    """ตรวจ base_url — ของผู้ใช้: https เท่านั้น และห้ามชี้เข้าเครือข่ายภายใน/เครื่องตัวเอง (กันใช้เซิร์ฟเวอร์ยิงเข้า
    ระบบภายใน) ยกเว้นโฮสต์ใน AI_PRIVATE_HOSTS · ของระบบ (ผู้ดูแลตั้ง): http ได้ (เช่น vLLM ในวงภายใน)"""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("URL ไม่ถูกต้อง — ต้องขึ้นต้นด้วย https://")
    if not personal:
        return url
    host = parsed.hostname.lower()
    allowed = {h.strip().lower() for h in (settings.AI_PRIVATE_HOSTS or "").split(",") if h.strip()}
    if host in allowed:
        return url
    if parsed.scheme != "https":
        raise ValueError("URL ของ API ต้องเป็น https://")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"หาเซิร์ฟเวอร์ {host} ไม่เจอ") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError(f"{host} อยู่ในเครือข่ายภายใน — ให้ผู้ดูแลเพิ่มใน AI_PRIVATE_HOSTS ก่อน")
    return url


# ---------------------------------------------------------------- เรียกใช้


def generate(cfg: AIConfig, prompt: str, image: Any = None, *, model: Optional[str] = None,
             max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
    """ส่ง prompt (+ รูป PIL.Image ไม่บังคับ) คืนข้อความคำตอบ (strip แล้ว)"""
    model = model or resolve_model(cfg)
    if cfg.source == "personal" and cfg.base_url and cfg.provider != "gemini":
        validate_base_url(cfg.base_url, personal=True)  # ตรวจซ้ำตอนเรียก (DNS อาจเปลี่ยนหลังบันทึก)
    if cfg.provider == "gemini":
        from app.services import gemini_client

        return gemini_client.generate_text(cfg.api_key, model, [prompt, image] if image is not None else prompt)
    if cfg.provider == "anthropic":
        return _anthropic(cfg, model, prompt, image, max_tokens)
    if cfg.provider == "openai":
        return _openai(cfg, model, prompt, image, max_tokens)
    raise AINotConfigured(f"ไม่รู้จักผู้ให้บริการ AI: {cfg.provider}")


def is_rate_limited(exc: Exception) -> bool:
    """โควต้าเต็ม / ถูกจำกัดอัตรา / ผู้ให้บริการแน่น — ควรรอแล้วลองใหม่"""
    code = getattr(exc, "status", None) or getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)
    return code in (429, 529) or "429" in text or "RESOURCE_EXHAUSTED" in text or "overloaded" in text.lower()


def test_config(cfg: AIConfig) -> str:
    """ลองเรียกจริงด้วยคำถามสั้นๆ — คืนชื่อรุ่นที่ใช้ (raise ถ้าใช้ไม่ได้)"""
    model = resolve_model(cfg)
    # สำเร็จ = เรียกได้โดยไม่มีข้อผิดพลาด (รุ่นที่ "คิดก่อนตอบ" อาจใช้ token หมดก่อนมีข้อความ — ไม่ถือว่าผิด)
    generate(cfg, "Reply with the single word OK.", model=model, max_tokens=256)
    return model


def friendly_error(exc: Exception) -> str:
    """ข้อความสั้นสำหรับผู้ใช้ (ไม่รวม key)"""
    status = getattr(exc, "status", None)
    if isinstance(exc, AINotConfigured):
        return str(exc)
    if status in (401, 403):
        return "API key ไม่ถูกต้อง หรือไม่มีสิทธิ์ใช้รุ่นนี้"
    if status == 404:
        return "ไม่พบรุ่น (model) หรือ URL ของ API — ตรวจชื่อรุ่น/URL"
    if is_rate_limited(exc):
        return "ผู้ให้บริการจำกัดการใช้งาน/เครดิตหมด — ลองใหม่ภายหลัง"
    msg = str(exc) or exc.__class__.__name__
    return msg[:_ERROR_DETAIL_CHARS]


# ---------------------------------------------------------------- HTTP


def _png_b64(image: Any) -> str:
    buf = io.BytesIO()
    img = image.convert("RGB") if getattr(image, "mode", "RGB") not in ("RGB", "L") else image
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """ไม่ตาม redirect — กัน URL ภายนอกส่งต่อไปเครือข่ายภายใน (API ของ AI ไม่ redirect อยู่แล้ว)"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _post_json(url: str, headers: dict, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"content-type": "application/json", "accept": "application/json", **headers})
    try:
        with _opener.open(req, timeout=REQUEST_TIMEOUT) as resp:  # noqa: S310 (URL ตรวจแล้ว)
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace") or "{}")
            err = payload.get("error")
            detail = err.get("message", "") if isinstance(err, dict) else str(err or payload.get("message", ""))
        except Exception:
            pass
        raise AIError(f"HTTP {exc.code}: {detail[:_ERROR_DETAIL_CHARS]}".strip(), exc.code) from None
    except urllib.error.URLError as exc:
        raise AIError(f"ติดต่อผู้ให้บริการ AI ไม่ได้: {exc.reason}") from None


def _anthropic(cfg: AIConfig, model: str, prompt: str, image: Any, max_tokens: int) -> str:
    content: list[dict] = []
    if image is not None:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _png_b64(image)}})
    content.append({"type": "text", "text": prompt})
    base = (cfg.base_url or ANTHROPIC_BASE).rstrip("/")
    url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
    data = _post_json(url, {"x-api-key": cfg.api_key, "anthropic-version": ANTHROPIC_VERSION},
                      {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]})
    parts = [b.get("text", "") for b in data.get("content", []) if isinstance(b, dict) and b.get("type") == "text"]
    return "".join(parts).strip()


def _openai(cfg: AIConfig, model: str, prompt: str, image: Any, max_tokens: int) -> str:
    if image is not None:
        content: Any = [{"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_png_b64(image)}"}}]
    else:
        content = prompt
    url = (cfg.base_url or OPENAI_BASE).rstrip("/") + "/chat/completions"
    headers = {}
    if cfg.api_key:
        # Bearer = OpenAI และ gateway ส่วนใหญ่ · api-key = Azure OpenAI (endpoint /openai/v1)
        headers = {"authorization": f"Bearer {cfg.api_key}", "api-key": cfg.api_key}
    body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
    try:
        data = _post_json(url, headers, body)
    except AIError as exc:
        # รุ่นใหม่ของ OpenAI/Azure ไม่รับ max_tokens (ต้องใช้ max_completion_tokens) — ลองอีกครั้ง
        if exc.status != 400 or "max_tokens" not in str(exc):
            raise
        body.pop("max_tokens")
        body["max_completion_tokens"] = max_tokens
        data = _post_json(url, headers, body)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    text = message.get("content") or ""
    if isinstance(text, list):  # บาง gateway คืนเป็นส่วนๆ
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    return str(text).strip()
