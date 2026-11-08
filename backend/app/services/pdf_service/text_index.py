"""ข้อความทั้งหน้า + กรอบของทุกอักขระ — ใช้ค้นหาแล้วได้ตำแหน่งจริงบนหน้า (PDPA, ค้นหาเพื่อเซ็นเซอร์)

ข้อความผ่านการจัดรูปภาษาไทยแล้ว (services/thai_text.py): PUA, สระอำแตก/หาย, ฟอนต์ที่ map สระอาเป็น ำ ฯลฯ
จึงค้นคำไทยที่พิมพ์ถูกต้องเจอ แม้ข้อความใน PDF จะถูกเก็บไว้ผิดรูป — ต่างจาก page.search_for ที่เทียบข้อความดิบ
(วัดกับไฟล์จริง: search_for เจอ 11/27 คำ — ดู scripts/thai_eval.py)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

from app.services import thai_text

MAX_KEYWORD_LENGTH = 300


@dataclass
class PageText:
    text: str
    boxes: list  # bbox ต่อตัวอักษร (None = ตัวคั่นที่เราเติมเอง: ช่องว่างเสมือน/ขึ้นบรรทัด)
    lines: list  # หมายเลขบรรทัดของแต่ละตัวอักษร


def content_page(page: fitz.Page) -> fitz.Page:
    """หน้าเดียวกันแต่ไม่มี annotation/ช่องฟอร์ม — อ่านเฉพาะ "เนื้อหน้า"

    PyMuPDF ดึงข้อความรวมภาพของ annotation ด้วย (ค่าในช่องฟอร์ม กล่องข้อความ กรอบที่มีข้อความ) — ถ้าไม่แยก
    การค้นหาเพื่อเซ็นเซอร์/PDPA จะปิดทับเนื้อหน้าที่ตำแหน่งกล่องนั้นแต่ตัวกล่องยังแสดงข้อความเดิม และการแก้ไข
    ข้อความจะเห็นข้อความในกล่องเป็นย่อหน้าของหน้า (ส่วนนั้นจัดการแยกที่ scrub_hidden_text / PDPA _object_findings)"""
    if page.first_annot is None and page.first_widget is None:
        return page
    tmp = fitz.open()
    tmp.insert_pdf(page.parent, from_page=page.number, to_page=page.number, annots=False)
    q = tmp[0]
    q._ja_src_doc = tmp  # ให้เอกสารชั่วคราวอยู่ตราบที่ยังใช้หน้านี้
    return q


def page_text(page: fitz.Page) -> PageText:
    chars, boxes, lines = [], [], []
    line_no = 0
    page = content_page(page)
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES)
    thai_text.normalize_page_dict(raw, page)
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            prev_x1 = None
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    if not ch["c"]:  # ถูกรวมกับตัวข้างเคียงตอนจัดรูป
                        continue
                    x0 = ch["bbox"][0]
                    # PDF บางไฟล์วางคำห่างกันโดยไม่มีอักขระช่องว่าง — เติมช่องว่างเสมือนเมื่อมีระยะห่างชัดเจน
                    if prev_x1 is not None and x0 - prev_x1 > span["size"] * 0.25 and chars and chars[-1] != " ":
                        chars.append(" ")
                        boxes.append(None)
                        lines.append(line_no)
                    chars.append(ch["c"])
                    boxes.append(ch["bbox"])
                    lines.append(line_no)
                    prev_x1 = ch["bbox"][2]
            chars.append("\n")
            boxes.append(None)
            lines.append(line_no)
            line_no += 1
    return PageText("".join(chars), boxes, lines)


def rects_for(pt: PageText, start: int, end: int) -> list[fitz.Rect]:
    """รวมกรอบตัวอักษรช่วง [start, end) แยกตามบรรทัด"""
    by_line: dict[int, fitz.Rect] = {}
    for i in range(start, end):
        box = pt.boxes[i]
        if box is None or not pt.text[i].strip():
            continue
        r = fitz.Rect(box)
        if r.is_empty:  # สระ/วรรณยุกต์บางฟอนต์กว้าง 0
            r = fitz.Rect(r.x0, r.y0, r.x0 + 0.5, r.y1)
        ln = pt.lines[i]
        by_line[ln] = by_line[ln] | r if ln in by_line else r
    return [r + (-0.5, -0.5, 0.5, 0.5) for r in by_line.values()]


def keyword_pattern(keyword: str, match_case: bool = False, is_regex: bool = False) -> re.Pattern:
    """คำค้น → regex บนข้อความที่จัดรูปแล้ว

    คำธรรมดา: จัดรูปไทยแล้วยอมให้มีช่องว่าง/ขึ้นบรรทัดคั่นระหว่างอักขระได้ (PDF มักแทรกช่องว่างเสมือน
    หรือคำไทยถูกตัดข้ามบรรทัด) และช่องว่างในคำค้นจะมีหรือไม่มีในเอกสารก็ได้
    regex: ใช้ตามที่ผู้ใช้พิมพ์ (ค้นบนข้อความทั้งหน้า ข้ามบรรทัดได้ด้วย \\s)
    """
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise ValueError(f"คำค้นยาวเกิน {MAX_KEYWORD_LENGTH} ตัวอักษร")
    flags = 0 if match_case else re.IGNORECASE
    if is_regex:
        try:
            pattern = re.compile(keyword, flags)
        except re.error as exc:
            raise ValueError(f"รูปแบบ Regular Expression ไม่ถูกต้อง: {exc}") from None
        if _nested_repeat(keyword):
            raise ValueError("รูปแบบ Regex มีตัวซ้ำซ้อนกัน เช่น (a+)+ ซึ่งอาจทำให้ค้นหานานมากจนค้าง — กรุณาเขียนให้ง่ายขึ้น")
        return pattern
    chars = [c for c in thai_text.normalize(keyword) if not c.isspace()]
    if not chars:
        raise ValueError("คำค้นว่าง")
    return re.compile(r"\s*".join(re.escape(c) for c in chars), flags)


def _nested_repeat(regex: str) -> bool:
    """มีตัวซ้ำไม่จำกัดซ้อนในตัวซ้ำไม่จำกัดอีกชั้น ("(a+)+", "(\\w*\\s?)*") หรือไม่ — รูปแบบแบบนี้ทำให้ re
    ย้อนรอยแบบเลขชี้กำลัง (ReDoS) บนข้อความที่เกือบตรง เช่นเส้นประยาวๆ ในเอกสาร ค้างทั้ง worker ได้"""
    try:
        import re._parser as sre_parse  # Python 3.11+
    except ImportError:  # pragma: no cover
        import sre_parse  # type: ignore
    try:
        tree = sre_parse.parse(regex)
    except Exception:
        return False
    repeats = {sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT}
    if hasattr(sre_parse, "POSSESSIVE_REPEAT"):
        repeats.add(sre_parse.POSSESSIVE_REPEAT)

    def walk(items, inside: bool) -> bool:
        for op, av in items:
            if op in repeats:
                lo, hi, sub = av
                unbounded = hi == sre_parse.MAXREPEAT or hi > 50
                if unbounded and inside:
                    return True
                if walk(sub, inside or unbounded):
                    return True
            elif op == sre_parse.SUBPATTERN:
                if walk(av[-1], inside):
                    return True
            elif op == sre_parse.BRANCH:
                if any(walk(b, inside) for b in av[1]):
                    return True
            elif op in (sre_parse.ASSERT, sre_parse.ASSERT_NOT):
                if walk(av[1], inside):
                    return True
        return False

    return walk(tree, False)


def find(pt: PageText, pattern: re.Pattern) -> list[tuple[int, int]]:
    """ช่วง [start, end) ที่ตรงกับ pattern (ไม่นับผลว่าง/ผลที่มีแต่ช่องว่าง)"""
    return [(m.start(), m.end()) for m in pattern.finditer(pt.text)
            if m.end() > m.start() and pt.text[m.start():m.end()].strip()]
