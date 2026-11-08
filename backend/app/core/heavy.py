"""คิวงานหนัก — จำกัดจำนวนโปรเซส Ghostscript / LibreOffice / Tesseract ที่รันพร้อมกันต่อ worker

ทำไม: งานพวกนี้กิน CPU เต็มคอร์ต่องาน ถ้าปล่อยพร้อมกันไม่จำกัด (เช่น 10 คนกดแปลง Word พร้อมกัน) การแสดงหน้า
และการแก้ไขของผู้ใช้คนอื่นจะช้าตามไปด้วย — load test รอบแรก CPU เต็มทั้งเครื่อง (ดู claude/phase-scalability-plan.md)

    with heavy_slot("ghostscript"):
        subprocess.run([...])

- ได้ช่องตามลำดับ (FIFO ของ threading) รอได้ไม่เกิน settings.HEAVY_QUEUE_TIMEOUT วินาที
- คิวยาวเกิน settings.HEAVY_QUEUE_MAX → ServerBusyError ทันที (ไม่ให้เธรดของ server ไปรอคิวกันหมด)
- ซ้อนกันได้: โค้ดที่ถือช่องอยู่แล้วเรียกงานหนักอีกชั้น (หรือแตกเธรดผ่าน run_in_slot_context) ไม่ขอช่องซ้ำ
- นับต่อ worker process (ไม่ใช้ Redis — ไม่มีช่องค้างถ้า process ตาย) รวมทั้งเครื่อง = BACKEND_WORKERS × HEAVY_JOBS_PER_WORKER
"""
from __future__ import annotations

import contextvars
import logging
import threading
import time
from contextlib import contextmanager

from app.core.config import settings

logger = logging.getLogger("heavy")

_held: contextvars.ContextVar[bool] = contextvars.ContextVar("heavy_slot_held", default=False)
_lock = threading.Lock()
_sem: threading.Semaphore | None = None
_sem_size = 0
_state = {"running": 0, "waiting": 0, "rejected": 0, "done": 0}


class ServerBusyError(RuntimeError):
    """งานหนักรอคิวนาน/คิวยาวเกินกำหนด — ตอบ 503 ให้ลองใหม่ภายหลัง"""


def _semaphore() -> threading.Semaphore:
    global _sem, _sem_size
    with _lock:
        if _sem is None or _sem_size != settings.HEAVY_JOBS_PER_WORKER:  # ค่าเปลี่ยน (เช่นในเทสต์) → สร้างใหม่
            _sem_size = settings.HEAVY_JOBS_PER_WORKER
            _sem = threading.Semaphore(_sem_size)
        return _sem


def stats() -> dict:
    """สถานะคิวของ worker นี้ (สำหรับ /health/metrics)"""
    with _lock:
        return {**_state, "slots": settings.HEAVY_JOBS_PER_WORKER}


@contextmanager
def heavy_slot(kind: str = "job"):
    if _held.get():
        yield
        return
    sem = _semaphore()
    started = time.monotonic()
    if not sem.acquire(blocking=False):
        with _lock:
            if _state["waiting"] >= settings.HEAVY_QUEUE_MAX:
                _state["rejected"] += 1
                logger.warning("heavy queue full: reject %s (waiting=%s)", kind, _state["waiting"])
                raise ServerBusyError("ระบบกำลังประมวลผลงานหนักจำนวนมาก กรุณาลองใหม่อีกครั้งในอีกสักครู่")
            _state["waiting"] += 1
        try:
            got = sem.acquire(timeout=settings.HEAVY_QUEUE_TIMEOUT)
        finally:
            with _lock:
                _state["waiting"] -= 1
        if not got:
            with _lock:
                _state["rejected"] += 1
            logger.warning("heavy queue timeout: %s after %.0fs", kind, time.monotonic() - started)
            raise ServerBusyError("ระบบกำลังประมวลผลงานหนักจำนวนมาก รอคิวนานเกินกำหนด กรุณาลองใหม่อีกครั้ง")
    waited = time.monotonic() - started
    if waited > 1:
        logger.info("heavy %s waited %.1fs in queue", kind, waited)
    with _lock:
        _state["running"] += 1
    token = _held.set(True)
    try:
        yield
    finally:
        _held.reset(token)
        with _lock:
            _state["running"] -= 1
            _state["done"] += 1
        sem.release()


def run_in_slot_context(fn):
    """ห่อฟังก์ชันที่จะส่งให้เธรดอื่น (ThreadPoolExecutor) ให้รู้ว่าช่องของงานแม่ถือไว้แล้ว — ไม่ขอช่องซ้ำจนติดตาย"""
    ctx = contextvars.copy_context()
    return lambda *a, **kw: ctx.copy().run(fn, *a, **kw)  # copy ต่อครั้ง — Context เดียวกันเข้าพร้อมกันหลายเธรดไม่ได้
