"""ค้นหาเพื่อเซ็นเซอร์ภาษาไทย (text_index + redact_by_search) — PDF จำลองอาการจากไฟล์จริง

ใส่ข้อความด้วย insert_text (ไม่ shape) เพื่อให้ข้อความที่ดึงกลับออกมา "ผิดรูป" แบบเดียวกับ PDF จริง:
PUA ของฟอนต์รุ่นเก่า, นิคหิต + สระอา, ช่องว่างแทนนิคหิต (Word), ฟอนต์ที่ map สระอาเป็น ำ (หนังสือราชการ)
แล้วตรวจว่าค้นด้วยคำที่พิมพ์ถูกต้องเจอ และหลังเซ็นเซอร์ข้อความหายจากไฟล์จริง
"""
import fitz
import pytest

from app.services.pdf_service import text_index


_FONT_CACHE = {}


def _font_path():
    """Sarabun + รหัส PUA (U+F700–F71D) แบบฟอนต์ไทยรุ่นเก่า (ชี้ไป glyph มาตรฐาน) — จำลองไฟล์ที่ใช้ PUA
    โดยไม่ต้องแนบฟอนต์ที่มี PUA (เดิมใช้ TH Sarabun New ซึ่งไม่ได้แนบมากับระบบแล้ว)"""
    if "path" not in _FONT_CACHE:
        import tempfile
        from pathlib import Path

        from fontTools.ttLib import TTFont

        from app.services.thai_text import PUA_MAP

        src = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf"
        import copy

        font = TTFont(str(src))
        cmap = font.getBestCmap()
        glyf, hmtx = font["glyf"], font["hmtx"]
        added = {}
        for pua, ch in PUA_MAP.items():  # glyph ของ PUA เป็นสำเนาแยก (ToUnicode ของ PDF จึงยังเป็นรหัส PUA)
            if ord(ch) in cmap:
                name = f"pua{pua:04X}"
                glyf[name] = copy.deepcopy(glyf[cmap[ord(ch)]])
                hmtx[name] = hmtx[cmap[ord(ch)]]
                added[pua] = name
        font.setGlyphOrder(list(glyf.glyphOrder))  # glyf[name] = ... ต่อท้ายลำดับ glyph ให้แล้ว
        font["maxp"].numGlyphs = len(glyf.glyphOrder)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap.update(added)
        out = Path(tempfile.mkdtemp()) / "Sarabun-PUA.ttf"
        font.save(str(out))
        _FONT_CACHE["path"] = str(out)
    return _FONT_CACHE["path"]


LINES = [
    "บริษัท ตัวอย่าง จ ากัด ส าหรับลูกค้า",                       # Word/TH SarabunPSK: นิคหิตเป็นช่องว่าง
    "งานซํ้า ๆ และการทํางานประจําวัน",                             # Google Docs/Noto: ํ + า
    "ข\uf70aาว ป\uf701\uf70bนโต",                                 # PUA ฟอนต์รุ่นเก่า (ข่าว ปิ้นโต)
    "ส ำนักงำนประกันสังคม ขอรับรองว่ำ ถนนติวำนนท์ มีสถำนะเป็นผู้ประกันตน",  # map สระอาเป็น ำ
    "เลขที่สัญญา AB-12",
    "34 ต่อท้ายบรรทัด",
]


def _pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    font = _font_path()
    for i, line in enumerate(LINES):
        page.insert_text((50, 80 + i * 30), line, fontsize=16, fontname="thsarabun", fontfile=font)
    return doc.tobytes()


@pytest.fixture
def page():
    doc = fitz.open(stream=_pdf_bytes(), filetype="pdf")
    yield doc[0]
    doc.close()


@pytest.mark.parametrize("keyword", [
    "จำกัด", "สำหรับลูกค้า", "งานซ้ำ", "การทำงานประจำวัน", "ข่าว", "ปิ้นโต",
    "สำนักงานประกันสังคม", "ถนนติวานนท์", "บริษัทตัวอย่าง",
])
def test_finds_thai_words_typed_correctly(page, keyword):
    assert not page.search_for(keyword)  # วิธีเดิม (เทียบข้อความดิบ) หาไม่เจอ
    pt = text_index.page_text(page)
    assert text_index.find(pt, text_index.keyword_pattern(keyword)), keyword


def test_regex_and_case(page):
    pt = text_index.page_text(page)
    assert text_index.find(pt, text_index.keyword_pattern(r"AB-12\s*34", is_regex=True))  # ข้ามบรรทัด
    assert text_index.find(pt, text_index.keyword_pattern("ab-12"))
    assert not text_index.find(pt, text_index.keyword_pattern("ab-12", match_case=True))
    with pytest.raises(ValueError):
        text_index.keyword_pattern("(", is_regex=True)
    with pytest.raises(ValueError):
        text_index.keyword_pattern("ก" * 400)


def test_redact_removes_text(client, make_user):
    _, headers = make_user()
    r = client.post("/pdf/upload", headers=headers, files={"file": ("thai.pdf", _pdf_bytes(), "application/pdf")})
    sid = r.json()["session_id"]
    r = client.post(f"/pdf/{sid}/redact-search", headers=headers, json={"keyword": "สำนักงานประกันสังคม"})
    assert r.status_code == 200 and r.json()["redacted_count"] == 1
    r = client.post(f"/pdf/{sid}/redact-search", headers=headers, json={"keyword": "การทำงาน"})
    assert r.json()["redacted_count"] == 1
    r = client.post(f"/pdf/{sid}/redact-search", headers=headers, json={"keyword": "ไม่มีคำนี้"})
    assert r.json()["redacted_count"] == 0 and r.json()["image_pages"] == []
    r = client.post(f"/pdf/{sid}/redact-search", headers=headers, json={"keyword": "(", "is_regex": True})
    assert r.status_code == 400

    from app.core.session import session_manager

    text = session_manager.get(sid).doc[0].get_text()
    assert "ประกันสังคม" not in text and "ส ำนักงำน" not in text
    assert "ทํางาน" not in text
    assert "บริษัท" in text  # ส่วนอื่นยังอยู่


def test_reports_pages_with_images():
    from types import SimpleNamespace

    from app.services.pdf_service import pages_with_images

    doc = fitz.open()
    doc.new_page()
    p2 = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 10), False)
    pix.clear_with(200)
    p2.insert_image(fitz.Rect(50, 400, 550, 520), pixmap=pix)  # ภาพลายเซ็น+ชื่อผู้ลงนาม
    session = SimpleNamespace(doc=doc, is_unlocked=True)
    assert pages_with_images(session) == [2]
