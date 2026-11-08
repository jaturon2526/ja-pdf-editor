"""RedisSessionManager หลาย process (จำลองด้วย manager 2 ตัวที่ใช้ Redis + ดิสก์ร่วมกัน)"""
import shutil
import threading

import fakeredis
import fitz
import pytest

from app.core.config import settings
from app.core.session import RedisSessionManager, SessionBusyError
from tests.conftest import make_pdf_bytes


@pytest.fixture
def pods():
    server = fakeredis.FakeServer()
    a = RedisSessionManager(fakeredis.FakeStrictRedis(server=server))
    b = RedisSessionManager(fakeredis.FakeStrictRedis(server=server))
    return a, b


def _new_session(manager, user_id=1):
    settings.ensure_dirs()
    import uuid

    sid = uuid.uuid4().hex
    original = settings.UPLOAD_DIR / f"{sid}.pdf"
    original.write_bytes(make_pdf_bytes())
    working = settings.WORKING_DIR / f"{sid}.pdf"
    shutil.copyfile(original, working)
    s = manager.create_session(original, working, "doc.pdf", user_id=user_id, session_id=sid)
    s.doc = fitz.open(working)
    s.is_unlocked = True
    with s.lock:
        s.push_history()
    return s


def _rotate(session, angle):
    with session.lock:
        session.doc[0].set_rotation(angle)
        session.mark_dirty()
        session.push_history()


def test_edit_on_one_pod_is_visible_on_other(pods):
    a, b = pods
    sa_ = _new_session(a)
    sb = b.get(sa_.session_id)  # pod B cache ไว้ตั้งแต่ก่อนแก้ไข
    assert sb is not None and sb.user_id == 1

    _rotate(sa_, 90)
    with sb.lock:  # เข้าล็อก → ต้องโหลดสถานะใหม่จาก Redis/ดิสก์
        assert sb.doc[0].rotation == 90
        assert sb.can_undo()
        assert sb.undo()
    with sa_.lock:  # undo ที่ทำบน B ต้องสะท้อนกลับมาที่ A
        assert sa_.doc[0].rotation == 0
        assert sa_.can_redo()


def test_history_survives_trimming_and_reconstruct(pods):
    a, b = pods
    s = _new_session(a)
    for i in range(30):  # เกิน _HISTORY_LIMIT → entry เก่าถูกตัดทิ้ง
        _rotate(s, (i % 4) * 90)
    fresh = b.get(s.session_id)
    with fresh.lock:
        assert len(fresh.history) == len(s.history)
        assert [e.seq for e in fresh.history] == [e.seq for e in s.history]
    keys = {k.decode() for k in a._redis.keys(f"session:{s.session_id}:hist:*")}
    assert len(keys) == len(s.history)  # entry ที่ถูกตัดต้องถูกลบออกจาก Redis ด้วย


def test_lock_is_exclusive_across_pods(pods):
    a, b = pods
    s = _new_session(a)
    other = b.get(s.session_id)
    b.LOCK_WAIT = 0.2
    entered = threading.Event()
    release = threading.Event()

    def hold():
        with s.lock:
            entered.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    entered.wait(5)
    try:
        with pytest.raises(SessionBusyError):
            with other.lock:
                pass
    finally:
        release.set()
        t.join()
    with other.lock:  # ว่างแล้วต้องเข้าได้
        pass


def test_close_removes_keys_everywhere(pods):
    a, b = pods
    s = _new_session(a)
    _rotate(s, 90)
    b.get(s.session_id)
    a.close(s.session_id)
    assert a._redis.keys(f"session:{s.session_id}:*") == []
    assert b.get(s.session_id) is None
