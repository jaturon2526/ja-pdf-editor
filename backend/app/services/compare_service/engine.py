"""เทียบ PDF 2 ไฟล์ — ข้อความ (คำที่เพิ่ม/ลบ/แก้ พร้อมตำแหน่ง) + ภาพ (จุดที่ภาพต่างกันนอกเหนือจากข้อความ)

ขั้นตอน (ดู claude/phase-compare-pdf-plan.md):
1. ดึงคำพร้อมกรอบทุกหน้า — ชั้นข้อความของ PDF (ตัดคำไทยด้วย thai_text.tokenize) · หน้าไม่มีข้อความ (สแกน) → OCR
2. เทียบลำดับคำทั้งเอกสารด้วย difflib → ช่วงเพิ่ม/ลบ/แก้ (ข้อความที่ไหลข้ามหน้าเพราะแทรกย่อหน้าไม่นับเป็นจุดต่าง)
3. จับคู่หน้า A↔B จากคำที่ตรงกัน (รองรับหน้าที่ถูกแทรก/ลบ) — หน้าที่ไม่มีข้อความจับคู่ตามลำดับในช่วงว่าง
4. เทียบภาพทีละคู่หน้า → กล่องจุดต่างที่ไม่ทับข้อความ (รูป ลายเซ็น เส้นตาราง ตราประทับ)

พิกัดทุกกล่องเป็นหน่วย point ของ "หน้าที่หมุนแล้ว" (ตรงกับภาพจาก /pdf/{sid}/page/{n}) — มุมบนซ้าย = (0, 0)
"""
from __future__ import annotations

import difflib
import logging
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional

import fitz
import numpy as np

from app.services import thai_text

logger = logging.getLogger("compare")

MAX_PAGES = 300
TOKEN_LIMIT_BLOCK = 30_000          # ช่วงบรรทัดที่ต่างกันมีคำรวมเกินนี้ → ไม่เทียบระดับคำ (difflib ช้าแบบกำลังสอง)
VISUAL_DPI = 100
VISUAL_THRESHOLD = 24               # ต่างกันเกินค่านี้ (0–255) ต่อพิกเซลถึงนับว่าต่าง — ต่ำพอให้เห็นลายเซ็นสีอ่อนเส้นบาง
VISUAL_MIN_AREA_PT = 12             # กล่องเล็กกว่านี้ (ตร.pt) ไม่นับ — กันจุดรบกวน/ขอบตัวอักษร
VISUAL_MERGE_PT = 12                # กล่องที่ห่างกันไม่เกินนี้รวมเป็นจุดเดียว (ลายเซ็น + กรอบ + ข้อความใต้ลายเซ็น)
SHIFT_TOLERANCE_PT = 3.0            # คำที่ตรงกันแต่ตำแหน่งเลื่อนเกินนี้ = เนื้อหาในหน้าเลื่อน → ไม่เทียบภาพหน้านั้น
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


class CompareError(Exception):
    pass


@dataclass
class Options:
    text: bool = True
    visual: bool = True
    ocr: bool = True                 # อ่านหน้าที่ไม่มีชั้นข้อความด้วย OCR
    ignore_case: bool = False
    ignore_digits_style: bool = True  # ๑๒๓ = 123
    ignore_punctuation: bool = False


@dataclass
class Token:
    text: str            # ข้อความจริง (แสดงผล)
    key: str             # ข้อความที่ใช้เทียบ (normalize แล้ว)
    page: int
    rect: tuple[float, float, float, float]   # พิกัดหน้าที่หมุนแล้ว
    line: int            # ลำดับบรรทัดทั้งเอกสาร (รวมคำบรรทัดเดียวกันเป็นกล่องเดียว)


@dataclass
class DocText:
    tokens: list[Token] = field(default_factory=list)
    page_sizes: list[tuple[float, float]] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    empty_pages: list[int] = field(default_factory=list)   # ไม่มีข้อความเลย (และไม่ได้/อ่าน OCR ไม่ได้)


# ------------------------------------------------------------------ 1. ดึงคำ

def _key(text: str, opts: Options) -> str:
    s = unicodedata.normalize("NFC", thai_text.normalize(text))
    if opts.ignore_digits_style:
        s = s.translate(_THAI_DIGITS)
    if opts.ignore_case:
        s = s.casefold()
    if opts.ignore_punctuation:
        s = "".join(c for c in s if not unicodedata.category(c).startswith("P"))
    return s


def _transform(rect: fitz.Rect, page: fitz.Page) -> tuple[float, float, float, float]:
    r = fitz.Rect(rect) * page.rotation_matrix if page.rotation else fitz.Rect(rect)
    r.normalize()
    return (round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2))


def _line_tokens(chars: list[tuple[str, fitz.Rect]]) -> list[tuple[str, fitz.Rect]]:
    """ตัวอักษรของบรรทัด → คำ (ตัดคำไทย) พร้อมกรอบรวมของตัวอักษรในคำ"""
    text = "".join(c for c, _ in chars)
    out, i = [], 0
    for tok in thai_text.tokenize(text, keep_whitespace=True):
        j = i + len(tok)
        # เครื่องหมายวรรคตอนเป็นคำแยก — "(Tax Invoice)" กับ "(Tax Invoice )" ต้องเหมือนกัน (ต่างแค่ช่องว่าง)
        start = i

        def cut(k: int) -> bool:  # เครื่องหมายที่ k แยกเป็นคำเดี่ยว (ยกเว้นในตัวเลข 1,000.50 / 12:30)
            return _is_punct(chars[k][0]) and not (i < k < j - 1 and chars[k - 1][0].isdigit() and chars[k + 1][0].isdigit())

        for k in range(i, j + 1):
            boundary = k == j or chars[k][0].isspace() or cut(k) or (k > start and cut(k - 1))
            if boundary and k > start:
                seg = "".join(c for c, _ in chars[start:k]).strip()
                if seg:
                    rect = fitz.Rect(chars[start][1])
                    for _, r in chars[start + 1:k]:
                        rect |= r
                    out.append((seg, rect))
                start = k + 1 if k < j and chars[k][0].isspace() else k
        i = j
    return out


def _is_punct(c: str) -> bool:
    return unicodedata.category(c)[0] in "PS" and c not in "ฯๆ฿"


def _page_text_tokens(page: fitz.Page) -> list[tuple[str, fitz.Rect, int]]:
    """คำบนหน้า เรียงตาม "แถว" ที่เห็นบนกระดาษ (บนลงล่าง แล้วซ้ายไปขวา) ไม่ใช่ลำดับใน content stream

    ข้อความที่แก้ใน Editor ถูกเขียนเป็นบล็อกใหม่ต่อท้าย content stream (กรอบสูงกว่าบรรทัดเดิมเล็กน้อย) ส่วนสัญลักษณ์
    bullet ของบรรทัดเดิมยังอยู่ที่เดิม — ถ้าเรียงตามบล็อก bullet จะหลุดไปอยู่คนละที่กับข้อความ ทำให้เห็นเป็นลบทั้งบรรทัด
    แล้วเพิ่มทั้งบรรทัด · รวมทุกบรรทัดที่ซ้อนกันในแนวตั้งเป็นแถวเดียว แล้วเรียงในแถวตามแกน x"""
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_MEDIABOX_CLIP)
    lines: list[tuple[fitz.Rect, list]] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            # U+FFFD = glyph ที่ฟอนต์ไม่มี Unicode (เช่น สระอำบางฟอนต์) — ไม่ใช่ข้อความจริง ข้ามไป
            chars = [(ch["c"], fitz.Rect(ch["bbox"])) for span in line.get("spans", []) for ch in span.get("chars", [])
                     if ch["c"] != "\ufffd"]
            if any(not c.isspace() for c, _ in chars):
                lines.append((fitz.Rect(line["bbox"]), chars))
    lines.sort(key=lambda item: (item[0].y0 + item[0].y1) / 2)
    rows: list[list[tuple[fitz.Rect, list]]] = []
    row_box: fitz.Rect | None = None
    for box, chars in lines:
        if row_box is not None:
            overlap = min(box.y1, row_box.y1) - max(box.y0, row_box.y0)
            if overlap >= 0.5 * min(box.height, row_box.height):
                rows[-1].append((box, chars))
                row_box = fitz.Rect(row_box) | box
                continue
        rows.append([(box, chars)])
        row_box = fitz.Rect(box)
    out = []
    for row_no, row in enumerate(rows):
        for _, chars in sorted(row, key=lambda item: item[0].x0):
            for text, rect in _line_tokens(chars):
                out.append((text, rect, row_no))
    return out


def _page_ocr_tokens(page: fitz.Page) -> list[tuple[str, fitz.Rect, int]]:
    from app.services.pdf_service import ocr as pdf_ocr

    region = page.rect * page.derotation_matrix if page.rotation else page.rect   # พิกัดหน้าก่อนหมุน
    words = pdf_ocr._ocr_words_robust(page, fitz.Rect(region).normalize())
    out = []
    for rect, text, line in words:
        for sub_text, sub_rect in _split_ocr_word(text, fitz.Rect(rect)):
            out.append((sub_text, sub_rect, line))
    return out


def _split_ocr_word(text: str, rect: fitz.Rect) -> list[tuple[str, fitz.Rect]]:
    """คำจาก OCR ภาษาไทยมักเป็นวลียาว — ตัดคำซ้ำแล้วแบ่งกรอบตามสัดส่วนตัวอักษร"""
    parts = [t for t in thai_text.tokenize(text, keep_whitespace=False) if t.strip()]
    if len(parts) <= 1:
        return [(text, rect)]
    total = sum(len(p) for p in parts) or 1
    out, x = [], rect.x0
    for p in parts:
        w = rect.width * len(p) / total
        out.append((p, fitz.Rect(x, rect.y0, x + w, rect.y1)))
        x += w
    return out


def extract(doc: fitz.Document, opts: Options, progress: Optional[Callable[[float], None]] = None) -> DocText:
    result = DocText()
    line_base = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        result.page_sizes.append((round(page.rect.width, 2), round(page.rect.height, 2)))
        items = _page_text_tokens(page)
        if not items and opts.ocr and _looks_scanned(page):
            try:
                items = _page_ocr_tokens(page)
                if items:
                    result.ocr_pages.append(pno)
            except Exception as exc:  # noqa: BLE001 — OCR ล้ม (ไม่มี tesseract/คิวเต็ม) ยังเทียบภาพได้
                if exc.__class__.__name__ == "ServerBusyError":
                    raise
                logger.warning("OCR หน้า %s ไม่สำเร็จ: %s", pno + 1, exc)
        if not items:
            result.empty_pages.append(pno)
        max_line = -1
        for text, rect, line in items:
            key = _key(text, opts)
            if not key:
                continue
            result.tokens.append(Token(text, key, pno, _transform(rect, page), line_base + line))
            max_line = max(max_line, line)
        line_base += max_line + 1
        if progress:
            progress((pno + 1) / doc.page_count)
    return result


def _looks_scanned(page: fitz.Page) -> bool:
    """หน้าที่มีรูปใหญ่ (สแกน/ภาพถ่ายเอกสาร) — หน้าว่างจริงไม่ต้อง OCR"""
    area = abs(page.rect)
    for info in page.get_image_info():
        if abs(fitz.Rect(info["bbox"]) & page.rect) >= 0.3 * area:
            return True
    return False


# ------------------------------------------------------------------ 2. เทียบข้อความ

def _merge_rects(tokens: list[Token]) -> list[dict]:
    """คำติดกันบนบรรทัดเดียวกัน → กล่องเดียว"""
    out: list[dict] = []
    for t in tokens:
        if out and out[-1]["page"] == t.page and out[-1]["_line"] == t.line:
            r = out[-1]
            r["x0"], r["y0"] = min(r["x0"], t.rect[0]), min(r["y0"], t.rect[1])
            r["x1"], r["y1"] = max(r["x1"], t.rect[2]), max(r["y1"], t.rect[3])
        else:
            out.append({"page": t.page, "x0": t.rect[0], "y0": t.rect[1], "x1": t.rect[2], "y1": t.rect[3], "_line": t.line})
    for r in out:
        r.pop("_line")
    return out


def _caret(tokens: list[Token], index: int, line_start: bool = False) -> Optional[dict]:
    """ตำแหน่งแทรกในฝั่งที่ไม่มีคำ (ใช้ชี้ว่าข้อความถูกเพิ่ม/ลบตรงไหน) — ท้ายคำก่อนหน้า หรือต้นคำถัดไป
    line_start: ข้อความที่หายไป/เพิ่มมาเริ่มบรรทัดใหม่ → ชี้ต้นบรรทัดถัดไป (ไม่ใช่ท้ายบรรทัดก่อนหน้า ซึ่งดูเหมือนคำท้ายบรรทัดถูกแก้)"""
    if line_start and index < len(tokens):
        t = tokens[index]
        return {"page": t.page, "x0": t.rect[0] - 1, "y0": t.rect[1], "x1": t.rect[0], "y1": t.rect[3]}
    if index > 0 and tokens:
        t = tokens[min(index, len(tokens)) - 1]
        return {"page": t.page, "x0": t.rect[2], "y0": t.rect[1], "x1": t.rect[2] + 1, "y1": t.rect[3]}
    if tokens:
        t = tokens[0]
        return {"page": t.page, "x0": t.rect[0] - 1, "y0": t.rect[1], "x1": t.rect[0], "y1": t.rect[3]}
    return None


def _starts_line(tokens: list[Token], index: int) -> bool:
    return 0 < index < len(tokens) and tokens[index].line != tokens[index - 1].line


def _joined(tokens: list[Token]) -> str:
    out = ""
    for t in tokens:
        if out and (not thai_text.has_thai(out[-1]) or not thai_text.has_thai(t.text[0])):
            out += " "
        out += t.text
    return out[:500]


def _line_ranges(tokens: list[Token]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = 0
    for k in range(1, len(tokens) + 1):
        if k == len(tokens) or tokens[k].line != tokens[start].line:
            out.append((start, k))
            start = k
    return out


def _opcodes(a: list[Token], b: list[Token]) -> list[tuple[str, int, int, int, int]]:
    """เทียบ 2 ชั้น: บรรทัดก่อน (เร็ว แม้เอกสารหลายร้อยหน้า) แล้วเทียบระดับคำเฉพาะช่วงบรรทัดที่ต่างกัน
    — ย่อหน้าที่ตัดบรรทัดใหม่ (ข้อความไหล) เป็นช่วง "แทนที่" ระดับบรรทัด แต่ระดับคำจะเหลือเฉพาะคำที่ต่างจริง"""
    ka, kb = [t.key for t in a], [t.key for t in b]
    la, lb = _line_ranges(a), _line_ranges(b)
    line_keys_a = ["\u241f".join(ka[s:e]) for s, e in la]
    line_keys_b = ["\u241f".join(kb[s:e]) for s, e in lb]
    ops: list[tuple[str, int, int, int, int]] = []

    def add(tag, i1, i2, j1, j2):
        if i1 == i2 and j1 == j2:
            return
        if ops and ops[-1][0] == tag and ops[-1][2] == i1 and ops[-1][4] == j1:
            ops[-1] = (tag, ops[-1][1], i2, ops[-1][3], j2)
        else:
            ops.append((tag, i1, i2, j1, j2))

    def tok(i, j):  # ตำแหน่งคำของบรรทัดที่ i / j (ท้ายเอกสาร = จำนวนคำ)
        return (la[i][0] if i < len(la) else len(a)), (lb[j][0] if j < len(lb) else len(b))

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line_keys_a, line_keys_b, autojunk=False).get_opcodes():
        ta1, tb1 = tok(i1, j1)
        ta2, tb2 = tok(i2, j2)
        if tag in ("equal", "insert", "delete"):
            add(tag, ta1, ta2, tb1, tb2)
            continue
        if (ta2 - ta1) + (tb2 - tb1) > TOKEN_LIMIT_BLOCK:
            add("replace", ta1, ta2, tb1, tb2)   # ช่วงต่างใหญ่มาก — รายงานเป็นก้อนเดียว
            continue
        for t2, x1, x2, y1, y2 in difflib.SequenceMatcher(None, ka[ta1:ta2], kb[tb1:tb2], autojunk=False).get_opcodes():
            add(t2, x1 + ta1, x2 + ta1, y1 + tb1, y2 + tb1)
    return ops


def text_changes(a: DocText, b: DocText, ops) -> list[dict]:
    changes = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        ta, tb = a.tokens[i1:i2], b.tokens[j1:j2]
        if tag in ("delete", "insert"):
            # แยกตามหน้า — ส่วนที่อยู่บนหน้าที่ถูกลบ/เพิ่มทั้งหน้าจะถูกรวมเป็นจุดต่างระดับหน้า (compare_documents)
            side = ta if tag == "delete" else tb
            start = 0
            for k in range(1, len(side) + 1):
                if k == len(side) or side[k].page != side[start].page:
                    part = side[start:k]
                    anchor_a = None if tag == "delete" else _caret(a.tokens, i1, _starts_line(b.tokens, j1))
                    anchor_b = None if tag == "insert" else _caret(b.tokens, j1, _starts_line(a.tokens, i1))
                    changes.append({
                        "kind": tag, "a_text": _joined(part) if tag == "delete" else "",
                        "b_text": _joined(part) if tag == "insert" else "",
                        "a_rects": _merge_rects(part) if tag == "delete" else [],
                        "b_rects": _merge_rects(part) if tag == "insert" else [],
                        "a_anchor": anchor_a, "b_anchor": anchor_b,
                    })
                    start = k
            continue
        kind = "replace"
        changes.append({
            "kind": kind,
            "a_text": _joined(ta), "b_text": _joined(tb),
            "a_rects": _merge_rects(ta), "b_rects": _merge_rects(tb),
            "a_anchor": None if ta else _caret(a.tokens, i1, _starts_line(b.tokens, j1)),
            "b_anchor": None if tb else _caret(b.tokens, j1, _starts_line(a.tokens, i1)),
        })
    return changes


# ------------------------------------------------------------------ 3. จับคู่หน้า

def pair_pages(a: DocText, b: DocText, ops) -> list[tuple[Optional[int], Optional[int]]]:
    na, nb = len(a.page_sizes), len(b.page_sizes)
    w = np.zeros((na, nb), dtype=np.int64)
    for tag, i1, i2, j1, j2 in ops:
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            w[a.tokens[i1 + k].page, b.tokens[j1 + k].page] += 1
    # จัดแนวแบบเรียงลำดับ (ไม่สลับลำดับหน้า) ให้ผลรวมคำที่ตรงกันมากที่สุด
    score = np.zeros((na + 1, nb + 1), dtype=np.int64)
    for i in range(1, na + 1):
        for j in range(1, nb + 1):
            score[i, j] = max(score[i - 1, j], score[i, j - 1], score[i - 1, j - 1] + w[i - 1, j - 1])
    matched: list[tuple[int, int]] = []
    i, j = na, nb
    while i > 0 and j > 0:
        if w[i - 1, j - 1] > 0 and score[i, j] == score[i - 1, j - 1] + w[i - 1, j - 1]:
            matched.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif score[i - 1, j] >= score[i, j - 1]:
            i -= 1
        else:
            j -= 1
    matched.reverse()
    # ช่วงระหว่างคู่ที่จับได้: หน้าที่เหลือจับคู่ตามลำดับ (เช่น หน้ารูปภาพล้วน) ส่วนเกินเป็นหน้าเพิ่ม/ลบ
    pairs: list[tuple[Optional[int], Optional[int]]] = []
    pa = pb = 0
    for ma, mb in [*matched, (na, nb)]:
        gap_a, gap_b = list(range(pa, ma)), list(range(pb, mb))
        while gap_a and gap_b:
            # หน้าที่มีข้อความแต่ไม่ตรงกันเลยกับอีกฝั่ง ยังจับคู่ตามลำดับได้ (แก้ทั้งหน้า) — ข้อความไปแสดงเป็นจุดต่าง
            pairs.append((gap_a.pop(0), gap_b.pop(0)))
        pairs.extend((x, None) for x in gap_a)
        pairs.extend((None, y) for y in gap_b)
        if ma < na and mb < nb:
            pairs.append((ma, mb))
        pa, pb = ma + 1, mb + 1
    return pairs


# ------------------------------------------------------------------ 4. เทียบภาพ

def _render_gray(page: fitz.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False, annots=True)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _shifted(a: DocText, b: DocText, ops, pa: int, pb: int) -> bool:
    moved = total = 0
    for tag, i1, i2, j1, j2 in ops:
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            ta, tb = a.tokens[i1 + k], b.tokens[j1 + k]
            if ta.page == pa and tb.page == pb:
                total += 1
                if abs(ta.rect[0] - tb.rect[0]) > SHIFT_TOLERANCE_PT or abs(ta.rect[1] - tb.rect[1]) > SHIFT_TOLERANCE_PT:
                    moved += 1
    return total >= 5 and moved / total > 0.3


def visual_boxes(page_a: fitz.Page, page_b: fitz.Page, dpi: int = VISUAL_DPI) -> list[tuple[float, float, float, float]]:
    """กล่องที่ภาพสองหน้าต่างกัน (พิกัด pt ของหน้าที่หมุนแล้ว) — ต้องขนาดหน้าเท่ากัน"""
    import cv2

    ga, gb = _render_gray(page_a, dpi), _render_gray(page_b, dpi)
    h, w = min(ga.shape[0], gb.shape[0]), min(ga.shape[1], gb.shape[1])
    diff = cv2.absdiff(ga[:h, :w], gb[:h, :w])
    # ไม่ใช้ morphological opening — ลบเส้นบาง 1 px (ลายเซ็น เส้นกรอบ) ทิ้ง · เนื้อหาเดียวกันเรนเดอร์ตรงกันทุกพิกเซลอยู่แล้ว
    mask = (diff > VISUAL_THRESHOLD).astype(np.uint8)
    grow = max(3, int(VISUAL_MERGE_PT * dpi / 72) | 1)
    mask = cv2.dilate(mask, np.ones((grow, grow), np.uint8))                 # รวมจุดใกล้กันเป็นก้อน
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    k = 72.0 / dpi
    pad = grow // 2
    boxes = []
    for x, y, bw, bh, _area in stats[1:n]:
        # หดกลับเท่าที่ขยาย ให้กรอบพอดีจุดที่ต่างจริง
        x0, y0 = min(x + pad, x + bw / 2), min(y + pad, y + bh / 2)
        x1, y1 = max(x + bw - pad, x0 + 1), max(y + bh - pad, y0 + 1)
        rect = (round(x0 * k, 2), round(y0 * k, 2), round(x1 * k, 2), round(y1 * k, 2))
        if (rect[2] - rect[0]) * (rect[3] - rect[1]) >= VISUAL_MIN_AREA_PT or max(rect[2] - rect[0], rect[3] - rect[1]) >= 8:
            boxes.append(rect)
    return _merge_boxes(boxes, VISUAL_MERGE_PT)


def _merge_boxes(boxes: list[tuple], gap: float) -> list[tuple]:
    """รวมกล่องที่ซ้อน/ใกล้กัน (≤ gap pt) จนไม่มีคู่ไหนรวมได้อีก"""
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out: list[list] = []
        for b in boxes:
            for o in out:
                if b[0] <= o[2] + gap and o[0] <= b[2] + gap and b[1] <= o[3] + gap and o[1] <= b[3] + gap:
                    o[0], o[1], o[2], o[3] = min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3])
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return [tuple(b) for b in boxes]


def _page_images(page: fitz.Page) -> list[tuple[bytes, tuple]]:
    """รูปบนหน้า (ลายนิ้วมือของข้อมูลรูป, กรอบในพิกัดหน้าที่หมุนแล้ว) — ข้ามรูปเล็กมาก (ไอคอน/จุด)"""
    out = []
    try:
        infos = page.get_image_info(hashes=True)
    except Exception:  # noqa: BLE001
        return out
    for info in infos:
        r = fitz.Rect(info["bbox"]) & page.cropbox
        if r.is_empty or r.width < 4 or r.height < 4:
            continue
        out.append((info.get("digest") or b"", _transform(r, page)))
    return out


def image_changes(page_a: fitz.Page, page_b: fitz.Page) -> list[tuple[str, Optional[tuple], Optional[tuple]]]:
    """รูปที่เพิ่ม / ลบ / เปลี่ยน (เช่น ลายเซ็น ตราประทับ โลโก้) — เทียบจากข้อมูลรูปและตำแหน่ง ได้กรอบตรงตัวรูปพอดี"""
    ia, ib = _page_images(page_a), _page_images(page_b)
    same = lambda r, s: all(abs(r[i] - s[i]) <= 2 for i in range(4))  # noqa: E731
    used_a: set[int] = set()
    out = []
    for dig_b, rb in ib:
        hit = next((k for k, (d, ra) in enumerate(ia) if k not in used_a and d == dig_b and same(ra, rb)), None)
        if hit is not None:
            used_a.add(hit)
            continue
        swap = next((k for k, (d, ra) in enumerate(ia) if k not in used_a and same(ra, rb)), None)
        if swap is not None:
            used_a.add(swap)
            out.append(("replace", ia[swap][1], rb))
        else:
            out.append(("insert", None, rb))
    for k, (_, ra) in enumerate(ia):
        if k not in used_a:
            out.append(("delete", ra, None))
    return out


def _overlap_ratio(r: tuple, s: dict | tuple) -> float:
    sx0, sy0, sx1, sy1 = (s["x0"], s["y0"], s["x1"], s["y1"]) if isinstance(s, dict) else s
    ix = max(0.0, min(r[2], sx1) - max(r[0], sx0))
    iy = max(0.0, min(r[3], sy1) - max(r[1], sy0))
    area = max(1e-6, (r[2] - r[0]) * (r[3] - r[1]))
    return ix * iy / area


def _text_area(tokens: list[Token], page: int, box: tuple) -> float:
    covered = 0.0
    for t in tokens:
        if t.page == page:
            covered += _overlap_ratio(box, t.rect)
            if covered >= 0.5:
                break
    return covered


# ------------------------------------------------------------------ รวม

def compare_documents(doc_a: fitz.Document, doc_b: fitz.Document, opts: Optional[Options] = None,
                      progress: Optional[Callable[[int, str], None]] = None) -> dict:
    opts = opts or Options()
    if doc_a.page_count > MAX_PAGES or doc_b.page_count > MAX_PAGES:
        raise CompareError(f"เทียบได้ไม่เกิน {MAX_PAGES} หน้าต่อไฟล์")

    def report(pct: float, msg: str):
        if progress:
            progress(int(pct), msg)

    report(2, "กำลังอ่านข้อความไฟล์แรก")
    a = extract(doc_a, opts, lambda f: report(2 + 33 * f, "กำลังอ่านข้อความไฟล์แรก"))
    report(35, "กำลังอ่านข้อความไฟล์ที่สอง")
    b = extract(doc_b, opts, lambda f: report(35 + 33 * f, "กำลังอ่านข้อความไฟล์ที่สอง"))
    report(68, "กำลังเทียบข้อความ")
    ops = _opcodes(a.tokens, b.tokens)
    changes = text_changes(a, b, ops) if opts.text else []
    pairs = pair_pages(a, b, ops)

    notes: list[str] = []
    if opts.visual:
        both = [(x, y) for x, y in pairs if x is not None and y is not None]
        for idx, (pa, pb) in enumerate(both):
            report(72 + 25 * idx / max(1, len(both)), "กำลังเทียบภาพ")
            sa, sb = a.page_sizes[pa], b.page_sizes[pb]
            if abs(sa[0] - sb[0]) > 2 or abs(sa[1] - sb[1]) > 2:
                changes.append({"kind": "page_size", "a_text": f"{sa[0]:.0f}×{sa[1]:.0f} pt", "b_text": f"{sb[0]:.0f}×{sb[1]:.0f} pt",
                                "a_rects": [_full(pa, sa)], "b_rects": [_full(pb, sb)], "a_anchor": None, "b_anchor": None})
                continue
            if pa in a.ocr_pages and pb in b.ocr_pages:
                continue  # สแกนคนละครั้ง ภาพต่างทั้งหน้าเสมอ — เทียบจากข้อความ OCR แทน
            if _shifted(a, b, ops, pa, pb):
                notes.append(f"หน้า {pa + 1}/{pb + 1}: เนื้อหาเลื่อนตำแหน่ง (ไม่เทียบภาพหน้านี้)")
                continue
            text_rects = [r for c in changes for r in c["a_rects"] + c["b_rects"]]
            # รูปที่เพิ่ม/ลบ/เปลี่ยน — กรอบตรงตัวรูป และกล่องจากการเทียบพิกเซลที่ทับรูปนั้นไม่นับซ้ำ
            notes_img = {"insert": "เพิ่มรูป (เช่น ลายเซ็น ตราประทับ)", "delete": "รูปถูกลบ", "replace": "รูปเปลี่ยน"}
            for tag, ra, rb in image_changes(doc_a[pa], doc_b[pb]):
                box_a = ra or rb
                box_b = rb or ra
                changes.append({"kind": "visual", "note": notes_img[tag], "a_text": "", "b_text": "",
                                "a_rects": [{"page": pa, "x0": box_a[0], "y0": box_a[1], "x1": box_a[2], "y1": box_a[3]}],
                                "b_rects": [{"page": pb, "x0": box_b[0], "y0": box_b[1], "x1": box_b[2], "y1": box_b[3]}],
                                "a_anchor": None, "b_anchor": None})
                text_rects.append({"page": pb, "x0": box_b[0], "y0": box_b[1], "x1": box_b[2], "y1": box_b[3]})
            for box in visual_boxes(doc_a[pa], doc_b[pb]):
                if _text_area(a.tokens, pa, box) >= 0.5 or _text_area(b.tokens, pb, box) >= 0.5:
                    continue  # ข้อความ — นับจากการเทียบข้อความแล้ว
                if any(_overlap_ratio(box, r) > 0.3 for r in text_rects if r["page"] in (pa, pb)):
                    continue
                rect = {"x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3]}
                changes.append({"kind": "visual", "note": "เส้น/กราฟิกต่างกัน", "a_text": "", "b_text": "",
                                "a_rects": [{"page": pa, **rect}], "b_rects": [{"page": pb, **rect}],
                                "a_anchor": None, "b_anchor": None})

    # ข้อความบนหน้าที่ถูกลบ/เพิ่มทั้งหน้า → รวมเป็นจุดต่าง "หน้าที่ลบ/เพิ่ม" จุดเดียว (ไม่แยกทีละคำซ้ำ)
    deleted = {x for x, y in pairs if y is None}
    inserted = {y for x, y in pairs if x is None}
    page_text_a: dict[int, list[str]] = {}
    page_text_b: dict[int, list[str]] = {}
    kept = []
    for c in changes:
        if c["kind"] == "delete" and c["a_rects"] and all(r["page"] in deleted for r in c["a_rects"]):
            page_text_a.setdefault(c["a_rects"][0]["page"], []).append(c["a_text"])
            continue
        if c["kind"] == "insert" and c["b_rects"] and all(r["page"] in inserted for r in c["b_rects"]):
            page_text_b.setdefault(c["b_rects"][0]["page"], []).append(c["b_text"])
            continue
        kept.append(c)
    changes = kept

    for pa, pb in pairs:
        if pa is None:
            changes.append({"kind": "page_insert", "a_text": "",
                            "b_text": f"หน้า {pb + 1}: " + " ".join(page_text_b.get(pb, []))[:300], "a_rects": [],
                            "b_rects": [_full(pb, b.page_sizes[pb])], "a_anchor": None, "b_anchor": None})
        elif pb is None:
            changes.append({"kind": "page_delete", "a_text": f"หน้า {pa + 1}: " + " ".join(page_text_a.get(pa, []))[:300],
                            "b_text": "",
                            "a_rects": [_full(pa, a.page_sizes[pa])], "b_rects": [], "a_anchor": None, "b_anchor": None})

    changes.sort(key=_order)
    for i, c in enumerate(changes, 1):
        c["id"] = i
    summary = {k: sum(1 for c in changes if c["kind"] == k)
               for k in ("insert", "delete", "replace", "visual", "page_insert", "page_delete", "page_size")}
    report(100, "เสร็จ")
    return {
        "a": {"pages": len(a.page_sizes), "page_sizes": a.page_sizes, "ocr_pages": a.ocr_pages, "empty_pages": a.empty_pages},
        "b": {"pages": len(b.page_sizes), "page_sizes": b.page_sizes, "ocr_pages": b.ocr_pages, "empty_pages": b.empty_pages},
        "pairs": [[x, y] for x, y in pairs],
        "changes": changes,
        "summary": {**summary, "total": len(changes)},
        "notes": notes,
        "identical": not changes,
    }


def _full(page: int, size: tuple[float, float]) -> dict:
    return {"page": page, "x0": 0.0, "y0": 0.0, "x1": size[0], "y1": size[1]}


def _order(c: dict):
    """เรียงตามตำแหน่งในไฟล์ใหม่ (B) — ส่วนที่ถูกลบใช้ตำแหน่งที่ควรอยู่ใน B · หน้าที่ถูกลบทั้งหน้าใช้ตำแหน่งใน A"""
    for r in (c["b_rects"][:1] or ([c["b_anchor"]] if c["b_anchor"] else [])):
        return (0, r["page"], round(r["y0"] / 4), r["x0"])
    for r in (c["a_rects"][:1] or ([c["a_anchor"]] if c["a_anchor"] else [])):
        return (1, r["page"], round(r["y0"] / 4), r["x0"])
    return (2, 0, 0, 0)
