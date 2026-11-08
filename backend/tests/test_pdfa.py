"""บันทึกเป็น PDF/A-1b / 2b / 3b — ตรวจด้วย verify_pdfa (ข้อกำหนดหลักของ ISO 19005) และ veraPDF ถ้ามี
(CI ติดตั้ง veraPDF และตั้ง VERAPDF_REQUIRED=1 — ไม่มี veraPDF ใน CI = test ล้ม ไม่ข้ามเงียบๆ)"""
import io
import os
import re
import shutil
import subprocess
from pathlib import Path

import fitz
import numpy as np
import pikepdf
import pytest
from PIL import Image

from app.core.session import session_manager
from app.models.schemas import AnnotationCreate, Rect
from app.services import annotation_service
from app.services.pdf_service import core, export_pdfa, verify_pdfa
from app.services.pdf_service.core import PDFError

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")
pytestmark = pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")


def _source() -> bytes:
    d = fitz.open()
    p = d.new_page()
    p.insert_font(fontname="sar", fontfile=FONT)
    p.insert_text((72, 80), "ข้อความไทย ทดสอบ PDF/A", fontname="sar", fontsize=14)
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 64, 300, 84), "uri": "https://example.com"})
    w = fitz.Widget()
    w.field_name, w.field_type = "name", fitz.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = fitz.Rect(72, 500, 300, 520), "Somchai"
    p.add_widget(w)
    rgba = (np.random.default_rng(1).random((60, 80, 4)) * 255).astype("uint8")
    b = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(b, "PNG")
    p.insert_image(fitz.Rect(72, 300, 232, 420), stream=b.getvalue())        # รูปโปร่งใส (PDF/A-1 ห้าม)
    b = io.BytesIO()
    Image.fromarray(rgba[:, :, :3]).save(b, "JPEG2000")
    p.insert_image(fitz.Rect(300, 300, 460, 420), stream=b.getvalue())       # JPEG 2000 (PDF/A-1 ห้าม)
    d.set_toc([[1, "หน้าแรก", 1]])
    d.set_metadata({"title": "รายงาน", "author": "สมชาย"})
    return d.tobytes()


def _session(data=None):
    s, _ = core.create_session_from_upload(data or _source(), "t.pdf", user_id=None)
    annotation_service.add_annotation(s, AnnotationCreate(page_number=0, type="highlight",
                                                          rect=Rect(x0=72, y0=66, x1=300, y1=86)))
    annotation_service.add_annotation(s, AnnotationCreate(page_number=0, type="freetext", content="กล่องข้อความ",
                                                          rect=Rect(x0=72, y0=200, x1=330, y1=230)))
    return s


def _verapdf(path: Path, flavour: str):
    exe = shutil.which("verapdf")
    if exe is None:
        if os.getenv("VERAPDF_REQUIRED") == "1":
            pytest.fail("ไม่พบ veraPDF ทั้งที่ CI ต้องตรวจด้วย veraPDF")
        return None
    r = subprocess.run([exe, "--flavour", flavour, "--format", "xml", str(path)], capture_output=True, text=True, timeout=300)
    assert "<validationReport" in r.stdout, r.stderr[-2000:]
    failed = re.findall(r'<rule[^>]*clause="([^"]*)"[^>]*testNumber="([^"]*)"[^>]*status="failed"', r.stdout) or \
        re.findall(r'<rule[^>]*status="failed"[^>]*clause="([^"]*)"[^>]*testNumber="([^"]*)"', r.stdout)
    return 'isCompliant="true"' in r.stdout, failed


@pytest.mark.parametrize("flavour", ["pdfa-1b", "pdfa-2b", "pdfa-3b"])
def test_export_pdfa_conforms(flavour):
    part = int(flavour[5])
    out, report = export_pdfa(_session(), flavour)
    try:
        assert report["pdf_version"] == f"PDF/A-{part}b"
        assert verify_pdfa(out, part) == []
        with pikepdf.open(out) as pdf:
            meta = pdf.open_metadata()
            assert str(meta.get("pdfaid:part")) == str(part) and meta.get("dc:title") == "รายงาน"
        doc = fitz.open(out)
        text = doc[0].get_text()
        assert "ข้อความไทย" in text and "กล่องข้อความ" in text and "Somchai" in text   # ไม่ถูกแปลงเป็นรูป
        assert len(doc[0].get_links()) == 1 and doc.get_toc() == [[1, "หน้าแรก", 1]]
        if part == 1:
            assert any("พื้นขาว" in c for c in report["converted"])
        vera = _verapdf(out, f"{part}b")
        if vera is not None:
            ok, failed = vera
            assert ok, f"veraPDF: ไม่ผ่าน {failed}"
    finally:
        out.unlink(missing_ok=True)


def test_verify_rejects_plain_pdf(tmp_path):
    p = tmp_path / "plain.pdf"
    p.write_bytes(_source())
    errors = verify_pdfa(p, 2)
    assert any("OutputIntent" in e for e in errors) and any("pdfaid" in e for e in errors)


def test_password_protected_document_is_refused():
    s = _session()
    s.output_password = "pw"
    with pytest.raises(PDFError, match="รหัสผ่าน"):
        export_pdfa(s, "pdfa-2b")


def test_save_as_copy_route_pdfa(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers, _source())
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=headers, json={"filename": "archive", "pdf_version": "pdfa-2b"})
    assert r.status_code == 200, r.text
    assert r.json()["version"]["pdf_version"] == "PDF/A-2b"
    opened = client.post(f"/pdf/{r.json()['new_session_id']}/open", headers=headers).json()
    s = session_manager.get(opened["session_id"])
    with s.lock:
        assert s.doc.metadata["format"] == "PDF 1.7"
