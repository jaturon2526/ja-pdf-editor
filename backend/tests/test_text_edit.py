"""แก้ไขข้อความบนพื้นหลังที่เป็นกราฟิก (เช่น หัวข้อตัวขาวบนแถบสีน้ำเงิน) ต้องไม่ลบแถบสีทิ้ง

บั๊กเดิม: redact ระบายสีที่สุ่มจาก 4 มุมของกล่องข้อความ — กล่องยื่นออกนอกแถบสีจึงสุ่มได้ขาว
แถบหายเป็นสีขาว และข้อความใหม่สีขาวมองไม่เห็น
"""
import shutil
from pathlib import Path

import fitz

from app.core.session import InMemorySessionManager
from app.models.schemas import Rect
from app.services import edit_service

BAR = fitz.Rect(0, 41, 369, 73)
BLUE = (0, 0.33, 1)


def _blue_share(page, rect):
    pix = page.get_pixmap(clip=rect, colorspace=fitz.csRGB, alpha=False)
    s = pix.samples
    blue = sum(1 for i in range(0, len(s), 3) if s[i + 2] > 200 and s[i] < 60)
    return blue / (pix.width * pix.height)


def _session(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(BAR, color=None, fill=BLUE)
    page.insert_text((34, 62), "4. Heading on blue bar", fontsize=14, color=(1, 1, 1))
    src = tmp_path / "in.pdf"
    doc.save(src)
    work = tmp_path / "work.pdf"
    shutil.copy(src, work)
    session = InMemorySessionManager().create_session(Path(src), Path(work), "in.pdf")
    session.doc = fitz.open(work)
    session.is_unlocked = True
    return session


def test_edit_heading_on_colored_bar_keeps_background(tmp_path):
    session = _session(tmp_path)
    inside_bar = fitz.Rect(5, 45, 360, 70)
    assert _blue_share(session.doc[0], inside_bar) > 0.9

    # กล่องที่ผู้ใช้ลากกว้างเกินแถบสีออกไปทางขวา
    edit_service.replace_text(session, 0, Rect(x0=34, y0=41, x1=407, y1=69), "4. New heading", 14,
                              "sarabun", (1, 1, 1), block_id="0-0")
    page = session.doc[0]
    assert _blue_share(page, inside_bar) > 0.9
    assert "4. New heading" in page.get_text()
    assert "Heading on blue bar" not in page.get_text()

    # แก้ซ้ำ: ข้อความจาก edit ครั้งก่อนต้องหายไป แถบสียังอยู่
    block = next(b for b in edit_service.get_text_blocks(session, 0) if b.block_id.startswith("edit-"))
    edit_service.replace_text(session, 0, block.rect, "4. Second edit", 14, "sarabun", (1, 1, 1),
                              block_id=block.block_id, previous_rect=block.rect)
    page = session.doc[0]
    assert _blue_share(page, inside_bar) > 0.9
    text = page.get_text()
    assert "4. Second edit" in text and "New heading" not in text


def _bar_right_edge(page, y):
    """ขอบขวาของแถบสีน้ำเงินที่ความสูง y (pt) — ไล่พิกเซลจากซ้ายไปขวา"""
    pix = page.get_pixmap(clip=fitz.Rect(0, y, page.rect.width, y + 1), colorspace=fitz.csRGB, alpha=False)
    right = 0
    for x in range(pix.width):
        r, g, b = pix.pixel(x, 0)
        if b > 200 and r < 60:
            right = x
    return right


def test_longer_heading_extends_the_bar_and_shorter_reedit_shrinks_it(tmp_path):
    session = _session(tmp_path)
    page = session.doc[0]
    bar_right = _bar_right_edge(page, 70)
    assert abs(bar_right - BAR.x1) <= 1

    long_text = "4. A much longer heading that runs past the end of the bar"
    edit_service.replace_text(session, 0, Rect(x0=34, y0=45, x1=560, y1=69), long_text, 14,
                              "sarabun", (1, 1, 1), block_id="0-0")
    page = session.doc[0]
    words = page.get_text("words")
    text_right = max(w[2] for w in words if w[4] in long_text.split())
    assert text_right > BAR.x1  # ข้อความยาวเกินแถบเดิมจริง
    assert _bar_right_edge(page, 70) >= text_right  # แถบขยายคลุมข้อความ

    block = next(b for b in edit_service.get_text_blocks(session, 0) if b.block_id.startswith("edit-"))
    edit_service.replace_text(session, 0, block.rect, "4. Short", 14, "sarabun", (1, 1, 1),
                              block_id=block.block_id, previous_rect=block.rect)
    assert abs(_bar_right_edge(session.doc[0], 70) - BAR.x1) <= 1  # ส่วนที่ต่อไว้ถูกลบ แถบกลับขนาดเดิม


def test_download_is_compacted_after_many_edits(client, make_user, upload):
    """ไฟล์ทำงานบันทึกแบบ incremental จึงโตขึ้นทุกครั้งที่แก้ — ไฟล์ที่ดาวน์โหลดต้องตัดของเก่าทิ้ง"""
    from app.core.session import session_manager
    from tests.conftest import make_pdf_bytes

    _, headers = make_user()
    sid = upload(headers, make_pdf_bytes(pages=1, text="Edit me"))
    rect = {"x0": 60, "y0": 60, "x1": 400, "y1": 90}
    for i in range(4):
        r = client.post(f"/edit/{sid}/text", headers=headers,
                        json={"page_number": 0, "rect": rect, "new_text": f"Edited {i}", "fontsize": 14})
        assert r.status_code == 200, r.text
        client.get(f"/pdf/{sid}/download", headers=headers)  # บันทึกลงไฟล์ทำงานทุกรอบ (ไฟล์โตขึ้น)

    working_size = session_manager.get(sid).working_path.stat().st_size
    data = client.get(f"/pdf/{sid}/download", headers=headers).content
    assert len(data) < working_size / 2
    page = fitz.open("pdf", data)[0]
    assert "Edited 3" in page.get_text() and "Edited 2" not in page.get_text()


def _table_session(tmp_path):
    """ตาราง 3 คอลัมน์ (เส้นแบ่งที่ x=200, 300) — ข้อความหัวตารางเป็นสตริงเดียวยาวข้ามเส้น (PyMuPDF ได้ span เดียว)"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x in (30, 200, 300, 400):
        page.draw_line((x, 80), (x, 260), color=(0, 0, 0), width=0.75)
    for y in (80, 110, 260):
        page.draw_line((30, y), (400, y), color=(0, 0, 0), width=0.75)
    page.insert_text((40, 100), "Head A" + " " * 57 + "Head B" + " " * 8 + "Head C", fontsize=11)
    page.insert_text((40, 130), "1. Coordinate with the consultant", fontsize=11)
    page.insert_text((240, 130), "20", fontsize=11)
    page.insert_text((340, 130), "85", fontsize=11)
    page.insert_text((40, 150), "2. Coordinate other units", fontsize=11)
    page.insert_text((240, 150), "40", fontsize=11)
    page.insert_text((40, 175), "3. Build the integration with the", fontsize=11)
    page.insert_text((40, 189), "customer database", fontsize=11)
    src = tmp_path / "table.pdf"
    doc.save(src)
    work = tmp_path / "table_work.pdf"
    shutil.copy(src, work)
    session = InMemorySessionManager().create_session(Path(src), Path(work), "table.pdf")
    session.doc = fitz.open(work)
    session.is_unlocked = True
    return session


def test_text_blocks_stay_inside_table_cells(tmp_path):
    session = _table_session(tmp_path)
    texts = [b.text for b in edit_service.get_text_blocks(session, 0)]
    # หัวตารางที่เป็นสตริงเดียวข้ามเส้นแบ่งคอลัมน์ → แยกตามช่อง
    for head in ("Head A", "Head B", "Head C"):
        assert head in texts, texts
    # ข้อความคนละคอลัมน์ในแถวเดียวกันไม่รวมกัน · ข้อในรายการคนละข้อไม่รวมกัน
    assert "1. Coordinate with the consultant" in texts
    assert "2. Coordinate other units" in texts
    assert {"20", "85", "40"} <= set(texts)
    # ข้อความที่ wrap ในช่องเดียวกันยังเป็นย่อหน้าเดียว
    assert "3. Build the integration with the\ncustomer database" in texts


def test_edit_one_table_cell_keeps_neighbour_cells(tmp_path):
    session = _table_session(tmp_path)
    cell = next(b for b in edit_service.get_text_blocks(session, 0) if b.text == "20")
    assert cell.rect.x1 < 300                    # กล่องอยู่ในช่องของตัวเอง
    edit_service.replace_text(session, 0, cell.rect, "25", 11, "sarabun", (0, 0, 0), block_id=cell.block_id)
    text = session.doc[0].get_text()
    assert "25" in text and "1. Coordinate with the consultant" in text and "85" in text


def test_longer_number_in_cell_widens_within_cell_instead_of_wrapping(tmp_path):
    session = _table_session(tmp_path)
    cell = next(b for b in edit_service.get_text_blocks(session, 0) if b.text == "85")
    edit_service.replace_text(session, 0, cell.rect, "100.5", 11, "sarabun", (0, 0, 0), block_id=cell.block_id)
    page = session.doc[0]
    assert "100.5" in page.get_text()                      # ไม่ถูกตัดเป็นหลายบรรทัด
    edited = next(b for b in edit_service.get_text_blocks(session, 0) if b.text == "100.5")
    assert edited.rect.x1 <= 400                           # ไม่ล้นเส้นขอบตารางด้านขวา
