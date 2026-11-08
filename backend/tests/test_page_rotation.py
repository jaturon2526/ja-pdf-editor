"""หน้าที่หมุน: ทุกหน้าใน session มี /Rotate = 0 เสมอ (หมุนเข้าเนื้อหน้า) — พิกัดบนจอ = พิกัดใน PDF
annotation ที่วาดบนหน้าที่หมุนจึงอยู่ตรงที่ผู้ใช้เห็นทั้งตอนดาวน์โหลด/พิมพ์/รวมเลเยอร์"""
from pathlib import Path

import fitz
import numpy as np

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")


def _doc(sid):
    from app.core.session import session_manager

    s = session_manager.get(sid)
    with s.lock:
        return fitz.open("pdf", s.doc.tobytes())


def _red_center(page):
    pix = page.get_pixmap(dpi=72, annots=True)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    ys, xs = np.where((a[:, :, 0] > 200) & (a[:, :, 1] < 80) & (a[:, :, 2] < 80))
    return float(xs.mean()), float(ys.mean())


def test_rotated_page_annotation_lands_where_drawn(client, make_user, upload):
    from tests.conftest import make_pdf_bytes

    _, h = make_user()
    sid = upload(h, make_pdf_bytes(pages=1))
    assert client.post(f"/pdf/{sid}/pages/rotate", headers=h, json={"page_numbers": [0], "angle": 90}).status_code == 200
    page = _doc(sid)[0]
    assert page.rotation == 0 and page.rect.width > page.rect.height     # แนวนอนตามที่หมุน แต่ไม่มี /Rotate
    # กรอบสีแดงที่มุมซ้ายบนของหน้า (พิกัดตามที่เห็นบนจอ)
    r = client.post(f"/annotation/{sid}", headers=h, json={
        "page_number": 0, "type": "rect", "color": [1, 0, 0], "rect": {"x0": 50, "y0": 40, "x1": 250, "y1": 140}})
    assert r.status_code == 200, r.text
    x, y = _red_center(_doc(sid)[0])
    assert 120 < x < 180 and 60 < y < 120                                # อยู่มุมซ้ายบนจริงในไฟล์
    listed = client.get(f"/annotation/{sid}/page/0", headers=h).json()
    assert round(listed[0]["rect"]["x0"]) in (49, 50)


def test_uploaded_rotated_pages_are_normalized_with_links_and_text(client, make_user, upload):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_font(fontname="sar", fontfile=FONT)
    p.insert_text((72, 80), "ข้อความหน้าแนวนอน", fontname="sar", fontsize=16)
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 64, 300, 84), "uri": "https://example.com"})
    s = p.add_rect_annot(fitz.Rect(380, 50, 540, 150))
    s.set_colors(stroke=(1, 0, 0))
    s.update()
    p.set_rotation(90)
    doc = fitz.open("pdf", doc.tobytes())
    before = doc[0].get_pixmap(dpi=50)
    links_before = [tuple(round(v) for v in link["from"]) for link in doc[0].get_links()]
    assert links_before
    _, h = make_user()
    sid = upload(h, doc.tobytes())
    page = _doc(sid)[0]
    assert page.rotation == 0
    assert [tuple(round(v) for v in link["from"]) for link in page.get_links()] == links_before
    after = page.get_pixmap(dpi=50)
    a = np.frombuffer(before.samples, dtype=np.uint8).astype(int)
    b = np.frombuffer(after.samples, dtype=np.uint8).astype(int)
    assert a.shape == b.shape and (np.abs(a - b) > 40).mean() < 0.002     # หน้าตาเหมือนเดิม (รวมกรอบ annotation)
    words = page.get_text("words")                                        # พิกัดคำ = พิกัดบนจอ (ข้อความแนวตั้งขอบขวา)
    assert words and words[0][0] > page.rect.width / 2


def test_signed_documents_keep_their_rotation(client, make_user, upload):
    from app.core.session import session_manager
    from tests.conftest import make_pdf_bytes

    _, h = make_user()
    sid = upload(h, make_pdf_bytes(pages=1))
    s = session_manager.get(sid)
    with s.lock:
        s.signed_pdf_bytes = b"existing"
    assert client.post(f"/pdf/{sid}/pages/rotate", headers=h, json={"page_numbers": [0], "angle": 90}).status_code == 200
    assert _doc(sid)[0].rotation == 90                                    # ไม่แก้เนื้อหน้า (ลายเซ็นยังใช้ได้)


def test_highlight_on_vertical_text_follows_the_line(client, make_user, upload):
    """ข้อความแนวตั้ง (หน้าที่หมุน 90°): ไฮไลต์ต้องบางพอดีบรรทัด ไม่ใช่วงรีอ้วน (MuPDF ใช้ความสูงของ quad ทำปลายมน)"""
    from tests.conftest import make_pdf_bytes

    _, h = make_user()
    sid = upload(h, make_pdf_bytes(pages=1, text="Highlight vertical line of text"))
    client.post(f"/pdf/{sid}/pages/rotate", headers=h, json={"page_numbers": [0], "angle": 90})
    words = client.get(f"/annotation/{sid}/page/0/words", headers=h).json()
    xs0 = min(w["rect"]["x0"] for w in words); xs1 = max(w["rect"]["x1"] for w in words)
    ys0 = min(w["rect"]["y0"] for w in words); ys1 = max(w["rect"]["y1"] for w in words)
    assert ys1 - ys0 > 3 * (xs1 - xs0)                                     # บรรทัดแนวตั้งจริง
    rect = {"x0": xs0, "y0": ys0, "x1": xs1, "y1": ys1}
    assert client.post(f"/annotation/{sid}", headers=h, json={"page_number": 0, "type": "highlight", "rect": rect}).status_code == 200
    doc = _doc(sid)
    page = doc[0]
    width = [a.rect.width for a in page.annots()][0]
    assert width < (xs1 - xs0) * 1.6, width                               # เดิม: วงรีกว้างกว่าบรรทัดหลายเท่า
