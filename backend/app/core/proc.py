"""เรียกโปรแกรมภายนอกแบบมีเวลาจำกัด และฆ่าทั้ง process group เมื่อหมดเวลา

subprocess.run(timeout=...) ฆ่าแค่ process แรก — LibreOffice (soffice → soffice.bin) และโปรแกรมที่แตก process ลูก
จะเหลือลูกค้างกินคิวงานหนัก/CPU ต่อ จึงเริ่ม process ใน session ใหม่ (start_new_session=True) แล้ว os.killpg ทั้งกลุ่ม
"""
from __future__ import annotations

import os
import signal
import subprocess


def run_killable(cmd: list[str], *, timeout: float, check: bool = False, input=None, text: bool = False,
                 env: dict | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """เหมือน subprocess.run(cmd, capture_output=True, ...) — หมดเวลา: ฆ่าทั้งกลุ่มแล้ว raise subprocess.TimeoutExpired"""
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text, env=env, cwd=cwd,
                            start_new_session=True)
    try:
        stdout, stderr = proc.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr) from None
    except BaseException:
        _kill_group(proc)
        proc.wait()
        raise
    finally:
        # process ลูกที่ยังค้างหลังตัวหลักจบ (เช่น LibreOffice ทิ้ง soffice.bin) — ปิดให้หมด
        if proc.returncode is not None:
            _kill_group(proc, quiet=True)
    if check and proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _kill_group(proc: subprocess.Popen, quiet: bool = False) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    except OSError:
        if not quiet:
            proc.kill()
