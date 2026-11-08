"""ตัวเทียบ PDF (compare_service.engine): ข้อความไทย/อังกฤษ · หน้าแทรก/ลบ · ข้อความไหลข้ามหน้า · ภาพต่าง · หน้าหมุน · OCR"""
import io
import shutil
from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.compare_service import Options, compare_documents
from app.services.compare_service import engine

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")


def _doc(pages: list[list[str]], *, rotate: int = 0, box: tuple | None = None, size=(595, 842)) -> fitz.Document:
    """pages = [[บรรทัด, ...], ...] — box = (หน้า, x0, y0, x1, y1) วาดสี่เหลี่ยมทึบ (จำลองรูป/ลายเซ็น)"""
    doc = fitz.open()
    for i, lines in enumerate(pages):
        p = doc.new_page(width=size[0], height=size[1])
        p.insert_font(fontname="sar", fontfile=FONT)
        for n, line in enumerate(lines):
            p.insert_text((72, 100 + 24 * n), line, fontname="sar", fontsize=14)
        if box and box[0] == i:
            p.draw_rect(fitz.Rect(*box[1:]), color=(0, 0, 0), fill=(0.2, 0.2, 0.2))
        if rotate:
            p.set_rotation(rotate)
    return fitz.open("pdf", doc.tobytes())


def _kinds(result):
    return [(c["kind"], c["a_text"], c["b_text"]) for c in result["changes"]]


def test_identical_documents():
    a = _doc([["สัญญาเช่าบ้าน ฉบับที่ 1", "ผู้เช่าตกลงชำระค่าเช่า 5,000 บาท"]])
    b = _doc([["สัญญาเช่าบ้าน ฉบับที่ 1", "ผู้เช่าตกลงชำระค่าเช่า 5,000 บาท"]])
    r = compare_documents(a, b)
    assert r["identical"] and r["summary"]["total"] == 0 and r["pairs"] == [[0, 0]]


def test_thai_word_replace_insert_delete_with_positions():
    a = _doc([["ผู้เช่าตกลงชำระค่าเช่าเดือนละ 5,000 บาท", "ภายในวันที่ 5 ของทุกเดือน", "หากผิดนัดปรับวันละ 100 บาท"]])
    b = _doc([["ผู้เช่าตกลงชำระค่าเช่าเดือนละ 6,500 บาท", "ภายในวันที่ 5 ของทุกเดือน โดยโอนเข้าบัญชี", "หากผิดนัดวันละ 100 บาท"]])
    r = compare_documents(a, b, Options(visual=False))
    kinds = _kinds(r)
    assert ("replace", "5,000", "6,500") in kinds
    assert any(k == "insert" and "โอน" in bt for k, _, bt in kinds)
    assert ("delete", "ปรับ", "") in kinds
    rep = next(c for c in r["changes"] if c["kind"] == "replace")
    (ra,), (rb,) = rep["a_rects"], rep["b_rects"]
    assert ra["page"] == rb["page"] == 0 and 80 < ra["y0"] < 100 and ra["x0"] > 150  # อยู่ท้ายบรรทัดแรก
    ins = next(c for c in r["changes"] if c["kind"] == "insert")
    assert ins["a_rects"] == [] and ins["a_anchor"]["page"] == 0  # ชี้ตำแหน่งในไฟล์เดิมที่ข้อความถูกเพิ่ม


def test_reflow_across_pages_is_not_a_change():
    lines = [f"ข้อ {i} รายละเอียดเงื่อนไขของสัญญา" for i in range(1, 41)]
    a = _doc([lines[:30], lines[30:]])
    b = _doc([["บทนำเพิ่มเติม"] + lines[:29], lines[29:]])  # แทรกบรรทัดแรก → ข้อ 30 ไหลไปหน้า 2
    r = compare_documents(a, b, Options(visual=False))
    assert _kinds(r) == [("insert", "", "บทนำเพิ่มเติม")]
    assert r["pairs"] == [[0, 0], [1, 1]]


def test_inserted_and_deleted_pages_are_paired_by_content():
    p1, p2, p3 = ["หน้าแรก ปก"], ["บทที่ 1 ความเป็นมา"], ["บทที่ 2 วิธีดำเนินการ"]
    a = _doc([p1, p2, p3])
    b = _doc([p1, ["ภาคผนวกใหม่ทั้งหน้า Appendix"], p2, p3])
    r = compare_documents(a, b, Options(visual=False))
    assert r["pairs"] == [[0, 0], [None, 1], [1, 2], [2, 3]]
    assert any(c["kind"] == "page_insert" for c in r["changes"])
    r2 = compare_documents(b, a, Options(visual=False))
    assert [None, 1] not in r2["pairs"] and [1, None] in r2["pairs"]


def test_visual_change_outside_text():
    a = _doc([["ลงชื่อผู้เช่า"]])
    b = _doc([["ลงชื่อผู้เช่า"]], box=(0, 300, 400, 420, 460))  # ลายเซ็น/ตราประทับเพิ่ม
    r = compare_documents(a, b)
    vis = [c for c in r["changes"] if c["kind"] == "visual"]
    assert len(vis) == 1
    box = vis[0]["b_rects"][0]
    assert box["x0"] <= 302 and box["x1"] >= 398 and box["y0"] <= 422 and box["y1"] >= 458
    assert r["summary"]["visual"] == 1 and r["summary"]["total"] == 1


def test_text_change_is_not_double_counted_as_visual():
    a = _doc([["Total amount 1,000 THB"]])
    b = _doc([["Total amount 9,999 THB"]])
    r = compare_documents(a, b)
    assert [c["kind"] for c in r["changes"]] == ["replace"]


def test_rotated_page_coordinates_match_rendered_image():
    a = _doc([["Hello world"]], rotate=90)
    b = _doc([["Hello there"]], rotate=90)
    r = compare_documents(a, b, Options(visual=False))
    (rb,) = r["changes"][0]["b_rects"]
    w, h = r["b"]["page_sizes"][0]
    assert (w, h) == (842, 595)  # หน้าหมุนแล้ว
    # หมุน 90° ตามเข็ม: ข้อความแนวนอนกลายเป็นแนวตั้งชิดขวา
    assert rb["x0"] > 600 and rb["y1"] - rb["y0"] > rb["x1"] - rb["x0"]


def test_digit_styles_and_options():
    a = _doc([["ราคา ๕๐๐ บาท Contract"]])
    b = _doc([["ราคา 500 บาท contract"]])
    r = compare_documents(a, b, Options(visual=False))
    assert _kinds(r) == [("replace", "Contract", "contract")]
    assert compare_documents(a, b, Options(visual=False, ignore_case=True))["identical"]
    assert not compare_documents(a, b, Options(visual=False, ignore_digits_style=False, ignore_case=True))["identical"]


def test_page_size_change():
    a = _doc([["A4 page"]])
    b = _doc([["A4 page"]], size=(612, 792))
    r = compare_documents(a, b)
    assert [c["kind"] for c in r["changes"]] == ["page_size"]


def test_too_many_pages():
    big = fitz.open()
    for _ in range(engine.MAX_PAGES + 1):
        big.new_page()
    with pytest.raises(engine.CompareError):
        compare_documents(big, _doc([["x"]]))


def _scan(lines: list[str]) -> fitz.Document:
    img = Image.new("L", (1240, 1754), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 44)
    for n, line in enumerate(lines):
        draw.text((150, 200 + 90 * n), line, fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    return fitz.open("pdf", doc.tobytes())


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="ต้องมี Tesseract")
def test_scanned_pages_are_compared_with_ocr():
    a = _scan(["Payment due 15 March", "Amount 4500 Baht"])
    b = _scan(["Payment due 30 March", "Amount 4500 Baht"])
    r = compare_documents(a, b)
    assert r["a"]["ocr_pages"] == [0] and r["b"]["ocr_pages"] == [0]
    assert ("replace", "15", "30") in _kinds(r)
    assert not any(c["kind"] == "visual" for c in r["changes"])  # สแกน: ไม่เทียบพิกเซล
    off = compare_documents(a, b, Options(ocr=False))
    assert off["a"]["empty_pages"] == [0] and any(c["kind"] == "visual" for c in off["changes"])


def test_progress_reported():
    seen = []
    compare_documents(_doc([["a"]]), _doc([["b"]]), progress=lambda p, m: seen.append(p))
    assert seen[0] <= 5 and seen[-1] == 100 and seen == sorted(seen)


def test_long_repetitive_document_with_inserted_page():
    """เอกสารยาวที่บรรทัดคล้ายกันมาก + แทรกหน้ากลางเอกสาร → ต้องเหลือแค่จุดที่ต่างจริง (เดิมเทียบทีละหน้าแล้วเพี้ยนทั้งท้ายเอกสาร)"""
    pages = [[f"ข้อ {p}.{i} ผู้เช่าตกลงชำระค่าเช่าและค่าบริการตามสัญญา" for i in range(25)] for p in range(40)]
    pb = [list(x) for x in pages]
    pb[7][3] = "ข้อ 7.3 ผู้เช่าตกลงชำระค่าเช่าเพิ่มเติม"
    pb.insert(20, ["หน้าใหม่ แทรกกลางเอกสาร"])
    r = compare_documents(_doc(pages), _doc(pb), Options(visual=False))
    assert r["summary"]["total"] == 2 and r["summary"]["replace"] == 1 and r["summary"]["page_insert"] == 1
    assert [None, 20] in r["pairs"] and [39, 40] in r["pairs"]


def _signature_png() -> bytes:
    """ลายเซ็นสีฟ้าอ่อน เส้นบาง (เหมือนเซ็นด้วยนิ้ว)"""
    img = Image.new("RGBA", (600, 200), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.line([(20, 150), (80, 40), (120, 160), (200, 60), (380, 30), (300, 120), (560, 90)], fill=(120, 150, 230, 255), width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_signature_stamp_is_one_change_at_the_image():
    """ไฟล์ก่อน/หลังลงนาม: ตราลงนามเป็นรูปเดียว (ลายเซ็นสีอ่อน + กรอบ + ข้อความสีเทา) → จุดต่างเดียวตรงกรอบรูป"""
    from app.services.signing_pdf import _stamp_image

    a = _doc([["เอกสารแนบ", "ลงชื่อผู้รับมอบ"]])
    b = fitz.open("pdf", a.tobytes())
    stamp = _stamp_image(250, 70, ["jaturon.p@example.com", "ลงนามอิเล็กทรอนิกส์ 29/10/2026 19:51"], _signature_png())
    buf = io.BytesIO()
    stamp.save(buf, "PNG")
    b[0].insert_image(fitz.Rect(150, 400, 400, 470), stream=buf.getvalue())
    b = fitz.open("pdf", b.tobytes())
    r = compare_documents(a, b)
    assert [(c["kind"], c["note"]) for c in r["changes"]] == [("visual", "เพิ่มรูป (เช่น ลายเซ็น ตราประทับ)")]
    box = r["changes"][0]["b_rects"][0]
    assert (round(box["x0"]), round(box["y0"]), round(box["x1"]), round(box["y1"])) == (150, 400, 400, 470)


def test_thin_light_vector_line_is_detected_as_one_box():
    a = _doc([["หัวข้อ"]])
    b = fitz.open("pdf", a.tobytes())
    shape = b[0].new_shape()
    shape.draw_polyline([(100, 500), (180, 460), (260, 520), (340, 470)])
    shape.finish(color=(0.6, 0.7, 0.95), width=0.6)
    shape.commit()
    r = compare_documents(a, fitz.open("pdf", b.tobytes()))
    vis = [c for c in r["changes"] if c["kind"] == "visual"]
    assert len(vis) == 1
    box = vis[0]["b_rects"][0]
    assert box["x0"] <= 102 and box["x1"] >= 338 and box["y0"] <= 462 and box["y1"] >= 518


def test_text_edited_in_editor_keeps_reading_order_and_ignores_spacing():
    """ข้อความที่แก้ใน Editor ถูกเขียนต่อท้าย content stream — ต้องเรียงตามตำแหน่งบนหน้า (เดิมเห็นเป็นลบบรรทัด
    แล้วไปเพิ่มรวมกันท้ายหน้า) · "(Tax Invoice )" กับ "(Tax Invoice)" ต่างแค่ช่องว่าง ไม่ใช่จุดต่าง"""
    lines = ["2.1 งานในขอบเขต (In Scope)", "2.1.1 Requirement & System Design", "รับข้อมูลทดสอบ (Test Data)",
             "เพิ่ม PDF Output (Tax Invoice) สำหรับส่ง Vendor", "เพิ่ม Text Export สำหรับส่งทีมบัญชี"]
    a = _doc([lines])
    b = fitz.open("pdf", a.tobytes())
    page = b[0]
    for i, new in ((1, "2.1.1 Requirement & System Design1"), (3, "เพิ่ม PDF Output (Tax Invoice ) สำหรับส่ง Vendor")):
        y = 100 + 24 * i
        page.add_redact_annot(fitz.Rect(70, y - 12, 560, y + 4))
        page.apply_redactions()
        page.insert_font(fontname="sar2", fontfile=FONT)
        page.insert_text((72, y), new, fontname="sar2", fontsize=14)
    r = compare_documents(a, fitz.open("pdf", b.tobytes()), Options(visual=False))
    assert _kinds(r) == [("insert", "", "1")]


def test_deleted_line_caret_points_to_next_line_start():
    a = _doc([["2.1 งานในขอบเขต (In Scope)", "2.1.1 Requirement", "รับข้อมูลทดสอบ"]])
    b = _doc([["2.1 งานในขอบเขต (In Scope)", "รับข้อมูลทดสอบ"]])
    (c,) = compare_documents(a, b, Options(visual=False))["changes"]
    assert c["kind"] == "delete" and c["b_rects"] == []
    assert c["b_anchor"]["x0"] < 75 and 100 < c["b_anchor"]["y1"] < 130   # ต้นบรรทัด "รับข้อมูลทดสอบ" ไม่ใช่ท้าย "(In Scope)"


def test_edited_bullet_line_keeps_its_bullet():
    """แก้ข้อความบรรทัดที่มี bullet: Editor เขียนข้อความใหม่เป็นบล็อกแยก (สูงกว่าเดิมเล็กน้อย) แต่ bullet อยู่ที่เดิม
    → ต้องเห็นแค่คำที่เพิ่ม ไม่ใช่ลบทั้งบรรทัดแล้วเพิ่มทั้งบรรทัด"""
    rows = ["• ปรับแก้ Template เดิม", "• เพิ่ม PDF Output (Tax Invoice) สำหรับส่ง Vendor", "• เพิ่ม Text Export สำหรับส่ง Vendor"]
    a = _doc([rows])
    b = fitz.open("pdf", a.tobytes())
    page = b[0]
    y = 100 + 24
    page.add_redact_annot(fitz.Rect(84, y - 13, 560, y + 4))   # ลบเฉพาะข้อความ — bullet ยังอยู่
    page.apply_redactions()
    page.insert_font(fontname="sar2", fontfile=FONT)
    page.insert_text((85, y - 3), "เพิ่ม PDF Output (Tax Invoice) สำหรับส่ง Vendor เพิ่มข้อความ", fontname="sar2", fontsize=13)
    r = compare_documents(a, fitz.open("pdf", b.tobytes()), Options(visual=False))
    assert _kinds(r) == [("insert", "", "เพิ่มข้อความ")]
