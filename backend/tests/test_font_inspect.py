"""ตรวจฟอนต์ (v1.38.0): ชื่อฟอนต์จริงในไฟล์ ขนาด สี การฝัง — ในย่อหน้าที่เลือกแก้ไข, ระดับ span และทั้งเอกสาร"""
from pathlib import Path

import fitz
from fpdf import FPDF

FONTS = Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts"


def _pdf() -> bytes:
    """หน้า 1: ย่อหน้าเดียวผสม Sarabun ตัวหนา 16 pt + Kanit 12 pt สีแดง (ฝังแบบ subset ด้วย fpdf2)
    หน้า 2: Helvetica (ฟอนต์มาตรฐาน PDF ไม่ฝัง)"""
    pdf = FPDF(unit="pt", format="A4")
    pdf.add_font("Sarabun", "B", str(FONTS / "Sarabun-Bold.ttf"))
    pdf.add_font("Kanit", "", str(FONTS / "Kanit-Regular.ttf"))
    pdf.set_text_shaping(True)
    pdf.add_page()
    pdf.set_xy(72, 72)
    pdf.set_font("Sarabun", "B", 16)
    pdf.write(20, "ใบแจ้งค่าบริการ ")
    pdf.set_font("Kanit", "", 12)
    pdf.set_text_color(255, 0, 0)
    pdf.write(20, "ยอดรวม")
    pdf.add_page()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(72, 72)
    pdf.write(14, "Plain Helvetica")
    doc = fitz.open("pdf", bytes(pdf.output()))
    return doc.tobytes()


def test_text_block_lists_fonts_in_file(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _pdf())
    blocks = client.get(f"/edit/{sid}/page/0/text-blocks", headers=h).json()
    block = next(b for b in blocks if "ใบแจ้ง" in b["text"])
    fonts = block["source_fonts"]
    assert [f["name"] for f in fonts] == ["SarabunBold", "Kanit"]  # ใช้มากสุดก่อน
    sarabun, kanit = fonts
    assert sarabun["size"] == 16 and sarabun["bold"] and sarabun["embedded"] and sarabun["subset"]
    assert sarabun["color"] == "#000000" and kanit["color"] == "#ff0000" and kanit["size"] == 12
    assert sarabun["chars"] > kanit["chars"] > 0
    assert block["fontname"].startswith("sarabun")  # ฟอนต์ระบบที่ใช้แทนยังคืนมาเหมือนเดิม
    assert block["fontsize"] == 16  # ตระกูลเดียวกับฟอนต์ระบบ → ใช้ขนาดจริงในไฟล์ (ไม่ใช่ค่าประมาณจากกรอบ)


def test_same_family():
    from app.services.font_inspect import same_family

    assert same_family("Sarabun-Regular", "sarabun") and same_family("SarabunBold", "sarabun-bold")
    assert not same_family("THSarabunNew-Bold", "sarabun-bold") and not same_family("Kanit", "sarabun")


def test_font_spans_and_document_fonts(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _pdf())
    spans = client.get(f"/edit/{sid}/page/1/font-spans", headers=h).json()["spans"]
    [helv] = [s for s in spans if "Helvetica" in s["text"]]
    assert helv["name"] == "Helvetica" and helv["base14"] and not helv["embedded"] and helv["size"] == 10
    assert helv["bbox"]["x1"] > helv["bbox"]["x0"]

    fonts = client.get(f"/edit/{sid}/fonts", headers=h).json()["fonts"]
    by_name = {f["name"]: f for f in fonts}
    assert by_name["SarabunBold"]["pages"] == [1] and by_name["SarabunBold"]["embedded"]
    assert by_name["Helvetica"]["pages"] == [2] and not by_name["Helvetica"]["embedded"]
    assert by_name["Kanit"]["type"] == "Type 0 (CID)"


def test_font_endpoints_owner_only_and_page_range(client, make_user, upload):
    _, owner = make_user()
    _, other = make_user()
    sid = upload(owner, _pdf())
    assert client.get(f"/edit/{sid}/fonts", headers=other).status_code in (403, 404)
    assert client.get(f"/edit/{sid}/page/9/font-spans", headers=owner).status_code == 400
