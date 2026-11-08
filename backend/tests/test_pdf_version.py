"""บันทึกเป็นไฟล์ใหม่แบบเลือก PDF เวอร์ชัน — ไฟล์ที่ได้ต้องตรงมาตรฐานเวอร์ชันนั้นจริง (หัวไฟล์ โครงสร้าง การเข้ารหัส เนื้อหา)"""
import io
import shutil

import fitz
import numpy as np
import pikepdf
import pytest
from PIL import Image

from app.core.session import session_manager
from app.services.pdf_service import core, export_pdf_version
from app.services.pdf_service.core import PDFError
from app.services.pdf_service.version import scan_features, _v

needs_gs = pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")


def _rich_pdf() -> bytes:
    """ไฟล์ที่มีคุณสมบัติของ 1.5+ ครบ: รูป JPEG 2000, เลเยอร์, object stream + ข้อความ ลิงก์ ฟอร์ม ไฮไลต์ บุ๊กมาร์ก"""
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 80), "Version test", fontsize=14)
    arr = (np.random.default_rng(1).random((120, 160, 3)) * 255).astype("uint8")
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "JPEG2000")
    p.insert_image(fitz.Rect(72, 300, 232, 420), stream=b.getvalue())
    ocg = doc.add_ocg("Layer1")
    p.insert_text((72, 200), "optional layer", oc=ocg)
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 64, 300, 84), "uri": "https://example.com"})
    w = fitz.Widget()
    w.field_name, w.field_type = "name", fitz.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = fitz.Rect(72, 500, 300, 520), "Somchai"
    p.add_widget(w)
    p.add_highlight_annot(fitz.Rect(72, 66, 300, 86))
    doc.set_toc([[1, "First", 1]])
    doc.set_metadata({"title": "รายงาน", "author": "สมชาย"})
    return doc.tobytes(garbage=3, deflate=True, use_objstms=1)


def _session(data, password=None):
    s, _ = core.create_session_from_upload(data, "t.pdf", user_id=None)
    s.output_password = password
    return s


@pytest.mark.parametrize("target", ["1.4", "1.5", "1.6", "1.7", "2.0"])
@pytest.mark.parametrize("password", [None, "pw"])
@needs_gs
def test_export_conforms_and_keeps_content(target, password):
    out, report = export_pdf_version(_session(_rich_pdf(), password), target)
    try:
        with pikepdf.open(out, password=password or "") as pdf:
            assert pdf.pdf_version == target
            assert "/Version" not in pdf.Root
            raw = out.read_bytes().replace(b" ", b"")
            if target == "1.4":
                assert b"/Type/ObjStm" not in raw and b"/Type/XRef" not in raw
            if password:
                expected_r = {"1.4": 3, "1.5": 3, "1.6": 4, "1.7": 6, "2.0": 6}[target]  # 1.7 = AES-256 (ค่าเริ่มต้น)
                assert pdf.encryption.R == expected_r
            meta = pdf.open_metadata()
            assert meta.get("dc:title") == "รายงาน"
            if target == "2.0":
                assert set(pdf.docinfo.keys()) <= {"/CreationDate", "/ModDate"}
            else:
                assert str(pdf.docinfo["/Title"]) == "รายงาน"
        if not password:
            assert all(_v(v) <= _v(target) for v in scan_features(out).values())
        assert report["method"] == ("ghostscript" if target == "1.4" else "rewrite")

        doc = fitz.open(out)
        if password:
            assert doc.needs_pass and doc.authenticate(password)
        page = doc[0]
        assert "Version test" in page.get_text()
        assert sorted(a.type[1] for a in page.annots()) == ["Highlight"]
        assert [(w.field_name, w.field_value) for w in page.widgets()] == [("name", "Somchai")]
        assert len(page.get_links()) == 1
        assert doc.get_toc() == [[1, "First", 1]]
        assert len(page.get_images()) >= 1
    finally:
        out.unlink(missing_ok=True)


@needs_gs
def test_downgrade_to_14_keeps_the_look():
    data = _rich_pdf()
    out, report = export_pdf_version(_session(data), "1.4")
    try:
        assert any("JPEG 2000" in c for c in report["converted"]) and any("เลเยอร์" in c for c in report["converted"])
        a = fitz.open("pdf", data)[0].get_pixmap(dpi=72, annots=False)
        b = fitz.open(out)[0].get_pixmap(dpi=72, annots=False)
        diff = np.abs(np.frombuffer(a.samples, np.uint8).astype(int) - np.frombuffer(b.samples, np.uint8).astype(int))
        assert diff.mean() < 1 and (diff > 40).mean() < 0.001       # รูปไม่ถูกบีบแบบเสียคุณภาพ
    finally:
        out.unlink(missing_ok=True)


def test_annotation_type_newer_than_target_is_removed():
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 80), "x")
    p.add_redact_annot(fitz.Rect(72, 66, 120, 86))       # Redact annotation = PDF 1.7
    out, report = export_pdf_version(_session(doc.tobytes()), "1.6")
    try:
        assert report["removed"] and not list(fitz.open(out)[0].annots())
    finally:
        out.unlink(missing_ok=True)


def test_signed_documents_are_refused(monkeypatch):
    from app.services.pdf_service import version
    monkeypatch.setattr(version, "has_digital_signatures", lambda doc: True)
    with pytest.raises(PDFError):
        export_pdf_version(_session(_rich_pdf()), "1.7")


@needs_gs
def test_save_as_copy_route_with_version(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers, _rich_pdf())
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=headers, json={"filename": "v14", "pdf_version": "1.4"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"]["pdf_version"] == "1.4"
    opened = client.post(f"/pdf/{body['new_session_id']}/open", headers=headers).json()
    s = session_manager.get(opened["session_id"])
    with s.lock:
        assert s.doc.metadata["format"] == "PDF 1.4"
    # ไม่ระบุเวอร์ชัน = ทำงานแบบเดิม
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=headers, json={"filename": "same"})
    assert r.status_code == 200 and r.json()["version"] is None
    r = client.post(f"/pdf/{sid}/save-as-copy", headers=headers, json={"filename": "bad", "pdf_version": "1.3"})
    assert r.status_code == 422
