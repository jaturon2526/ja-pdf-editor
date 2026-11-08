"""Ghostscript กับข้อความไทยจาก Word/LibreOffice (ActualText) — ลดขนาดไฟล์ / PDF/A ต้องคัดลอก/ค้นหาได้เหมือนเดิม"""
import shutil
from pathlib import Path

import fitz
import pytest

from tests.test_file_signature_status import _file_id

FIXTURE = Path(__file__).parent / "fixtures" / "libreoffice_thai.pdf"
needs_gs = pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")


def _text(data: bytes) -> str:
    return "".join(p.get_text() for p in fitz.open("pdf", data))


def test_run_ghostscript_preserves_marked_content(monkeypatch):
    from app.services.pdf_service import optimize

    seen = []
    monkeypatch.setattr(optimize.subprocess, "run", lambda cmd, **kw: seen.append(cmd))
    optimize._run_ghostscript(["gs", "-sDEVICE=pdfwrite", "-sOutputFile=x.pdf", "in.pdf"])
    assert "-dPreserveMarkedContent=true" in seen[0]


@needs_gs
def test_compress_keeps_libreoffice_thai_text(client, make_user, upload):
    _, h = make_user()
    data = FIXTURE.read_bytes()
    fid = _file_id(client, h, upload(h, data, name="letter.pdf"))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=h, json={"action": "compress", "compress_profile": "screen"})
    assert r.status_code == 200, r.text
    if r.json()["status"] == "ok":
        out = client.get(f"/pdf/files/{r.json()['file']['id']}/download", headers=h).content
        assert _text(out) == _text(data)


@needs_gs
def test_pdfa_keeps_libreoffice_thai_text(client, make_user, upload):
    _, h = make_user()
    data = FIXTURE.read_bytes()
    sid = upload(h, data, name="letter.pdf")
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=h, json={"filename": "a2b", "pdf_version": "pdfa-2b"})
    assert r.status_code == 200, r.text
    assert not any("คัดลอก/ค้นหา" in c for c in r.json()["version"]["converted"])
    out = client.get(f"/pdf/files/{r.json()['new_id']}/download", headers=h).content
    norm = lambda t: "".join(t.split())  # noqa: E731
    assert norm(_text(out)) == norm(_text(data)) and "หนังสือทวงถามหนี้" in _text(out)


def test_compress_falls_back_to_images_when_ghostscript_breaks_text(client, make_user, upload, monkeypatch):
    """Ghostscript รุ่นที่ทำข้อความเพี้ยน (จำลอง) → ไม่ใช้ผลนั้น ใช้วิธีบีบรูปอย่างเดียว"""
    from app.services.pdf_service import optimize

    monkeypatch.setattr(optimize, "text_preserved", lambda a, b: False)
    _, h = make_user()
    import io
    import numpy as np
    from PIL import Image

    doc = fitz.open("pdf", FIXTURE.read_bytes())
    arr = (np.random.default_rng(2).random((1200, 1600, 3)) * 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    doc[0].insert_image(fitz.Rect(72, 500, 300, 700), stream=buf.getvalue())
    data = doc.tobytes()
    sid = upload(h, data)
    r = client.post(f"/pdf/{sid}/compress", headers=h, json={"profile": "screen"})
    assert r.status_code == 200, r.text
    assert r.json().get("method") == "images"
    from app.core.session import session_manager

    s = session_manager.get(sid)
    with s.lock:
        assert s.doc[0].get_text() == fitz.open("pdf", data)[0].get_text()
