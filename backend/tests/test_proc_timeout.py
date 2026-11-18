"""SEC-03: โปรแกรมภายนอกที่ค้างต้องถูกฆ่าทั้ง process group เมื่อหมดเวลา (ไม่เหลือ process ลูก)"""
import os
import subprocess
import sys
import time

import pytest

from app.core.proc import run_killable


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # zombie ที่รอ reap ถือว่าตายแล้ว
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except FileNotFoundError:
        return False


def test_timeout_kills_whole_process_group(tmp_path):
    pidfile = tmp_path / "child.pid"
    # process แม่แตกลูกที่ sleep ยาว แล้วตัวเองก็รอ — เหมือน soffice → soffice.bin
    code = ("import subprocess,sys,time;"
            f"p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
            f"open({str(pidfile)!r},'w').write(str(p.pid));time.sleep(60)")
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_killable([sys.executable, "-c", code], timeout=1.5)
    assert time.monotonic() - start < 10
    child = int(pidfile.read_text())
    for _ in range(50):
        if not _alive(child):
            break
        time.sleep(0.05)
    assert not _alive(child), "process ลูกยังค้างอยู่"


def test_check_and_output_like_subprocess_run():
    r = run_killable([sys.executable, "-c", "print('ok')"], timeout=10, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok"
    with pytest.raises(subprocess.CalledProcessError) as exc:
        run_killable([sys.executable, "-c", "import sys;sys.stdout.write('E');sys.exit(3)"], timeout=10, check=True)
    assert exc.value.returncode == 3 and exc.value.stdout == b"E"
    r = run_killable([sys.executable, "-c", "import sys;print(sys.stdin.read()[::-1])"], timeout=10, input=b"abc")
    assert r.stdout.strip() == b"cba"
