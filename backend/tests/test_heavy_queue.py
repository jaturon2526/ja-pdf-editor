"""คิวงานหนัก (app/core/heavy.py): จำกัดงานพร้อมกันต่อ worker · คิวเต็ม/รอนานตอบ 503 · ซ้อนกันไม่ติดตาย"""
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core import heavy
from app.core.config import settings
from app.core.heavy import ServerBusyError, heavy_slot, run_in_slot_context


@pytest.fixture
def limits(monkeypatch):
    def set_(slots=1, queue=8, timeout=5.0):
        monkeypatch.setattr(settings, "HEAVY_JOBS_PER_WORKER", slots)
        monkeypatch.setattr(settings, "HEAVY_QUEUE_MAX", queue)
        monkeypatch.setattr(settings, "HEAVY_QUEUE_TIMEOUT", timeout)
    set_()
    return set_


def _hold(seconds: float, started: threading.Event):
    with heavy_slot("test"):
        started.set()
        time.sleep(seconds)


def test_limits_concurrency_per_worker(limits):
    limits(slots=2)
    peak, now, lock = [0], [0], threading.Lock()

    def job():
        with heavy_slot("test"):
            with lock:
                now[0] += 1
                peak[0] = max(peak[0], now[0])
            time.sleep(0.05)
            with lock:
                now[0] -= 1

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda _: job(), range(8)))
    assert peak[0] == 2
    assert heavy.stats()["running"] == 0 and heavy.stats()["waiting"] == 0


def test_queue_full_rejects_immediately(limits):
    limits(slots=1, queue=0)
    started = threading.Event()
    t = threading.Thread(target=_hold, args=(0.5, started))
    t.start()
    started.wait(2)
    t0 = time.monotonic()
    with pytest.raises(ServerBusyError), heavy_slot("test"):
        pass
    assert time.monotonic() - t0 < 0.2
    t.join()


def test_wait_timeout(limits):
    limits(slots=1, queue=4, timeout=0.2)
    started = threading.Event()
    t = threading.Thread(target=_hold, args=(1.0, started))
    t.start()
    started.wait(2)
    with pytest.raises(ServerBusyError, match="รอคิวนาน"), heavy_slot("test"):
        pass
    t.join()
    with heavy_slot("test"):  # ว่างแล้วได้ช่องทันที
        pass


def test_nested_and_child_threads_do_not_deadlock(limits):
    limits(slots=1, timeout=1.0)
    with heavy_slot("outer"):
        with heavy_slot("inner"):
            pass
        with ThreadPoolExecutor(2) as ex:
            futs = [ex.submit(run_in_slot_context(lambda: heavy_slot("child").__enter__() or "ok")) for _ in range(2)]
            assert [f.result(timeout=3) for f in futs] == ["ok", "ok"]


@pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")
def test_compress_returns_503_when_queue_full(client, make_user, limits):
    from tests.test_compress import _pdf
    limits(slots=1, queue=0)
    headers = make_user()[1]
    sid = client.post("/pdf/upload", headers=headers, files={"file": ("t.pdf", _pdf(), "application/pdf")}).json()["session_id"]
    started = threading.Event()
    t = threading.Thread(target=_hold, args=(1.0, started))
    t.start()
    started.wait(2)
    r = client.post(f"/pdf/{sid}/compress", headers=headers, json={"profile": "screen"})
    t.join()
    assert r.status_code == 503, r.text
    assert "ลองใหม่" in r.json()["detail"] and r.headers.get("retry-after") == "30"
    assert client.post(f"/pdf/{sid}/compress", headers=headers, json={"profile": "screen"}).status_code == 200
