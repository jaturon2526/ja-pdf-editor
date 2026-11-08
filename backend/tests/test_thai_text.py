"""จัดรูปข้อความไทยที่ดึงจาก PDF (services/thai_text.py) — กรณีจากไฟล์จริงใน test_pdf_files/"""
import pytest

from app.services import thai_text as tt


@pytest.mark.parametrize("raw, expected", [
    # Word → PDF (TH SarabunPSK): นิคหิตของสระอำกลายเป็นช่องว่าง
    ("ที่จ าเป็นต่อธุรกรรม", "ที่จำเป็นต่อธุรกรรม"),
    ("ส าหรับ ส านักงาน", "สำหรับ สำนักงาน"),
    ("น ้ าหนัก", "น้ำหนัก"),
    # สระอำแตก
    ("คํา", "คำ"),
    ("นํ้า", "น้ำ"),
    ("น้ํา", "น้ำ"),
    # ำ มาก่อนวรรณยุกต์
    ("นำ้", "น้ำ"),
    # PUA ของฟอนต์ไทยรุ่นเก่า
    ("ก\uf70aา", "ก่า"),
    ("ป\uf701\uf70bน", "ปิ้น"),
    ("\uf700าน", "ฐาน"),
    ("ก\uf711า", "กำ"),
    # สลับลำดับ / ซ้ำ / สระเอสองตัว / zero-width
    ("ก่ีบ", "กี่บ"),
    ("กิ่่", "กิ่"),
    ("เเม่", "แม่"),
    ("สวัส\u200bดี", "สวัสดี"),
    # ไม่แตะข้อความที่ถูกอยู่แล้ว
    ("ทาสีบ้าน คานาดา ตาราง", "ทาสีบ้าน คานาดา ตาราง"),
    ("Hello World 123", "Hello World 123"),
    ("ราคา 1,500 บาท", "ราคา 1,500 บาท"),
])
def test_normalize(raw, expected):
    assert tt.normalize(raw) == expected


def test_normalize_is_idempotent():
    for raw in ["ส าหรับ", "นํ้า", "ก\uf70aา", "เเม่"]:
        once = tt.normalize(raw)
        assert tt.normalize(once) == once


def test_chars_keep_positions():
    chars = list("ส าหรับ")
    out = tt.normalize_chars(chars)
    assert len(out) == len(chars)
    assert out[1] == "" and out[2] == "ำ"
    assert "".join(out) == "สำหรับ"


def test_misencoded_am_font():
    # หนังสือราชการ (THSarabunNew): glyph สระอา map เป็น ำ, สระอำจริง = ช่องว่าง + ำ
    raw = "ส ำนักงำนประกันสังคม ขอรับรองว่ำ ถนนติวำนนท์"
    assert tt.normalize(raw, misencoded_am=True) == "สำนักงานประกันสังคม ขอรับรองว่า ถนนติวานนท์"


def test_detects_misencoded_font_by_dictionary():
    bad = ("ส ำนักงำนประกันสังคม ขอรับรองว่ำ มีสถำนะเป็นผู้ประกันตน ในระบบประกันสังคมมำแล้ว "
           "เข้ำร่วมโครงกำร จึงเรียนมำเพื่อโปรดทรำบ ขอแสดงควำมนับถือ")
    good = "บริษัท จำกัด สำนักงานใหญ่ ใบส่งสินค้าสำหรับลูกค้า จำนวนเงิน ชำระแล้ว คำอธิบาย"
    assert tt.detect_misencoded_am_fonts({"THSarabunNew": bad, "Tahoma": good}) == {"THSarabunNew"}


def test_normalize_page_dict_rawdict_and_dict():
    rawdict = {"blocks": [{"type": 0, "lines": [{"spans": [
        {"font": "F", "chars": [{"c": c, "bbox": (i, 0, i + 1, 1)} for i, c in enumerate("จ าเป็น")]},
    ]}]}]}
    tt.normalize_page_dict(rawdict)
    chars = rawdict["blocks"][0]["lines"][0]["spans"][0]["chars"]
    assert "".join(ch["c"] for ch in chars) == "จำเป็น"
    assert len(chars) == 7  # กรอบเดิมยังอยู่ครบ

    d = {"blocks": [{"type": 0, "lines": [{"spans": [
        {"font": "F", "text": "ส"}, {"font": "F", "text": " าหรับ"},
    ]}]}]}
    tt.normalize_page_dict(d)
    assert "".join(s["text"] for s in d["blocks"][0]["lines"][0]["spans"]) == "สำหรับ"


def test_convert_service_uses_shared_normalizer():
    from app.services.convert_service import _normalize_thai_text

    assert _normalize_thai_text("ส าหรับ นํ้า") == "สำหรับ น้ำ"


# ---------------------------------------------------------------- วงกลมสระอำที่วาดเป็นเส้น (เฟส 3)

def _pdf_with_vector_circles(words, circle_on, font="Sarabun-Regular.ttf", size=20):
    """วางคำทีละคำ แล้ววาดวงแหวนนิคหิตเป็นเส้นเหนือสระอาของคำที่อยู่ใน circle_on (จำลอง PDF ที่วงกลมสระอำกลายเป็นรูปวาด)"""
    from pathlib import Path

    import fitz

    fontfile = str(Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / font)
    doc = fitz.open()
    page = doc.new_page()
    x = 50
    for w in words:
        page.insert_text((x, 100), w, fontsize=size, fontname="f", fontfile=fontfile)
        x += 120
    raw = page.get_text("rawdict")
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = "".join(c["c"] for c in span["chars"])
                for w in circle_on:
                    i = text.find(w)
                    if i < 0:
                        continue
                    aa = i + w.index("า")
                    ox, base = span["chars"][aa]["origin"]
                    center = (ox - 0.12 * size, base - 0.75 * size)
                    page.draw_circle(center, 0.1 * size, color=(0, 0, 0), fill=None, width=0.04 * size)
    return doc


@pytest.mark.parametrize("font", ["Sarabun-Regular.ttf", "Sarabun-Bold.ttf"])
def test_vector_drawn_sara_am_is_restored(font):
    doc = _pdf_with_vector_circles(["สาหรับ", "กาหนด", "ทาสี", "น้าท่วม"], ["สาหรับ", "กาหนด", "น้าท่วม"], font=font)
    page = doc[0]
    raw = tt.normalize_page_dict(page.get_text("rawdict"), page)
    text = "".join(ch["c"] for b in raw["blocks"] for ln in b["lines"] for s in ln["spans"] for ch in s["chars"])
    assert "สำหรับ" in text and "กำหนด" in text and "น้ำท่วม" in text
    assert "ทาสี" in text  # ไม่มีวงกลม = สระอาจริง ไม่แตะ
    d = tt.normalize_page_dict(page.get_text("dict"), page)  # แบบ dict (หน้าแก้ไขข้อความ) ก็ได้ผลเดียวกัน
    joined = "".join(s["text"] for b in d["blocks"] for ln in b["lines"] for s in ln["spans"])
    assert "สำหรับ" in joined and "ทาสี" in joined


def test_unrelated_circles_do_not_change_text():
    doc = _pdf_with_vector_circles(["ทาสี", "ตาราง"], [])
    page = doc[0]
    page.draw_circle((80, 60), 8)          # วงกลมใหญ่ (เช่น ช่องติ๊ก) — ขนาดไม่เข้าเกณฑ์
    page.draw_circle((60, 140), 2)         # วงกลมเล็กใต้บรรทัด — ตำแหน่งไม่เข้าเกณฑ์
    raw = tt.normalize_page_dict(page.get_text("rawdict"), page)
    text = "".join(ch["c"] for b in raw["blocks"] for ln in b["lines"] for s in ln["spans"] for ch in s["chars"])
    assert "ทาสี" in text and "ตาราง" in text and "ำ" not in text


def test_nikhahit_without_unicode():
    assert tt.normalize("ส�าหรับ") == "สำหรับ"
    assert tt.normalize("A�า") == "A�า"  # ไม่ใช่หลังพยัญชนะไทย ไม่แตะ


def test_zero_width_sara_am_is_widened_so_copy_and_search_see_no_space():
    """ฟอนต์ Norasi (PDF จาก LibreOffice) รายงาน ำ กว้าง 0 แต่ตัวถัดไปเริ่มห่างออกไปเท่าความกว้างจริง —
    เดิมคัดลอก/ค้นหาได้ "สำ หรับ" (ระยะนั้นถูกนับเป็นช่องว่าง)"""
    def ch(c, x0, x1):
        return {"c": c, "bbox": (x0, 0.0, x1, 17.0)}

    chars = [ch("ส", 266.75, 272.69), ch("ำ", 272.7, 272.7), ch("ห", 276.7, 283.05), ch("ร", 283.09, 287.7),
             ch("ั", 287.69, 287.69), ch("บ", 287.69, 293.73)]
    page_dict = {"blocks": [{"type": 0, "lines": [{"spans": [{"size": 10.0, "font": "Norasi", "chars": chars}]}]}]}
    tt.normalize_page_dict(page_dict)
    out = page_dict["blocks"][0]["lines"][0]["spans"][0]["chars"]
    assert out[1]["bbox"][2] == 276.7          # ำ ยาวถึงตัวถัดไป
    assert out[4]["bbox"][0] == out[4]["bbox"][2]   # ไม้หันอากาศ (วางซ้อน) คงกว้าง 0
    assert out[0]["bbox"] == (266.75, 0.0, 272.69, 17.0)
