"""รวมเลเยอร์ (Flatten): annotation/ฟอร์มกลายเป็นเนื้อหน้า โดยลิงก์ บุ๊กมาร์ก การหมุนหน้า และข้อความยังอยู่ครบ"""
import shutil
import subprocess
from pathlib import Path

import fitz
import pytest

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")
needs_gs = pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")


def _doc_bytes() -> bytes:
    doc = fitz.open()
    p = doc.new_page()
    p.insert_font(fontname="sar", fontfile=FONT)
    p.insert_text((72, 80), "หน้าแรก ทดสอบการรวมเลเยอร์", fontname="sar", fontsize=14)
    p.insert_text((72, 112), "ลิงก์ไปเว็บไซต์", fontname="sar", fontsize=11)
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect, w.field_value = "name", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(72, 160, 300, 180), "Somchai"
    p.add_widget(w)
    p2 = doc.new_page()
    p2.insert_font(fontname="sar", fontfile=FONT)
    p2.insert_text((72, 80), "หน้าสองแนวนอน", fontname="sar", fontsize=14)
    p2.set_rotation(90)
    doc[0].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 100, 250, 115), "uri": "https://example.com"})
    doc[0].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 125, 250, 140), "page": 1})
    doc.set_toc([[1, "หน้าแรก", 1], [1, "หน้าสอง", 2]])
    return doc.tobytes()


@pytest.fixture
def flat_session(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers, _doc_bytes())
    r = client.post(f"/annotation/{sid}", headers=headers, json={
        "page_number": 0, "type": "freetext", "content": "ข้อความในกล่อง", "fontsize": 14,
        "rect": {"x0": 72, "y0": 230, "x1": 330, "y1": 260}})
    assert r.status_code == 200, r.text
    r = client.post(f"/annotation/{sid}", headers=headers, json={
        "page_number": 0, "type": "highlight", "rect": {"x0": 72, "y0": 66, "x1": 300, "y1": 86}})
    assert r.status_code == 200, r.text
    return sid, headers


def _doc(sid):
    from app.core.session import session_manager

    s = session_manager.get(sid)
    with s.lock:
        return fitz.open("pdf", s.doc.tobytes())


def test_flatten_burns_annotations_and_keeps_links_toc_rotation(client, flat_session):
    sid, headers = flat_session
    r = client.post(f"/pdf/{sid}/flatten", headers=headers)
    assert r.status_code == 200, r.text
    doc = _doc(sid)
    p0, p1 = doc[0], doc[1]
    assert list(p0.annots()) == [] and list(p0.widgets()) == []
    text = p0.get_text()
    assert "ข้อความในกล่อง" in text and "Somchai" in text        # FreeText + ค่าในฟอร์ม เป็นข้อความในหน้า
    links = p0.get_links()
    assert {l.get("uri") for l in links if l.get("uri")} == {"https://example.com"}
    assert any(l.get("page") == 1 for l in links)                   # ลิงก์ไปหน้าในเอกสารยังอยู่
    assert doc.get_toc() == [[1, "หน้าแรก", 1], [1, "หน้าสอง", 2]]
    # หน้าที่หมุนไว้ยังเป็นแนวนอน (Ghostscript ไม่หมุนหน้าเองตามทิศตัวอักษร)
    assert p1.rect.width > p1.rect.height


def test_flatten_failure_leaves_document_untouched(client, flat_session, monkeypatch):
    sid, headers = flat_session

    def boom(self, **kw):
        raise RuntimeError("simulated")

    monkeypatch.setattr(fitz.Document, "bake", boom)
    r = client.post(f"/pdf/{sid}/flatten", headers=headers)
    assert r.status_code == 400 and "simulated" in r.json()["detail"]
    types = [a.type[1] for a in _doc(sid)[0].annots()]
    assert "FreeText" in types and "Highlight" in types              # เดิม: FreeText หายทั้งที่ล้มเหลว


def test_flatten_does_not_need_ghostscript(client, flat_session, monkeypatch):
    from app.services.pdf_service import optimize

    sid, headers = flat_session

    def missing(cmd, **kw):
        raise FileNotFoundError("gs")

    monkeypatch.setattr(optimize.subprocess, "run", missing)
    assert client.post(f"/pdf/{sid}/flatten", headers=headers).status_code == 200


def test_flatten_keeps_thai_text_of_libreoffice_pdf(client, make_user, upload):
    """PDF จาก LibreOffice (สร้างเอกสารอัตโนมัติ/แปลง Office) — เดิมผ่าน Ghostscript แล้วข้อความไทยที่คัดลอกได้เพี้ยน
    เป็น "หนั\x03งสื\x06อ" เพราะฟอนต์ถูกเข้ารหัสใหม่"""
    _, headers = make_user()
    data = (Path(__file__).parent / "fixtures" / "libreoffice_thai.pdf").read_bytes()
    before = fitz.open("pdf", data)[0].get_text()
    sid = upload(headers, data)
    r = client.post(f"/annotation/{sid}", headers=headers, json={
        "page_number": 0, "type": "highlight", "rect": {"x0": 72, "y0": 66, "x1": 300, "y1": 86}})
    assert r.status_code == 200
    assert client.post(f"/pdf/{sid}/flatten", headers=headers).status_code == 200
    page = _doc(sid)[0]
    assert list(page.annots()) == []
    after = page.get_text()
    assert after == before and "หนังสือทวงถามหนี้" in after and not any(ord(c) < 9 for c in after)


def test_flatten_drops_hidden_annotations(client, flat_session):
    from app.core.session import session_manager

    sid, headers = flat_session
    s = session_manager.get(sid)
    with s.lock:
        a = s.doc[0].add_freetext_annot(fitz.Rect(72, 300, 300, 330), "ซ่อนอยู่ไม่ควรติด", fontsize=12)
        a.set_flags(fitz.PDF_ANNOT_IS_HIDDEN)
        a.update()
    assert client.post(f"/pdf/{sid}/flatten", headers=headers).status_code == 200
    assert "ซ่อนอยู่" not in _doc(sid)[0].get_text()


def test_flatten_and_compress_refuse_digitally_signed_documents(client, flat_session):
    from app.core.session import session_manager

    sid, headers = flat_session
    s = session_manager.get(sid)
    with s.lock:
        s.signed_pdf_bytes = b"existing"
    r = client.post(f"/pdf/{sid}/flatten", headers=headers)
    assert r.status_code == 400 and "ลายเซ็นดิจิทัล" in r.json()["detail"]
    r = client.post(f"/pdf/{sid}/compress", headers=headers, json={"profile": "screen"})
    assert r.status_code == 400 and "ลายเซ็นดิจิทัล" in r.json()["detail"]
