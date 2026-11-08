"""ลดขนาดไฟล์ (Ghostscript): annotation/ช่องฟอร์มต้องอยู่ครบ, ไม่เขียนทับถ้าไม่เล็กลง, คืนขนาดก่อน/หลัง"""
import io
import shutil
from pathlib import Path

import fitz
import numpy as np
import pikepdf
import pytest
from PIL import Image

from app.core.session import session_manager

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")

pytestmark = pytest.mark.skipif(shutil.which("gs") is None, reason="ต้องมี Ghostscript")


def _pdf(photo=True):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_font(fontname="sar", fontfile=FONT)   # ฟอนต์ฝังทั้งไฟล์ — Ghostscript ตัดเหลือเฉพาะตัวที่ใช้
    p.insert_text((72, 80), "Compress test", fontname="sar", fontsize=14)
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 64, 300, 84), "uri": "https://example.com"})
    w = fitz.Widget()
    w.field_name, w.field_type = "name", fitz.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = fitz.Rect(72, 160, 300, 180), "Somchai"
    p.add_widget(w)
    if photo:
        rng = np.random.default_rng(1)
        arr = (rng.random((900, 1200, 3)) * 60 + np.linspace(0, 190, 1200)[None, :, None]).astype("uint8")
        b = io.BytesIO()
        Image.fromarray(arr).save(b, "JPEG", quality=95)
        p.insert_image(fitz.Rect(72, 300, 520, 640), stream=b.getvalue())
    return doc.tobytes(garbage=3, deflate=True)


@pytest.fixture
def auth_headers(make_user):
    return make_user()[1]


def _open(client, headers, data):
    sid = client.post("/pdf/upload", headers=headers, files={"file": ("t.pdf", data, "application/pdf")}).json()["session_id"]
    for body in [dict(page_number=0, type="highlight", rect=dict(x0=72, y0=66, x1=300, y1=86)),
                 dict(page_number=0, type="freetext", rect=dict(x0=72, y0=200, x1=330, y1=230), content="note", fontsize=14),
                 dict(page_number=0, type="rect", rect=dict(x0=60, y0=290, x1=530, y1=650), color=[1, 0, 0])]:
        assert client.post(f"/annotation/{sid}", headers=headers, json=body).status_code == 200
    return sid


def _page(sid):
    s = session_manager.get(sid)
    with s.lock:
        return fitz.open("pdf", s.doc.tobytes())


def test_compress_keeps_annotations_forms_and_links(client, auth_headers):
    sid = _open(client, auth_headers, _pdf())
    r = client.post(f"/pdf/{sid}/compress", headers=auth_headers, json={"profile": "screen"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["after"] < body["before"] * 0.8
    doc = _page(sid)
    page = doc[0]
    assert sorted(a.type[1] for a in page.annots()) == ["FreeText", "Highlight", "Square"]
    assert [(w.field_name, w.field_value) for w in page.widgets()] == [("name", "Somchai")]
    assert len(page.get_links()) == 1
    # ช่องฟอร์มต้องไม่ถูกวาดลงเนื้อหน้าซ้ำ (ไม่งั้นแก้ค่าแล้วจะเห็นค่าเก่าซ้อนอยู่) — ดูเฉพาะเนื้อหน้า ไม่รวม annotation
    with pikepdf.open(io.BytesIO(doc.tobytes())) as pdf:
        del pdf.pages[0].obj["/Annots"]
        del pdf.Root["/AcroForm"]
        out = io.BytesIO()
        pdf.save(out)
    text = fitz.open("pdf", out.getvalue())[0].get_text()
    assert "Compress test" in text and "Somchai" not in text and "note" not in text
    assert client.post(f"/pdf/{sid}/undo", headers=auth_headers).status_code == 200


def test_compress_without_gain_leaves_document_untouched(client, auth_headers):
    sid = _open(client, auth_headers, _pdf(photo=False))
    first = client.post(f"/pdf/{sid}/compress", headers=auth_headers, json={"profile": "screen"}).json()
    assert first["status"] == "ok" and first["after"] < first["before"]
    session = session_manager.get(sid)
    doc_before = session.doc
    r = client.post(f"/pdf/{sid}/compress", headers=auth_headers, json={"profile": "screen"})
    assert r.status_code == 200 and r.json() == {"status": "no_change"}
    assert session.doc is doc_before   # ไม่ได้เปิดไฟล์ใหม่มาแทน


def test_dashboard_quick_compress_creates_smaller_copy(client, make_user, upload):
    _, owner = make_user()
    sid = upload(owner, _pdf(), name="รูปถ่าย.pdf")
    files = client.get("/pdf/files", headers=owner).json()["files"]
    rec = next(f for f in files if f["session_id"] == sid)
    assert rec["file_size"] > 0

    r = client.post(f"/pdf/files/{rec['id']}/quick-action", headers=owner,
                    json={"action": "compress", "compress_profile": "screen"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["file"]["filename"] == "รูปถ่าย (ลดขนาด).pdf"
    assert body["sizes"]["before"] == rec["file_size"] and body["sizes"]["after"] < rec["file_size"] * 0.8

    files = {f["id"]: f for f in client.get("/pdf/files", headers=owner).json()["files"]}
    assert files[rec["id"]]["file_size"] == rec["file_size"]          # ไฟล์เดิมไม่เปลี่ยน
    assert files[body["file"]["id"]]["file_size"] == body["sizes"]["after"]



def test_dashboard_quick_compress_without_gain_creates_nothing(client, make_user, upload):
    _, owner = make_user()
    upload(owner, _pdf(photo=False), name="text.pdf")
    fid = client.get("/pdf/files", headers=owner).json()["files"][0]["id"]
    first = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={"action": "compress"}).json()
    assert first["status"] == "ok"
    r = client.post(f"/pdf/files/{first['file']['id']}/quick-action", headers=owner, json={"action": "compress"})
    assert r.status_code == 200 and r.json() == {"status": "no_change"}
    assert len(client.get("/pdf/files", headers=owner).json()["files"]) == 2
