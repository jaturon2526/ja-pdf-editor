"""
redis_client — จัดการ connection ไปยัง Redis (ถ้ามี)

ถ้าไม่มีการตั้งค่า PDF_REDIS_URL หรือ Redis เชื่อมต่อไม่ได้ get_redis() จะคืน None
และ session_manager จะใช้ InMemorySessionManager (โหมด default ที่ใช้มาตลอด) แทนโดยอัตโนมัติ

ออกแบบให้ fail-safe: ไม่มี Redis ก็ยังใช้งานได้ปกติ แต่จำกัดที่ single instance
"""
import logging

logger = logging.getLogger("redis_client")

_redis_instance = None
_initialized = False


def get_redis():
    """คืน Redis client instance (หรือ None ถ้าไม่ได้ตั้งค่าหรือเชื่อมต่อไม่ได้)"""
    global _redis_instance, _initialized
    if _initialized:
        return _redis_instance
    _initialized = True
    try:
        from app.core.config import settings

        if not settings.REDIS_URL:
            logger.info("PDF_REDIS_URL ไม่ได้ตั้งค่า — ใช้ InMemorySessionManager (single-instance)")
            return None
        import redis  # noqa: PLC0415

        client = redis.from_url(settings.REDIS_URL, decode_responses=False)
        client.ping()  # ทดสอบการเชื่อมต่อจริงก่อน commit
        logger.info("เชื่อมต่อ Redis สำเร็จ: %s", settings.REDIS_URL)
        _redis_instance = client
    except ImportError:
        logger.warning(
            "ไม่พบ library 'redis' — ติดตั้งด้วย: pip install redis>=5.0.0"
            " แล้วรีสตาร์ท server เพื่อใช้งาน multi-instance mode"
        )
    except Exception as exc:
        logger.warning(
            "เชื่อมต่อ Redis ไม่สำเร็จ (%s) — ใช้ InMemorySessionManager แทน"
            " (ยังใช้งานได้ปกติแต่จำกัดที่ single instance)",
            exc,
        )
    return _redis_instance


def reset_for_testing() -> None:
    """เรียกจาก test เท่านั้น — รีเซ็ต singleton เพื่อเริ่มใหม่"""
    global _redis_instance, _initialized
    _redis_instance = None
    _initialized = False
