"""ตัวกลางเรียก Gemini ผ่านแพ็กเกจ google-genai (แทน google-generativeai ที่เลิกซัพพอร์ตแล้ว)

ทำไมต้องมีโมดูลนี้:
- SDK เดิมใช้ `genai.configure(api_key=...)` ซึ่งเป็น global state ของทั้ง process — ตอน OCR ด้วย key
  ส่วนตัวของผู้ใช้คนหนึ่ง key นั้นจะค้างเป็น key ของทั้งแอป ทำให้ request ของผู้ใช้คนอื่น (รวมถึงงานที่ตั้งใจ
  ใช้ system key) ไปใช้ key ของคนอื่นแทน
- SDK ใหม่ใช้ `genai.Client(api_key=...)` แยกตาม key — โมดูลนี้ cache client ไว้ต่อ key และไม่มี global state
"""
from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from typing import Any, Optional

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger("gemini_client")

# timeout ต่อ request (มิลลิวินาที) — กัน request ค้างจนกิน worker thread
_REQUEST_TIMEOUT_MS = 120_000
# จำนวน client ที่ cache ไว้สูงสุด (ต่อ API key) — แต่ละ client ถือ HTTP connection pool ของตัวเอง
_MAX_CACHED_CLIENTS = 64

# รุ่นที่ใช้เมื่อหารุ่น Flash ล่าสุดจาก API ไม่ได้
DEFAULT_FLASH_MODEL = "gemini-2.5-flash"

_clients: "OrderedDict[str, genai.Client]" = OrderedDict()
_clients_lock = threading.Lock()


class GeminiNotConfigured(RuntimeError):
    """ไม่มี API key ให้ใช้"""


def get_client(api_key: Optional[str]) -> genai.Client:
    """คืน Client ของ API key นี้ (สร้างครั้งแรกแล้ว cache ไว้)"""
    if not api_key:
        raise GeminiNotConfigured("ไม่ได้ตั้งค่า Gemini API key")
    with _clients_lock:
        client = _clients.get(api_key)
        if client is not None:
            _clients.move_to_end(api_key)
            return client
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS))
        _clients[api_key] = client
        while len(_clients) > _MAX_CACHED_CLIENTS:
            _clients.popitem(last=False)
        return client


def system_api_key() -> Optional[str]:
    return settings.GEMINI_API_KEY or None


def generate_text(api_key: Optional[str], model: str, contents: Any) -> str:
    """เรียก generate_content แล้วคืนข้อความ (strip แล้ว) — contents เป็น str หรือ list ของ str/PIL.Image ได้"""
    response = get_client(api_key).models.generate_content(model=model, contents=contents)
    return (response.text or "").strip()


_flash_model_cache: dict[str, str] = {}


def _flash_version(name: str) -> float:
    match = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(match.group(1)) if match else 0.0


def latest_flash_model(api_key: Optional[str]) -> str:
    """หารุ่น Gemini Flash ใหม่สุด (ที่ไม่ใช่ lite/preview/audio/image) จากรายชื่อรุ่นที่ key นี้ใช้ได้
    cache ผลไว้ทั้ง process — ถ้าดึงรายชื่อไม่ได้จะใช้ DEFAULT_FLASH_MODEL"""
    cache_key = "system" if api_key == system_api_key() else "user"
    if cache_key in _flash_model_cache:
        return _flash_model_cache[cache_key]
    try:
        names = []
        for m in get_client(api_key).models.list():
            name = (m.name or "").replace("models/", "")
            if (
                name.startswith("gemini-") and "flash" in name
                and not any(tag in name for tag in ("lite", "preview", "audio", "image", "tts", "live", "exp"))
            ):
                names.append(name)
        if names:
            names.sort(key=_flash_version, reverse=True)
            _flash_model_cache[cache_key] = names[0]
            logger.info("เลือกใช้ Gemini Flash รุ่น %s", names[0])
            return names[0]
    except Exception as exc:
        logger.warning("ดึงรายชื่อรุ่น Gemini ไม่สำเร็จ ใช้ %s แทน: %s", DEFAULT_FLASH_MODEL, exc)
    return DEFAULT_FLASH_MODEL


def is_rate_limited(exc: Exception) -> bool:
    """ข้อผิดพลาดแบบ 429 / quota เต็ม (ควร retry ภายหลัง)"""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code == 429 or "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)


def reset_for_testing() -> None:
    with _clients_lock:
        _clients.clear()
    _flash_model_cache.clear()
