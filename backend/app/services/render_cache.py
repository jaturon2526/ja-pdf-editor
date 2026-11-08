"""cache ภาพหน้าเอกสารที่เรนเดอร์แล้ว (GET /pdf/{sid}/page/{n}) — เลื่อนกลับไปหน้าเดิม/ภาพย่อ/หลายแท็บไม่ต้องเรนเดอร์ซ้ำ

key ผูกกับ "รุ่น" ของเอกสาร — แก้ไขแล้ว key เปลี่ยนเอง ไม่ต้องลบ cache:
- โหมด Redis (หลาย worker): รุ่น = session._seen_version (เลข session:{sid}:ver ที่ทุก worker เห็นตรงกัน)
  เก็บใน Redis อายุ TTL วินาที (maxmemory-policy volatile-lru ลบตัวเก่าเองเมื่อเต็ม)
- ไม่มี Redis (worker เดียว): รุ่น = session._render_rev + id(doc) เก็บในหน่วยความจำ จำกัด MAX_LOCAL_BYTES
ไม่ cache ตอนมีการแก้ไขที่ยังไม่ sync (session._doc_dirty) — รุ่นยังไม่ขยับ อาจชนกับภาพของสถานะอื่น"""
from __future__ import annotations

import threading
from collections import OrderedDict

TTL = 600
MAX_LOCAL_BYTES = 96 * 1024 * 1024

_local: "OrderedDict[str, bytes]" = OrderedDict()
_local_bytes = 0
_lock = threading.Lock()


def _redis():
    from app.core.session import RedisSessionManager, session_manager

    if isinstance(session_manager, RedisSessionManager):
        return session_manager._redis
    return None


def key_for(session, page: int, zoom: float, fmt: str) -> str | None:
    if session._doc_dirty or session.doc is None:
        return None
    z = f"{zoom:.3f}"
    if _redis() is not None:
        return f"render:{session.session_id}:{session._seen_version}:{page}:{z}:{fmt}"
    return f"render:{session.session_id}:{session._render_rev}:{id(session.doc)}:{page}:{z}:{fmt}"


def get(key: str | None) -> bytes | None:
    if not key:
        return None
    r = _redis()
    if r is not None:
        try:
            return r.get(key)
        except Exception:
            return None
    with _lock:
        data = _local.get(key)
        if data is not None:
            _local.move_to_end(key)
        return data


def put(key: str | None, data: bytes) -> None:
    global _local_bytes
    if not key or not data:
        return
    r = _redis()
    if r is not None:
        try:
            r.set(key, data, ex=TTL)
        except Exception:
            pass
        return
    with _lock:
        old = _local.pop(key, None)
        if old is not None:
            _local_bytes -= len(old)
        _local[key] = data
        _local_bytes += len(data)
        while _local_bytes > MAX_LOCAL_BYTES and _local:
            _, dropped = _local.popitem(last=False)
            _local_bytes -= len(dropped)
