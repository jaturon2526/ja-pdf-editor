"""ตัดคำ/ขึ้นบรรทัดภาษาไทย (เฟส 4): edit_service.layout._wrap_text, thai_text.tokenize/with_break_opportunities"""
import threading
from pathlib import Path

import fitz
import pytest

from app.services import thai_text
from app.services.edit_service.layout import _break_units, _measure_width, _wrap_text

FONT = str(Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")
TEXT = ("    ข้อเสนอแนะมาตรฐานด้านเทคโนโลยีสารสนเทศและการสื่อสารที่จำเป็นต่อธุรกรรมทางอิเล็กทรอนิกส์ มาก ๆ "
        "(ฉบับปรับปรุง) https://example.com/a/very/long/path/that/does/not/fit\nบรรทัดใหม่")


@pytest.mark.parametrize("width", [40, 60, 100, 160, 400])
def test_lines_never_exceed_width_and_keep_all_text(width):
    lines = _wrap_text(TEXT, FONT, 12, width)
    assert all(_measure_width(ln, FONT, 12) <= width + 0.01 for ln in lines), lines
    assert "".join(lines).replace(" ", "") == TEXT.replace("\n", "").replace(" ", "")


def test_breaks_at_word_boundaries():
    words = set(thai_text.tokenize(TEXT.split("\n")[0], keep_whitespace=False))
    for ln in _wrap_text(TEXT, FONT, 12, 160)[:-1]:
        last = thai_text.tokenize(ln.strip(), keep_whitespace=False)[-1]
        assert last in words or not thai_text.has_thai(last) or last in ("ๆ", ")"), (ln, last)


def test_no_line_starts_with_mai_yamok_or_closing_paren():
    for width in (50, 70, 90, 120):
        for ln in _wrap_text("ดีมาก ๆ เลย (ภาษาไทย) ทดสอบ ฯลฯ", FONT, 12, width):
            assert not ln.startswith(("ๆ", ")")) and not ln.endswith("("), ln


def test_units():
    assert _break_units("มาก ๆ (ไทย) ราคา 100%, ฯลฯ") == ["มาก ๆ ", "(ไทย) ", "ราคา ", "100%, ", "ฯลฯ"]


def test_indent_kept_on_first_line_only_and_newlines_respected():
    lines = _wrap_text("    ย่อหน้าแรกที่ยาวพอจะขึ้นบรรทัดใหม่แน่นอน\n\nย่อหน้าสอง", FONT, 12, 120)
    assert lines[0].startswith("    ") and not lines[1].startswith(" ")
    assert "" in lines and lines[-1] == "ย่อหน้าสอง"


def test_english_still_wraps_at_spaces():
    assert _wrap_text("Hello World", FONT, 12, 500) == ["Hello World"]
    assert _wrap_text("Hello World", FONT, 12, 40) == ["Hello", "World"]


def test_measuring_is_thread_safe():
    _measure_width.cache_clear()
    results, errors = [], []

    def work(size):
        try:
            results.append((size, _wrap_text(TEXT, FONT, size, 150)))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(s,)) for s in (10, 12, 14, 16) * 5]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    by_size = {}
    for size, lines in results:
        by_size.setdefault(size, lines)
        assert by_size[size] == lines


def test_custom_words_and_break_opportunities():
    assert "สพธอ" in thai_text.tokenize("สพธอ.ออกข้อเสนอแนะ")
    z = thai_text.with_break_opportunities("หนังสือฉบับนี้ ABC 123 มาก ๆ")
    assert z.replace("​", "") == "หนังสือฉบับนี้ ABC 123 มาก ๆ"
    assert z.count("​") == 2  # หนังสือ|ฉบับ|นี้ เท่านั้น — ไม่แทรกระหว่างอังกฤษ/ตัวเลข/ก่อน ๆ


def test_text_written_by_fpdf2_extracts_cleanly():
    """fpdf2 (shaping) ใส่ \\x03 \\x06 ต่อท้าย ำ ใน ToUnicode — ข้อความที่แอปเขียนเองต้องค้น/คัดลอกได้"""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("S", "", FONT)
    pdf.set_font("S", size=14)
    pdf.set_text_shaping(True, script="thai", language="tha")
    pdf.cell(0, 10, "คำขอ น้ำท่วม กำลังใจ")
    page = fitz.open(stream=bytes(pdf.output()))[0]
    raw = thai_text.normalize_page_dict(page.get_text("dict"), page)
    text = "".join(s["text"] for b in raw["blocks"] for ln in b["lines"] for s in ln["spans"])
    assert text.strip() == "คำขอ น้ำท่วม กำลังใจ"


def test_edit_text_wraps_thai_at_word_boundaries(client, make_user, upload):
    from app.core.session import session_manager

    _, headers = make_user()
    sid = upload(headers)
    r = client.get(f"/edit/{sid}/page/0/text-blocks", headers=headers)
    block = r.json()[0] if isinstance(r.json(), list) else r.json()["blocks"][0]
    new_text = "การแก้ไขข้อความภาษาไทยต้องขึ้นบรรทัดใหม่ตรงขอบคำเสมอ ไม่ตัดกลางคำ และคำขอต้องค้นหาได้"
    body = {"page_number": 0, "block_id": block["block_id"], "new_text": new_text,
            "rect": block["rect"] if "rect" in block else block["bbox"], "fontname": "sarabun", "fontsize": 12}
    r = client.post(f"/edit/{sid}/text", headers=headers, json=body)
    assert r.status_code == 200, r.text
    page = session_manager.get(sid).doc[0]
    raw = thai_text.normalize_page_dict(page.get_text("dict"), page)
    lines = ["".join(s["text"] for s in ln["spans"]).strip() for b in raw["blocks"] for ln in b["lines"]]
    assert "".join(lines).replace(" ", "") .find(new_text.replace(" ", "")) >= 0, lines
    words = set(thai_text.tokenize(new_text, keep_whitespace=False))
    for ln in lines:
        if ln and thai_text.has_thai(ln) and ln != lines[-1]:
            assert thai_text.tokenize(ln, keep_whitespace=False)[-1] in words, (ln, lines)
