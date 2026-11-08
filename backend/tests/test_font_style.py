"""ชื่อฟอนต์จาก PDF → ฟอนต์ในระบบ (fonts.match_pdf_font_name) และเครื่องจัดรูปอักษรไทย"""
import pytest


@pytest.mark.parametrize("pdf_name, bold, italic", [
    ("Kanit-Regular", False, False),
    ("Kanit", False, False),            # เดิม: "it" ใน Kanit → ตัวเอียง (Kanit Bold เลยเสียตัวหนา)
    ("KanitBold", True, False),
    ("Mitr-Medium", False, False),      # "it" ใน Mitr
    ("THSarabunIT9", False, False),     # ฟอนต์ราชการ TH SarabunIT๙ — "IT" คือชื่อฟอนต์ ไม่ใช่ตัวเอียง
    ("TH SarabunIT๙", False, False),
    ("THSarabunPSK-Bold", True, False),
    ("Arial-BoldItalicMT", True, True),
    ("THSarabunNew,BoldItalic", True, True),
    ("Helvetica-BdIt", True, True),
    ("Sarabun-Italic", False, True),
    ("TimesNewRomanPSMT", False, False),
])
def test_detect_style_from_pdf_font_name(pdf_name, bold, italic):
    from app.services.fonts import _detect_style_from_name

    assert _detect_style_from_name(pdf_name) == (bold, italic)


def test_match_pdf_font_name_keeps_kanit_bold_and_sarabun_it9_upright():
    from app.services import fonts

    assert fonts.match_pdf_font_name("KanitBold") == "kanit-bold"
    assert fonts.match_pdf_font_name("ABCDEF+THSarabunIT9") == "sarabun"   # ไม่แนบ TH Sarabun New → Sarabun
    assert fonts.match_pdf_font_name("THSarabunIT9", flag_italic=True) == "sarabun-italic"  # flag ของ span ยังมีผล


def test_thai_shaping_engines_available():
    """fpdf2 ใช้ uharfbuzz · ตราลายเซ็นดิจิทัลใช้ Pillow RAQM — ขาดแล้วสระ/วรรณยุกต์วางผิดตำแหน่งแบบเงียบ ๆ"""
    from PIL import features

    import uharfbuzz  # noqa: F401
    assert features.check("raqm")
