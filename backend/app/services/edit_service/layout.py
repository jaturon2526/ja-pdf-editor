"""ตัวช่วยจัดวางข้อความที่ใช้ร่วมกัน: ตัดคำไทย วัด/ตัดบรรทัด สุ่มสีพื้นหลัง และค่าคงที่ (เหตุผล/ประวัติบั๊ก ดู NOTES.md)"""
from __future__ import annotations

import functools
import threading

import fitz  # PyMuPDF
from fpdf import FPDF


from app.services import thai_text

# เผื่อ redact แล้ววาดใหม่ทับพอดีเป๊ะจนดูอึดอัด ขยับกรอบวาดจริงเข้ามาเล็กน้อย (point)
_TEXT_INSET = 1.0
_LINE_HEIGHT_RATIO = 1.35  # ระยะห่างบรรทัดสำหรับข้อความไทย (สระ/วรรณยุกต์ซ้อนบน-ล่างต้องการที่มากกว่าอังกฤษเปล่าๆ)

# เส้นขีดใต้ข้อความ (ผู้ใช้แจ้งขอเพิ่ม — ปุ่ม Underline ในหน้าจอแก้ไขข้อความ) ไม่ใช่ font variant (ไม่ต้อง
# มีไฟล์ฟอนต์แยก ใช้ได้กับทุกฟอนต์/ทุกสไตล์) วาดเป็นเส้นตรงเพิ่มต่างหากใต้ baseline ของแต่ละบรรทัด —
# ระยะห่างจาก baseline และความหนาเส้นคำนวณเป็นสัดส่วนกับ fontsize เหมือน metric อื่นๆ ในไฟล์นี้
_UNDERLINE_OFFSET_RATIO = 0.14  # ระยะจาก baseline ลงมาถึงเส้นขีดใต้ = fontsize * ratio นี้
_UNDERLINE_WIDTH_RATIO = 0.06   # ความหนาเส้น = fontsize * ratio นี้ (มีขั้นต่ำกันเส้นบางเกินไปตอน fontsize เล็ก)
_UNDERLINE_MIN_WIDTH_PT = 0.6

# เอกสารแบบฟอร์ม/ใบแจ้งหนี้: รวมบรรทัดเป็นย่อหน้าเดียวกันเฉพาะเมื่อบรรทัดก่อนหน้า "กว้าง" อย่างน้อย
# สัดส่วนนี้ของบรรทัดที่กว้างที่สุดใน block เดียวกัน (ดูหมายเหตุ "แก้บั๊กสำคัญ #3" ด้านบน)
_PARAGRAPH_WRAP_RATIO = 0.7

# ทะเบียนย่อหน้าที่เคยแก้ไข (session.text_edits) ใช้ prefix นี้กับ block_id เสมอ กันชนกับ block_id
# แบบ "<block>-<กลุ่ม>" ที่มาจาก PyMuPDF ตรงๆ (ดูหมายเหตุ "แก้บั๊กสำคัญ #6" ด้านบนของไฟล์)
_TRACKED_EDIT_PREFIX = "edit-"

# ตอนย้าย/ปรับขนาดรูปภาพ (reposition_image) ต้องขยายกรอบเดิมออกมาก่อนสุ่มสีพื้นหลัง กันสุ่มโดนสีของ
# ตัวรูปเอง แทนที่จะเป็นพื้นหลังจริงเบื้องหลังรูป (ดูหมายเหตุ "แก้บั๊กสำคัญ #7" ที่ reposition_image)
_BG_SAMPLE_MARGIN_PT = 6.0

# เผื่อ tolerance เล็กน้อยตอนเช็คว่า bbox รูปภาพที่แทรกเอง (จากการแก้ไขข้อความ) อยู่ "ภายใน" กรอบที่
# ทะเบียน session.text_edits เก็บไว้หรือเปล่า (ดู _rect_contains / หมายเหตุ "แก้บั๊กสำคัญ #9" ด้านบน
# ของไฟล์) กัน floating point/การปัดเศษระหว่างตอนวาดรูปกับตอนอ่าน bbox กลับมาไม่ตรงกันเป๊ะๆ
_TEXT_EDIT_IMAGE_TOLERANCE_PT = 1.5


def _tokenize(paragraph: str) -> list[str]:
    """ตัดคำหนึ่งบรรทัด/ย่อหน้าย่อย (newmm + คำเสริมใน app/assets/thai_custom_words.txt) เก็บช่องว่างไว้ด้วย"""
    return thai_text.tokenize(paragraph, keep_whitespace=True)


# ขึ้นบรรทัดใหม่ "ก่อน" ตัวเหล่านี้ไม่ได้ (ไม้ยมก ไปยาลน้อย วงเล็บปิด เครื่องหมายวรรคตอน) และ "หลัง" วงเล็บเปิดไม่ได้
_NO_LINE_START = set("\u0E46\u0E2F)]}\u201d\u2019\u00bb,.:;!?%")
_NO_LINE_END = set("([{\u201c\u2018\u00ab")


def _no_line_start(tok: str) -> bool:
    """ขึ้นบรรทัดใหม่หน้า token นี้ไม่ได้: ๆ ฯ (ตัวเดี่ยว — ไม่ใช่ ฯลฯ) และวงเล็บปิด/เครื่องหมายวรรคตอน"""
    return tok in ("\u0E46", "\u0E2F") or (tok[:1] in _NO_LINE_START and not thai_text.is_thai(tok[:1]))


def _break_units(paragraph: str) -> list[str]:
    """รวม token เป็นหน่วยที่ห้ามแยกบรรทัดกลาง: "มาก ๆ", "ไทย)", "(ไทย", ช่องว่างติดไปกับคำก่อนหน้า"""
    units: list[str] = []
    pending = ""  # วงเล็บเปิด/อัญประกาศเปิดที่ต้องติดไปกับคำถัดไป
    tokens = _tokenize(paragraph)
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok.isspace():
            if units and nxt and _no_line_start(nxt):  # "มาก" " " "ๆ" → "มาก ๆ"
                units[-1] += tok + nxt
                i += 2
                continue
            if units:
                units[-1] += tok
            else:
                units.append(tok)
            i += 1
            continue
        if tok[-1:] in _NO_LINE_END and not tok.strip("".join(_NO_LINE_END)):
            pending += tok
            i += 1
            continue
        if units and (_no_line_start(tok) or tok[:1] in thai_text.MARKS) and not pending:
            units[-1] += tok
        else:
            units.append(pending + tok)
            pending = ""
        i += 1
    if pending:
        units.append(pending)
    return units


_fpdf_cache: dict[str, FPDF] = {}
_measure_lock = threading.Lock()  # FPDF ไม่ thread-safe — หลาย session อาจวัดฟอนต์เดียวกันพร้อมกัน


def _get_fpdf_for_font(font_path: str) -> FPDF:
    """FPDF ต่อไฟล์ฟอนต์ไว้วัดความกว้าง (เปิด text shaping เหมือนตอนวาดจริงใน text.py) — เรียกภายใต้ _measure_lock"""
    if font_path not in _fpdf_cache:
        pdf = FPDF(unit="pt")
        pdf.add_page()
        pdf.add_font("Custom", "", font_path)
        pdf.set_font("Custom", size=12)
        try:
            pdf.set_text_shaping(True, script="thai", language="tha")
        except Exception:  # pragma: no cover — ไม่มี uharfbuzz ก็วัดแบบไม่ shape
            pass
        _fpdf_cache[font_path] = pdf
    return _fpdf_cache[font_path]


@functools.lru_cache(maxsize=20000)
def _measure_width(text: str, font_path: str, fontsize: float) -> float:
    """วัดความกว้างข้อความ (หน่วย point) ด้วย fpdf2 แบบ shaping เดียวกับตอนวาด"""
    if not text:
        return 0.0
    with _measure_lock:
        pdf = _get_fpdf_for_font(font_path)
        pdf.set_font("Custom", size=fontsize)
        return pdf.get_string_width(text)


@functools.lru_cache(maxsize=1)
def _syllable_trie():
    from pythainlp.tokenize import syllable_dict_trie

    return syllable_dict_trie() if callable(syllable_dict_trie) else syllable_dict_trie


def _split_points(unit: str) -> list[str]:
    """ชิ้นย่อยของหน่วยที่ยาวเกินบรรทัด: คำไทยแยกเป็นพยางค์ (เทค|โน|โล|ยี) ส่วนอื่นแยกเป็นกลุ่มอักษร (TCC)"""
    try:
        from pythainlp.tokenize import tcc, word_tokenize

        out: list[str] = []
        for part in word_tokenize(unit, custom_dict=_syllable_trie(), engine="newmm", keep_whitespace=True):
            out.extend([part] if thai_text.has_thai(part) and len(part) <= 8 else tcc.segment(part))
        return out
    except Exception:  # pragma: no cover — ไม่มี pythainlp
        return list(unit)


def _split_long_unit(unit: str, font_path: str, fontsize: float, max_width: float) -> list[str]:
    """หน่วยที่กว้างเกินบรรทัด (คำประสมยาว, URL) → ตัดที่ขอบพยางค์/กลุ่มอักษร ไม่ให้สระ/วรรณยุกต์แยกจากพยัญชนะ"""
    pieces: list[str] = []
    current = ""
    for c in _split_points(unit):
        if current and _measure_width(current + c, font_path, fontsize) > max_width:
            pieces.append(current)
            current = c
        else:
            current += c
    if current:
        pieces.append(current)
    return pieces


def _wrap_text(text: str, font_path: str, fontsize: float, max_width: float) -> list[str]:
    """ตัดบรรทัดแบบ greedy ที่ขอบคำ ให้แต่ละบรรทัดกว้างไม่เกิน max_width (point)

    - ผู้ใช้กด Enter = ขึ้นบรรทัด/ย่อหน้าใหม่เสมอ · ย่อหน้าเว้นวรรคต้นบรรทัดแรกไว้ (เยื้อง) บรรทัดต่อไปตัดช่องว่างหน้า
    - ไม่ขึ้นบรรทัดใหม่ก่อน ๆ ฯ วงเล็บปิด/เครื่องหมายวรรคตอน และไม่ทิ้งวงเล็บเปิดไว้ท้ายบรรทัด
    - คำที่ยาวกว่าบรรทัดตัดที่ขอบพยางค์ (ไม่ล้นกล่อง)
    """
    def width(s: str) -> float:
        return _measure_width(s.rstrip(), font_path, fontsize)

    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        para_lines: list[str] = []
        current = ""
        for unit in _break_units(paragraph):
            if current and width(current + unit) <= max_width:
                current += unit
                continue
            if current.strip():
                para_lines.append(current)
            current = unit if not para_lines else unit.lstrip()
            if width(current) > max_width:
                *full, current = _split_long_unit(current, font_path, fontsize, max_width)
                para_lines.extend(full)
        if current.strip() or not para_lines:
            para_lines.append(current)
        lines.extend([para_lines[0].rstrip()] + [ln.strip() for ln in para_lines[1:]])
    return lines

def _rgb01_to_int(rgb: tuple[float, float, float]) -> int:
    """แปลงสี RGB 0-1 (ที่ใช้วาดจริง) กลับเป็น sRGB int แบบเดียวกับที่ PyMuPDF คืนมาใน span["color"]
    ใช้ตอนสร้าง TextBlock ปลอมๆ จากทะเบียน session.text_edits (ดูหมายเหตุ "แก้บั๊กสำคัญ #6") ให้
    หน้าตาเหมือน TextBlock ที่มาจากข้อความดิบใน PDF จริงๆ — frontend จะได้แปลงกลับเป็น hex ได้แบบเดียวกัน
    """
    r, g, b = rgb
    r_i = max(0, min(255, round(r * 255)))
    g_i = max(0, min(255, round(g * 255)))
    b_i = max(0, min(255, round(b * 255)))
    return (r_i << 16) | (g_i << 8) | b_i

def _sample_background_color(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float]:
    """เดาสีพื้นหลังบริเวณกล่องข้อความ (ก่อน redact) จากสีที่มุมทั้ง 4 ของกล่อง แทนการ fill ขาวเสมอ
    (ดูหมายเหตุ "แก้บั๊กสำคัญ #4" ด้านบนของไฟล์ — กันปื้นขาวโผล่ทับพื้นหลังสีของ field ในฟอร์ม/ใบแจ้งหนี้)
    หาสีไม่ได้ด้วยเหตุผลใดๆ (กล่องเล็กเกินไป, error) fallback เป็นขาวเหมือนพฤติกรรมเดิม
    """
    try:
        clip = fitz.Rect(rect)
        if clip.width < 1 or clip.height < 1:
            return (1.0, 1.0, 1.0)
        pix = page.get_pixmap(clip=clip, matrix=fitz.Matrix(1, 1), colorspace=fitz.csRGB, alpha=False)
        w, h = pix.width, pix.height
        if w < 1 or h < 1:
            return (1.0, 1.0, 1.0)
        # ใช้สีที่พบบ่อยที่สุดตามขอบกล่องทั้ง 4 ด้าน (เดิมดูแค่ 4 มุม — มุมเดียวที่เลยขอบแถบสีก็ทำให้เดาผิด)
        border = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
        border += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
        samples = [pix.pixel(x, y) for x, y in border]
        most_common = max(set(samples), key=samples.count)
        return tuple(c / 255.0 for c in most_common)
    except Exception:
        return (1.0, 1.0, 1.0)
