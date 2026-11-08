"""OCR ภาษาไทย (เฟส 5b, app/services/ocr_thai.py) — ตัดบรรทัดเอง, ลบเส้นตาราง/จุดไข่ปลา, แก้คำด้วยพจนานุกรม

ส่วนที่ต้องใช้ tesseract ภาษาไทยจะข้ามบนเครื่องที่ไม่มี (Docker image มีอยู่แล้ว)
"""
import io
import shutil
import subprocess
from pathlib import Path

import fitz
import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.services import ocr_thai

FONTS = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts"


def _has_thai_tesseract() -> bool:
    if not shutil.which("tesseract"):
        return False
    return "tha" in subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split()


needs_tesseract = pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย")


def _render(lines: list[str], font: str = "Sarabun-Regular.ttf", size: float = 18, dpi: int = 300) -> Image.Image:
    """ข้อความ shape ด้วย fpdf2 (HarfBuzz) → ภาพเทา"""
    from fpdf import FPDF

    line_h = size * 1.7
    width = 40 + max(len(ln) for ln in lines) * size * 0.62
    pdf = FPDF(unit="pt", format=(width, 20 + line_h * len(lines)))
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0)
    pdf.add_page()
    pdf.add_font("F", "", str(FONTS / font))
    pdf.set_font("F", size=size)
    pdf.set_text_shaping(True, script="thai", language="tha")
    for i, ln in enumerate(lines):
        pdf.set_xy(20, 10 + i * line_h)
        pdf.cell(width - 40, line_h, ln)
    pix = fitz.open(stream=bytes(pdf.output()))[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


# ---------------------------------------------------------------- ไม่ต้องใช้ tesseract

def test_segment_lines_merges_tone_mark_rows_into_main_line():
    mask = np.zeros((120, 200), dtype=bool)
    mask[10:14, 20:180:10] = True      # แถววรรณยุกต์/สระบน (บาง) ของบรรทัดแรก
    mask[17:40, 10:190] = True         # บรรทัดแรก
    mask[60:83, 10:190] = True         # บรรทัดที่สอง
    mask[85:89, 30:150:12] = True      # สระล่างของบรรทัดที่สอง
    assert ocr_thai.segment_lines(mask) == [(10, 40), (60, 89)]


def test_segment_lines_big_logo_does_not_swallow_text_lines():
    """โลโก้สูงแถบเดียวบนหัวกระดาษ ต้องไม่ทำให้ทุกบรรทัดกลายเป็น "แถบบาง" แล้วรวมเป็นแถบเดียวทั้งหน้า"""
    mask = np.zeros((400, 200), dtype=bool)
    mask[5:125, 70:130] = True                 # โลโก้
    for k in range(6):
        y = 150 + 40 * k
        mask[y:y + 3, 20:180:10] = True        # วรรณยุกต์
        mask[y + 6:y + 26, 10:190] = True      # บรรทัด
    segs = ocr_thai.segment_lines(mask)
    assert len(segs) == 7
    assert segs[1] == (150, 176)


def test_remove_rules_erases_table_borders_but_keeps_text():
    img = _render(["หนังสือรับรองการเป็นผู้ประกันตน", "ผู้อำนวยการสำนักเงินสมทบ"])
    framed = img.copy()
    d = ImageDraw.Draw(framed)
    d.rectangle((3, 3, img.width - 4, img.height - 4), outline=0, width=3)
    mask = ocr_thai._ink(framed)
    cleaned, m2 = ocr_thai.remove_rules(framed, mask)
    a = np.asarray(cleaned)
    assert a[4, img.width // 2] == 255 and a[img.height // 2, 4] == 255      # เส้นกรอบหาย
    assert m2.sum() > 0.8 * ocr_thai._ink(img).sum()                          # ตัวอักษรยังอยู่เกือบครบ


def test_deskew_angle_detects_small_rotation():
    img = _render(["หนังสือรับรองการเป็นผู้ประกันตน"] * 4, dpi=200)
    tilted = img.rotate(1.5, resample=Image.BICUBIC, expand=True, fillcolor=255)
    assert ocr_thai.deskew_angle(ocr_thai._ink(img)) == 0.0
    assert abs(ocr_thai.deskew_angle(ocr_thai._ink(tilted)) + 1.5) <= 0.25


@pytest.mark.parametrize("ocr_text, expected", [
    ("ผู้รัปมอบอำนาจ", "ผู้รับมอบอำนาจ"),     # บ/ป ในส่วนที่ไม่รู้จัก
    ("อำเภอปากเคร็ด", "อำเภอปากเกร็ด"),       # ก/ค
    ("น้าหนักสุทธิ", "น้ำหนักสุทธิ"),          # นิคหิตหายเมื่อซ้อนวรรณยุกต์ (ตัดคำได้น้อยลง)
    ("ทาสี", "ทาสี"),                          # คำที่ถูกอยู่แล้วไม่แก้ (บั๊กเดิมของ frontend: ทาสี → ทำสี)
    ("คานาดา", "คานาดา"),
    ("ประจำป", "ประจำป"),                      # ส่วนที่ไม่รู้จักแก้ทางเดียวไม่ได้ → คงเดิม
    ("INV-2026/0142", "INV-2026/0142"),        # ไม่แตะภาษาอังกฤษ/ตัวเลข
])
def test_correct_word(ocr_text, expected):
    assert ocr_thai.correct_word(ocr_text) == expected


def test_merge_split_words_only_when_result_is_a_dictionary_word():
    W = ocr_thai.OcrWord
    merged = ocr_thai._merge_split_words([W("เห็นสมคว", (0, 0, 10, 10), 90), W("รอนุญาต", (12, 0, 30, 10), 80)])
    assert [w.text for w in merged] == ["เห็นสมควรอนุญาต"] and merged[0].box == (0, 0, 30, 10)
    kept = ocr_thai._merge_split_words([W("ขอแสดง", (0, 0, 10, 10), 90), W("ความนับถือ", (12, 0, 30, 10), 90)])
    assert [w.text for w in kept] == ["ขอแสดง", "ความนับถือ"]


def test_words_from_line_maps_spaces_from_txt_to_token_boxes():
    tok = lambda t, x: {"text": t, "left": x, "top": 0, "width": 10, "height": 20, "conf": "90"}  # noqa: E731
    words = ocr_thai._words_from_line("ขอ แสดง", [tok("ข", 0), tok("อ", 10), tok("แส", 30), tok("ดง", 40)], 5, 7)
    assert [(w.text, w.box) for w in words] == [("ขอ", (5, 7, 25, 27)), ("แสดง", (35, 7, 55, 27))]


# ---------------------------------------------------------------- ใช้ tesseract จริง

@needs_tesseract
def test_recognize_keeps_tone_marks_that_plain_psm6_drops():
    # ฟอนต์ตัวใหญ่: เดิม tesseract แยกแถววรรณยุกต์ออกเป็นบรรทัดขยะ → "ที่" กลายเป็น "ที"
    lines = ["จึงขอให้ท่านติดต่อชำระภายในเจ็ดวัน", "ผู้ใหญ่บ้านหมู่ที่ ๗ ตำบลศรีสุนทร", "ขอแสดงความนับถือ"]
    text = ocr_thai.recognize_text(_render(lines))
    got = [ln.replace(" ", "") for ln in text.splitlines()]
    assert "จึงขอให้ท่านติดต่อชำระภายในเจ็ดวัน" in got
    assert "ขอแสดงความนับถือ" in got
    assert any(ln.startswith("ผู้ใหญ่บ้านหมู่ที่") for ln in got)
    assert len(got) == 3  # ไม่มีบรรทัดขยะจากแถววรรณยุกต์


@needs_tesseract
def test_recognize_drops_dot_leaders_and_table_lines():
    img = _render(["ลงชื่อ ................................ ผู้รับมอบอำนาจ", "เลขที่ INV-2026/0142"], font="Sarabun-Regular.ttf",
                  size=14, dpi=200)
    d = ImageDraw.Draw(img)
    d.rectangle((2, 2, img.width - 3, img.height - 3), outline=0, width=2)
    lines = [ln.text for ln in ocr_thai.recognize(img)]
    assert lines[0].replace(" ", "") == "ลงชื่อผู้รับมอบอำนาจ"
    assert "INV-2026/0142" in lines[1]


@needs_tesseract
def test_recognize_word_boxes_are_in_input_image_coordinates():
    img = _render(["ผู้อำนวยการสำนักเงินสมทบ"], size=16, dpi=200)
    tilted = img.rotate(-1.2, resample=Image.BICUBIC, expand=True, fillcolor=255)
    for im in (img, tilted):
        words = [w for ln in ocr_thai.recognize(im) for w in ln.words]
        assert words and "".join(w.text for w in words) == "ผู้อำนวยการสำนักเงินสมทบ"
        x0, y0, x1, y1 = words[0].box
        ink = np.argwhere(ocr_thai._ink(im))
        assert abs(y0 - ink[:, 0].min()) < 15 and abs(x0 - ink[:, 1].min()) < 15


@needs_tesseract
def test_uploaded_image_becomes_searchable_pdf(client, make_user):
    from app.core.session import session_manager
    from app.services.pdf_service import text_index

    _, headers = make_user()
    buf = io.BytesIO()
    _render(["หนังสือรับรองการเป็นผู้ประกันตน", "ผู้อำนวยการสำนักเงินสมทบ"], dpi=200).save(buf, "PNG", dpi=(200, 200))
    r = client.post("/pdf/upload", headers=headers, files={"file": ("scan.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["filename"] == "scan.pdf"
    page = session_manager.get(r.json()["session_id"]).doc[0]
    assert abs(page.rect.width - Image.open(buf).width * 72 / 200) < 1   # ขนาดหน้าตาม dpi ของรูป
    pt = text_index.page_text(page)
    assert text_index.find(pt, text_index.keyword_pattern("ผู้อำนวยการสำนักเงินสมทบ"))


def test_ocr_layer_stops_at_time_budget_and_reports_remaining(monkeypatch):
    from app.services.pdf_service import ocr

    doc = fitz.open()
    png = io.BytesIO()
    _render(["ผู้อำนวยการสำนักเงินสมทบ"], dpi=150).save(png, "PNG")
    for _ in range(3):
        doc.new_page().insert_image(fitz.Rect(72, 72, 500, 160), stream=png.getvalue())

    class S:
        pass

    session = S()
    session.doc, session.is_unlocked = doc, True
    session.mark_dirty = session.push_history = lambda: None
    calls = []
    monkeypatch.setattr(ocr, "_ocr_page_regions", lambda page, *a: calls.append(page.number) or 1)
    monkeypatch.setattr(ocr, "OCR_TIME_BUDGET", -1.0)   # หมดเวลาตั้งแต่ก่อนเริ่มหน้าแรก
    r = ocr.add_ocr_text_layer(session)
    assert calls == [] and r["skipped_pages"] == 3
    monkeypatch.setattr(ocr, "OCR_TIME_BUDGET", 1000.0)
    r = ocr.add_ocr_text_layer(session)
    assert calls == [0, 1, 2] and r == {"pages": [1, 2, 3], "words": 3, "skipped_pages": 0}


def test_numbers_are_not_dot_leaders():
    from app.services.pdf_service.ocr import _looks_like_leader

    for word in ("๕๐๐", "00001", "1,000", "2550"):
        assert not _looks_like_leader(word), word
    for leader in (".....", "จจจจจ", "๑๑๑๑๑๑๑", "------"):
        assert _looks_like_leader(leader), leader


@needs_tesseract
def test_short_thai_image_upload_keeps_numbers_and_thai():
    """รูปข้อความไทยสั้น ๆ (ไม่กี่บรรทัด): OSD มักทายเป็นอักษรละติน — ต้องไม่ถูกอ่านด้วยโมเดลอังกฤษทั้งภาพ
    และตัวเลขไทย/ตัวเลขที่ซ้ำตัว ("๕๐๐", "00001") ต้องไม่ถูกตัดทิ้งเป็นจุดไข่ปลา"""
    import fitz as _fitz

    from app.services.pdf_service import image_to_searchable_pdf, text_index

    buf = io.BytesIO()
    _render(["น้ำหนักสุทธิ ๕๐๐ กรัม ผลิตในประเทศไทย", "เลขประจำตัวผู้เสียภาษี 0105555123456 สาขาที่ 00001"],
            font="Sarabun-Regular.ttf", size=14, dpi=300).save(buf, "PNG", dpi=(300, 300))
    page = _fitz.open(stream=image_to_searchable_pdf(buf.getvalue()))[0]
    pt = text_index.page_text(page)
    for word in ("น้ำหนักสุทธิ", "๕๐๐", "ประเทศไทย", "ผู้เสียภาษี", "00001"):
        assert text_index.find(pt, text_index.keyword_pattern(word)), (word, pt.text)


@pytest.mark.parametrize("font", ["Sarabun-Regular.ttf", "Kanit-Regular.ttf"])
def test_thai_digit_shapes_are_recognised(font):
    """เลขไทยอ่านด้วยการเทียบรูปร่าง (Tesseract อ่านเลขไทยพลาดบ่อยมาก: ๖→๐, ๗→ข, ๙→«)"""
    from app.services import thai_digits

    right = 0
    for number in ("๒๕๖๙", "๐๑๓๔", "๕๗๘", "๑๒๓"):
        got = thai_digits.read_digits(_render([number], font=font, size=16, dpi=200))
        assert len(got) == len(number), (font, number, got)
        # ตัวที่บอกว่ามั่นใจต้องถูก (ตัวที่ไม่มั่นใจ ระบบจะไม่นำไปแก้ผลของ Tesseract)
        assert all(ch == want for (ch, sure, _b), want in zip(got, number) if sure), (font, number, got)
        right += "".join(ch for ch, _s, _b in got) == number
    assert right >= 3, font


@needs_tesseract
def test_recognize_fixes_thai_numerals_in_dates():
    lines = ocr_thai.recognize(_render(["ออกให้ ณ วันที่ ๒๗ มกราคม พ.ศ. ๒๕๖๖", "ประกาศ ณ วันที่ ๑๘ เมษายน พ.ศ. ๒๕๖๘"],
                                       font="Sarabun-Regular.ttf", size=12, dpi=200))
    text = " ".join(ln.text for ln in lines).replace(" ", "")
    for part in ("๒๗มกราคม", "พ.ศ.๒๕๖๖", "๑๘เมษายน", "พ.ศ.๒๕๖๘"):
        assert part in text, (part, text)


def test_digit_lookalikes_in_phone_numbers():
    line = ocr_thai.OcrLine([ocr_thai.OcrWord(t, (0, 0, 1, 1), 90) for t in ("โทร", "O", "2123", "4567", "1O5")])
    assert [w.text for w in ocr_thai._fix_digit_lookalikes(line).words] == ["โทร", "0", "2123", "4567", "105"]
