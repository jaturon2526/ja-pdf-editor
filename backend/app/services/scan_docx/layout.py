"""จัดผล OCR ของหน้าสแกนเป็นโครงเอกสาร: ย่อหน้า (พร้อมจัดชิด/เยื้อง/tab/จุดไข่ปลา), ตาราง, กรอบ, รูป

หน่วยในโครงเอกสารเป็น point (1/72 นิ้ว) วัดจากมุมซ้ายบนของหน้ากระดาษ
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.services import ocr_thai, thai_text
from app.services.scan_docx.analyze import Box, Graphic, Grid, PageAnalysis, area, inside, overlap

# ความสูงส่วนกลางตัวอักษร (ฐานนิยมของก้อนหมึก) ÷ ขนาดฟอนต์ Sarabun — วัดจากฟอนต์จริง 150–300 dpi (0.56–0.61)
SARABUN_CHAR_RATIO = 0.59
_THAI = re.compile(r"[฀-๿]")
_CHECKMARK = re.compile(r"[/vVwWJy\u00a5\u2713\u221a]{1,2}")


# ---------------------------------------------------------------- โครงเอกสาร

@dataclass
class Run:
    text: str
    bold: bool = False
    size: float = 11.0
    color: str | None = None    # "FFFFFF" = ตัวอักษรขาว (บนพื้นเข้ม)


@dataclass
class Tab:
    pos: float                  # pt จากขอบซ้ายของพื้นที่ข้อความ (margin)
    align: str = "left"         # left | right | center
    leader: str | None = None   # None | "dot"


@dataclass
class Paragraph:
    runs: list[Run]
    align: str = "left"         # left | center | right | justify
    left: float = 0.0           # เยื้องซ้าย (pt จาก margin)
    first: float = 0.0          # เยื้องบรรทัดแรก (บวก = เข้า, ลบ = ห้อย)
    tabs: list[Tab] = field(default_factory=list)
    space_before: float = 0.0
    line: float | None = None   # ระยะบรรทัดแบบ exact (pt) — None = ตามฟอนต์
    top: float = 0.0            # ตำแหน่งบนสุดของหมึก (pt) — ใช้คำนวณระยะห่าง
    bottom: float = 0.0
    lines: int = 1
    ink_left: float = 0.0       # ตำแหน่งซ้ายสุดของหมึกจริง (pt จาก margin) — ใช้ตอนเลิกจัดกึ่งกลาง


@dataclass
class Picture:
    box: Box                    # px ในภาพหน้า
    kind: str
    top: float = 0.0
    bottom: float = 0.0
    x: float = 0.0              # pt จากขอบซ้ายกระดาษ
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    floating: bool = False      # วางลอยตำแหน่งตายตัว (อยู่ข้างข้อความ) แทนการแทรกในบรรทัด
    host: object = None         # ย่อหน้าที่รูปลอยยึดตำแหน่งแนวตั้ง (เลื่อนตามข้อความ)
    rel_y: float = 0.0          # ระยะจากบนสุดของย่อหน้านั้น (pt)
    space_before: float = 0.0
    align: str = "left"
    left: float = 0.0


@dataclass
class TableCell:
    row: int
    col: int
    row_span: int
    col_span: int
    paragraphs: list[Paragraph]
    shade: str | None = None    # สีพื้นช่อง (hex) — หัวตารางพื้นเข้ม


@dataclass
class Table:
    col_widths: list[float]     # pt
    row_heights: list[float]    # pt
    cells: list[TableCell]
    left: float = 0.0           # pt จาก margin
    top: float = 0.0
    bottom: float = 0.0
    space_before: float = 0.0
    is_box: bool = False


@dataclass
class PageLayout:
    width: float
    height: float
    margins: tuple[float, float, float, float]   # left, top, right, bottom (pt)
    blocks: list                                  # Paragraph | Picture | Table (เรียงบนลงล่าง)


# ---------------------------------------------------------------- คำ / บรรทัด

@dataclass
class Word:
    text: str
    box: tuple[float, float, float, float]
    conf: float
    bold: bool = False
    garbage: bool = False


@dataclass
class Segment:
    words: list[Word]
    leader: bool = False        # แถวจุดไข่ปลา (ไม่มีคำ)
    box: tuple[float, float, float, float] = (0, 0, 0, 0)

    def __post_init__(self):
        if self.words:
            self.box = (min(w.box[0] for w in self.words), min(w.box[1] for w in self.words),
                        max(w.box[2] for w in self.words), max(w.box[3] for w in self.words))


@dataclass
class Row:
    segments: list[Segment]
    char_h: float               # px

    @property
    def box(self):
        bs = [s.box for s in self.segments]
        return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))

    @property
    def text_segments(self):
        return [s for s in self.segments if not s.leader]


def _join_words(words: list[Word], char_h: float) -> list[Run]:
    """ต่อคำเป็นข้อความ: ช่องว่างแคบระหว่างคำไทย (Tesseract แทรกกลางคำ/วลี) ไม่ใส่ช่องว่าง"""
    runs: list[Run] = []
    prev: Word | None = None
    for w in words:
        sep = ""
        if prev is not None:
            gap = w.box[0] - prev.box[2]
            both_thai = _THAI.search(prev.text[-1:]) and _THAI.search(w.text[:1])
            punct = prev.text[-1:] in "_-/.:" or w.text[:1] in "_-/.:,)"
            sep = "" if (both_thai and gap < 0.45 * char_h) or (punct and gap < 0.25 * char_h) else " "
        if runs and runs[-1].bold == w.bold:
            runs[-1].text += sep + w.text
        else:
            if sep and runs:
                runs[-1].text += sep
            runs.append(Run(w.text, w.bold))
        prev = w
    return runs


def _stroke_ratio(mask: np.ndarray, box) -> float:
    """ความหนาเส้นโดยประมาณ (2·พื้นที่/เส้นรอบรูป) — ใช้แยกตัวหนา (เทียบกับค่ากลางของหน้า)"""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    sub = mask[max(0, y0):y1, max(0, x0):x1]
    if sub.size == 0 or not sub.any():
        return 0.0
    er = cv2.erode(sub.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    perim = int((sub & ~er).sum())
    return 2.0 * sub.sum() / max(1, perim)


def _line_char_h(mask: np.ndarray, box, default: float, words: list | None = None) -> float:
    """ความสูงตัวอักษรของบรรทัด: ฐานนิยมความสูงก้อนหมึก — นับเฉพาะในกรอบคำภาษาไทยถ้ามี (ตัวเลข/อักษรละติน
    สูงกว่าตัวอักษรไทยส่วนกลาง บรรทัดที่มีตัวเลขเยอะจะได้ขนาดใหญ่เกินจริง) · ก้อนหมึกน้อยวัดไม่นิ่ง ใช้ค่าของทั้งหน้า"""
    boxes = [box]
    if words:
        thai = [w.box for w in words if _THAI.search(w.text)]
        if thai:
            boxes = thai
    hs_all = []
    pad = int(0.4 * default)
    for b in boxes:
        x0, y0, x1, y1 = (int(round(v)) for v in b)
        sub = mask[max(0, y0 - pad):y1 + pad, max(0, x0):x1]
        if sub.size == 0:
            continue
        n, _l, st, _c = cv2.connectedComponentsWithStats(sub.astype(np.uint8), connectivity=8)
        hs = st[1:, cv2.CC_STAT_HEIGHT]
        ws = st[1:, cv2.CC_STAT_WIDTH]
        hs_all.extend(hs[(hs >= 0.45 * default) & (hs <= 3 * default) & (ws <= 2.5 * hs)].tolist())
    if len(hs_all) < 12:
        return default
    hist = np.bincount(np.asarray(hs_all, dtype=np.int64))
    smooth = np.convolve(hist, np.ones(3), mode="same")
    return float(np.argmax(smooth))


LOW_CONF = 45                   # คำที่มั่นใจต่ำกว่านี้ไม่ใช้เป็นข้อความ — กลุ่มใหญ่พอ = ลายมือ/ลายเซ็น → รูป


def _lines_score(lines) -> float:
    """คะแนนผล OCR ทั้งหน้า (อักษรไทยในคำที่มีในพจนานุกรม + ละติน/ตัวเลขครึ่งน้ำหนัก) — ใช้เลือกระหว่างผลสองชุด"""
    from app.services.pdf_service.scan import _text_score

    return _text_score([(None, w.text) for ln in lines for w in ln.words])


def ocr_words(pa: PageAnalysis) -> list[list[Word]]:
    """OCR ทั้งหน้า (ภาพที่ลบเส้น/รูป/จุดไข่ปลาแล้ว) → บรรทัดของคำ
    - ทิ้งคำในพื้นที่รูป และคำซ้ำ (แถบบรรทัดของ ocr_thai ซ้อนกัน → --psm 6 อ่านบรรทัดข้างเคียงซ้ำ)
    - คำที่มั่นใจต่ำ: รวมกลุ่มเป็นพื้นที่ "ลายมือ/ลายเซ็น" แล้วเพิ่มเป็นรูป (pa.graphics) แทนข้อความขยะ"""
    from app.services.scan_docx.analyze import Graphic, _cluster, union

    lines = ocr_thai.recognize(pa.text_gray)   # รวมการอ่านซ้ำบรรทัดไทยที่ถูกอ่านเป็นอังกฤษแล้ว
    if pa.layer_lines and not pa.angle:
        # ไฟล์จากเมนูสแกน: มีข้อความที่อ่านไว้ตอนสแกน (อ่านจากภาพเทาก่อนตัดเป็นขาวดำ) — เทียบกับผลอ่านใหม่แล้วใช้ผลที่ดีกว่า
        layer = [ocr_thai.OcrLine([ocr_thai.OcrWord(t, b, 90.0) for b, t in ln]) for ln in pa.layer_lines]
        if _lines_score(layer) > _lines_score(lines):
            lines = layer
    cand: list[tuple[int, Word]] = []
    for li, ln in enumerate(lines):
        for w in ln.words:
            if not w.text.strip():
                continue
            b = tuple(float(v) for v in w.box)
            ib = tuple(int(v) for v in b)
            if b[2] - b[0] < 1 or b[3] - b[1] < 1:
                continue
            if any(inside(ib, g.box, 0.5) for g in pa.graphics):
                continue
            cand.append((li, Word(w.text, b, w.conf)))
    # คำซ้ำ: กรอบซ้อนกันมากกับคำในบรรทัดอื่น → เก็บคำที่มั่นใจกว่า
    drop = set()
    for i, (li, w) in enumerate(cand):
        for j in range(i + 1, len(cand)):
            lj, v = cand[j]
            if li == lj:
                continue
            ov = overlap(tuple(int(x) for x in w.box), tuple(int(x) for x in v.box))
            if ov > 0.5 * min(area(tuple(int(x) for x in w.box)), area(tuple(int(x) for x in v.box))):
                drop.add(i if (w.conf * len(w.text)) < (v.conf * len(v.text)) else j)
    _reread_english(pa, cand, drop)
    # ช่วงคำที่อ่านเป็นข้อความไทยที่ไม่มีความหมาย (ลายมือ/ลายเซ็นที่ Tesseract มั่นใจผิด ๆ) → ถือเป็นคำมั่นใจต่ำ
    by_line: dict[int, list[int]] = {}
    for k, (li, w) in enumerate(cand):
        if k not in drop:
            by_line.setdefault(li, []).append(k)
    for ks in by_line.values():
        ks.sort(key=lambda k: cand[k][1].box[0])
        groups: list[list[int]] = [[ks[0]]]
        for k in ks[1:]:
            if cand[k][1].box[0] - cand[groups[-1][-1]][1].box[2] > 2.6 * pa.char_h:
                groups.append([k])
            else:
                groups[-1].append(k)
        for g in groups:
            text = "".join(cand[k][1].text for k in g)
            thai = sum(1 for c in text if "\u0E01" <= c <= "\u0E4E")
            letters = sum(1 for c in text if c.isalnum())
            conf = statistics.mean(cand[k][1].conf for k in g)
            garbage = (thai >= 4 and thai_text.dictionary_coverage(text) < 0.35 and conf < 80) \
                or (thai == 0 and letters <= 3 and conf < 80 and not text.strip().isdigit()) \
                or (thai == 0 and len(g) <= 3 and all(len(cand[k][1].text) <= 3 for k in g) and conf < 85
                    and not text.isdigit())
            if garbage:
                for k in g:
                    cand[k][1].conf = min(cand[k][1].conf, LOW_CONF - 1)
                    cand[k][1].garbage = True
    # คำมั่นใจต่ำที่อยู่กลางบรรทัดข้อความดี (รหัส/สัญลักษณ์ที่อ่านยาก) = ข้อความ ไม่ใช่ลายมือ
    good_by_line: dict[int, list[Word]] = {}
    for k, (li, w) in enumerate(cand):
        if k not in drop and w.conf >= LOW_CONF:
            good_by_line.setdefault(li, []).append(w)

    def in_text(li: int, w: Word) -> bool:
        for v in good_by_line.get(li, ()):
            if max(v.box[0] - w.box[2], w.box[0] - v.box[2]) < 2.6 * pa.char_h:
                return True
        cy = (w.box[1] + w.box[3]) / 2
        for ld in pa.leaders:     # คำนำหน้าจุดไข่ปลาในแบบฟอร์ม ("ที่อยู่ ........")
            if ld.box[1] - pa.char_h <= cy <= ld.box[3] + pa.char_h and -pa.char_h < ld.box[0] - w.box[2] < 3 * pa.char_h:
                return True
        return False

    ch = pa.char_h
    low, keep_low = [], set()
    for k, (li, w) in enumerate(cand):
        if k in drop or w.conf >= LOW_CONF:
            continue
        if any(inside(tuple(int(x) for x in w.box), g.box, 0.6) for g in pa.grids):
            if w.conf >= 20:
                keep_low.add(k)
            continue
        if in_text(li, w):
            if w.conf >= 30 and not getattr(w, "garbage", False):
                keep_low.add(k)
            continue
        low.append(w)
    for group in _cluster([tuple(int(x) for x in w.box) for w in low], gap=1.6 * ch):
        b = group[0]
        for g in group[1:]:
            b = union(b, g)
        # ลายมือ/ลายเซ็นมักสูงกว่าตัวพิมพ์หรือกินพื้นที่กว้าง — คำพิมพ์สั้น ๆ ที่อ่านไม่ออกไม่กลายเป็นรูป
        if (b[3] - b[1]) >= 1.5 * ch or area(b) >= 10 * ch * ch:
            pa.graphics.append(Graphic(b, "image"))
    out: dict[int, list[Word]] = {}
    for k, (li, w) in enumerate(cand):
        if k in drop:
            continue
        if w.conf < LOW_CONF and k not in keep_low:
            continue
        if any(inside(tuple(int(x) for x in w.box), g.box, 0.5) for g in pa.graphics):
            continue
        out.setdefault(li, []).append(w)
    result = [out[k] for k in sorted(out)]
    # ช่องติ๊ก → อักขระ ☐ (รวมเข้าบรรทัดเดียวกันทีหลังใน _merge_line_fragments)
    for b in pa.checkboxes:
        result.append([Word("\u2610", tuple(float(v) for v in b), 99.0)])
    return result




_CODE = re.compile(r"\*{0,2}[A-Za-z]{1,5}[0-9]{0,4}")
_ASCII_WORD = re.compile(r"[A-Za-z0-9*_@#&+%/.:,()\\-]+")


def _reread_english(pa: PageAnalysis, cand: list, drop: set) -> None:
    """คำภาษาอังกฤษ/รหัสที่โมเดลไทย+อังกฤษอ่านพลาด ("Address_test" → "คสใต่เอะรร", "*M9" มั่นใจ 18)
    → อ่านเฉพาะคำนั้นซ้ำด้วยโมเดลอังกฤษ ใช้ผลใหม่เมื่อมั่นใจกว่าชัดเจน"""
    jobs = []
    for k, (_li, w) in enumerate(cand):
        if k in drop:
            continue
        thai = sum(1 for c in w.text if "\u0E01" <= c <= "\u0E4E")
        ascii_like = any(c.isascii() and c.isalnum() for c in w.text) or "*" in w.text
        suspicious_thai = thai >= 4 and thai_text.dictionary_coverage(w.text) < 0.6
        if (ascii_like and w.conf < 75) or suspicious_thai:
            x0, y0, x1, y1 = w.box
            need = max(60.0, w.conf + 10) if ascii_like else 88.0
            for f in (0.3, 0.8):     # ขอบรอบคำสองขนาด (รหัสสั้นต้องการขอบกว้าง คำยาวต้องการขอบแคบ) เลือกผลที่มั่นใจกว่า
                m = f * (y1 - y0)
                jobs.append((k, need, pa.text_gray.crop((int(max(0, x0 - m)), int(max(0, y0 - m)), int(x1 + m), int(y1 + m)))))
    if not jobs:
        return
    pages = ocr_thai._tesseract_batch([j[2] for j in jobs], 7, "eng")
    best: dict[int, tuple[str, float, float]] = {}
    for (k, need, _img), page in zip(jobs, pages):
        alt = " ".join(page.text.split()).strip()
        alt = re.sub(r'^[“”"\']+', "*", alt)      # ดอกจันที่ OCR อ่านเป็นเครื่องหมายคำพูด (รหัส *M9, **TY1)
        if not alt or sum(c.isalnum() for c in alt) < 2 or not _ASCII_WORD.fullmatch(alt.replace(" ", "")):
            continue
        if k not in best or page.conf > best[k][1]:
            best[k] = (alt, page.conf, need)
    for k, (alt, conf, need) in best.items():
        w = cand[k][1]
        # รหัสสั้น ๆ (ตัวอักษร+ตัวเลข) ความมั่นใจของ Tesseract ต่ำเสมอแม้อ่านถูก — ยอมรับที่เกณฑ์ต่ำกว่า
        code_like = bool(_CODE.fullmatch(alt)) and need < 88
        if conf >= need or (code_like and conf >= 25):
            w.text, w.conf = alt, max(conf, 50.0 if code_like else conf)


def mark_bold(lines: list[list[Word]], mask: np.ndarray, char_h: float) -> None:
    """ตัวหนา: ความหนาเส้น ÷ ความสูงตัวอักษรของบรรทัด สูงกว่าค่ากลางของหน้าชัดเจน
    (หารด้วยความสูงตัวอักษรของบรรทัด ไม่ใช่ของคำ — คำที่เป็นตัวเลขล้วนกรอบเตี้ยกว่าคำไทย)"""
    ratios = []
    for ln in lines:
        lb = (min(w.box[0] for w in ln), min(w.box[1] for w in ln), max(w.box[2] for w in ln), max(w.box[3] for w in ln))
        lh = _line_char_h(mask, lb, char_h, ln)
        for w in ln:
            if len(w.text) >= 2:
                ratios.append((w, _stroke_ratio(mask, w.box) / max(1.0, lh)))
    vals = [r for _w, r in ratios if r > 0]
    if len(vals) < 8:
        return
    med = statistics.median(vals)
    for w, r in ratios:
        w.bold = r > 1.16 * med


def _segments(words: list[Word], char_h: float, full_width: bool = False, mask: np.ndarray | None = None) -> list[Segment]:
    """แบ่งบรรทัด OCR เป็นช่วง ๆ ตามช่องว่างกว้าง (คอลัมน์/ข้อความชิดขวาในบรรทัดเดียวกัน)
    บรรทัดที่ยาวเต็มความกว้าง (ย่อหน้าจัดเต็มบรรทัด ช่องว่างระหว่างคำถูกยืด) ต้องห่างมากกว่าจึงแบ่ง"""
    words = sorted(words, key=lambda w: w.box[0])
    limit = (5.5 if full_width else 2.6) * char_h
    segs: list[list[Word]] = [[words[0]]]
    for w in words[1:]:
        prev = segs[-1][-1]
        gap = w.box[0] - prev.box[2]
        if gap > limit and mask is not None:
            # กรอบคำจาก Tesseract อาจคลาดเคลื่อน (จับคู่ข้อความกับ token ไม่ตรง) — ช่องว่างที่ยังมีหมึกอยู่ไม่ใช่ช่องว่างจริง
            # เฉพาะแถบกลางที่สองคำซ้อนกัน (ไม่เอาหมึกของบรรทัดข้างเคียงที่กรอบคำสูงไปแตะ)
            top, bot = max(prev.box[1], w.box[1]), min(prev.box[3], w.box[3])
            if bot - top < 4:
                top, bot = min(prev.box[1], w.box[1]), max(prev.box[3], w.box[3])
            q = (bot - top) * 0.25
            cols = mask[max(0, int(top + q)):int(bot - q), int(prev.box[2]):int(w.box[0])].any(axis=0)
            if cols.size and cols.mean() > 0.15:
                gap = 0
        if gap > limit:
            segs.append([w])
        else:
            segs[-1].append(w)
    return [Segment(s) for s in segs]


# ---------------------------------------------------------------- ย่อหน้า

class _Ctx:
    def __init__(self, pa: PageAnalysis, dpi: float, left_px: float, right_px: float, mask: np.ndarray):
        self.pa = pa
        self.k = 72.0 / dpi          # px → pt
        self.left = left_px          # ขอบซ้ายพื้นที่ข้อความ (px) — margin หรือขอบในของกรอบ/ช่องตาราง
        self.right = right_px
        self.mask = mask

    def pt(self, px: float) -> float:
        return px * self.k

    def size_of(self, char_h_px: float) -> float:
        s = self.pt(char_h_px) / SARABUN_CHAR_RATIO
        return max(6.0, min(48.0, round(s * 2) / 2))


def _row_size(ctx: _Ctx, row: Row) -> float:
    return ctx.size_of(row.char_h)


def build_paragraphs(rows: list[Row], ctx: _Ctx) -> list[Paragraph]:
    width = ctx.right - ctx.left
    paras: list[Paragraph] = []
    cur: list[Row] = []

    def flush():
        if cur:
            paras.append(_make_paragraph(cur, ctx))
            cur.clear()

    for row in rows:
        if not cur:
            cur.append(row)
            continue
        prev = cur[-1]
        pb, rb = prev.box, row.box
        h = max(prev.char_h, row.char_h)
        same_size = abs(prev.char_h - row.char_h) <= 0.25 * h
        close = rb[1] - pb[3] < 1.1 * h
        single = len(prev.segments) == 1 and len(row.segments) == 1 and not prev.segments[0].leader \
            and not row.segments[0].leader
        first_left = min(r.box[0] for r in cur)
        body_left = cur[1].box[0] if len(cur) > 1 else None
        full = pb[2] > ctx.right - 2.2 * h and (pb[2] - min(pb[0], rb[0])) > 0.5 * width
        if body_left is not None:
            aligned = abs(rb[0] - body_left) < 1.2 * h
        else:
            # บรรทัดที่สอง: ชิดซ้ายเท่าบรรทัดแรก หรือ ออกซ้ายกว่า (บรรทัดแรกเยื้องเข้า)
            aligned = abs(rb[0] - first_left) < 1.2 * h or (rb[0] < first_left and first_left - rb[0] < 8 * h)
        if single and same_size and close and full and aligned:
            cur.append(row)
        else:
            flush()
            cur.append(row)
    flush()
    return paras


def _make_paragraph(rows: list[Row], ctx: _Ctx) -> Paragraph:
    size = ctx.size_of(statistics.median(r.char_h for r in rows))
    top = ctx.pt(min(r.box[1] for r in rows))
    bottom = ctx.pt(max(r.box[3] for r in rows))
    if len(rows) == 1:
        return _single_row_paragraph(rows[0], ctx, size, top, bottom)
    runs: list[Run] = []
    for i, r in enumerate(rows):
        seg_runs = _join_words(r.segments[0].words, r.char_h)
        if runs and seg_runs:
            # ต่อบรรทัด: ไทยต่อไทยไม่เว้นวรรค (ภาษาไทยไม่ใช้ช่องว่างตัดบรรทัด) อื่น ๆ เว้นวรรค
            sep = "" if (_THAI.search(runs[-1].text[-1:]) and _THAI.search(seg_runs[0].text[:1])) else " "
            if runs[-1].bold == seg_runs[0].bold:
                runs[-1].text += sep + seg_runs[0].text
                seg_runs = seg_runs[1:]
            else:
                runs[-1].text += sep
        runs.extend(seg_runs)
    for r in runs:
        r.size = size
    first_x = rows[0].box[0]
    body_x = statistics.median(r.box[0] for r in rows[1:])
    left = max(0.0, ctx.pt(body_x - ctx.left))
    first = ctx.pt(first_x - body_x)
    pitch = statistics.median(rows[i + 1].box[1] - rows[i].box[1] for i in range(len(rows) - 1))
    # บรรทัดเต็มเกือบทุกบรรทัด (ยกเว้นบรรทัดสุดท้าย) → กระจายเต็มบรรทัดแบบไทย
    full = sum(1 for r in rows[:-1] if r.box[2] > ctx.right - 2.5 * r.char_h)
    align = "justify" if full >= max(1, len(rows) - 1) * 0.7 else "left"
    return Paragraph(runs, align, left, first, [], 0.0, _line_pitch(ctx, pitch, size), top, bottom, len(rows))


def _line_pitch(ctx: _Ctx, pitch_px: float, size: float) -> float:
    # ระยะบรรทัดตามต้นฉบับ แต่ไม่ชิดจนสระบน/วรรณยุกต์ซ้อนของ Sarabun ถูกตัด
    return round(max(ctx.pt(pitch_px), 1.22 * size), 1)


def _single_row_paragraph(row: Row, ctx: _Ctx, size: float, top: float, bottom: float) -> Paragraph:
    segs = row.segments
    width = ctx.right - ctx.left
    first = segs[0]
    runs: list[Run] = []
    tabs: list[Tab] = []
    left_px = first.box[0] - ctx.left
    align = "left"
    texts = row.text_segments
    if len(segs) == 1 and not first.leader:
        x0, _y0, x1, _y1 = first.box
        center = (x0 + x1) / 2
        mid = (ctx.left + ctx.right) / 2
        if abs(center - mid) < 0.04 * width and (x0 - ctx.left) > 0.12 * width:
            align, left_px = "center", 0
        elif x1 > ctx.right - 0.03 * width and (x0 - ctx.left) > 0.35 * width:
            align, left_px = "right", 0
        runs = _join_words(first.words, row.char_h)
    else:
        start = 0 if not first.leader else None
        if first.leader:
            # บรรทัดเริ่มด้วยจุดไข่ปลา: tab แบบจุดนำจากขอบซ้าย
            left_px = 0
            runs.append(Run("\t"))
            tabs.append(Tab(ctx.pt(first.box[2] - ctx.left), "left", "dot"))
        else:
            runs.extend(_join_words(first.words, row.char_h))
        for s in segs[1:]:
            if s.leader:
                runs.append(Run("\t"))
                tabs.append(Tab(ctx.pt(s.box[2] - ctx.left), "left", "dot"))
                continue
            prev = segs[segs.index(s) - 1]
            if prev.leader:
                # ข้อความต่อท้ายจุดไข่ปลา (เช่น "วันที่ ....... เดือน")
                runs.append(Run(" "))
            else:
                at_right = s.box[2] > ctx.right - 0.03 * width and s is segs[-1]
                if at_right:
                    tabs.append(Tab(ctx.pt(s.box[2] - ctx.left), "right"))
                else:
                    tabs.append(Tab(ctx.pt(s.box[0] - ctx.left), "left"))
                runs.append(Run("\t"))
            runs.extend(_join_words(s.words, row.char_h))
        del start
    for r in runs:
        r.size = size
    return Paragraph(runs, align, max(0.0, ctx.pt(left_px)), 0.0, tabs, 0.0, round(1.3 * size, 1), top, bottom, 1,
                     max(0.0, ctx.pt(first.box[0] - ctx.left)))


# ---------------------------------------------------------------- ประกอบหน้า

def _merge_line_fragments(lines: list[list[Word]]) -> list[list[Word]]:
    """คำที่ OCR แยกออกมาเป็นบรรทัดเล็ก ๆ ทั้งที่อยู่ระดับเดียวกับบรรทัดอื่น (คำท้ายบรรทัดที่มีวรรณยุกต์สูง
    ถูกตัดเป็นแถบแยก) → รวมเข้าบรรทัดนั้น"""
    def box(ws):
        return (min(w.box[0] for w in ws), min(w.box[1] for w in ws), max(w.box[2] for w in ws), max(w.box[3] for w in ws))

    lines = [list(ws) for ws in lines if ws]
    changed = True
    while changed:
        changed = False
        lines.sort(key=lambda ws: len(ws))
        for i, ws in enumerate(lines):
            a = box(ws)
            for j, vs in enumerate(lines):
                if i == j or len(vs) < len(ws):
                    continue
                b = box(vs)
                vo = min(a[3], b[3]) - max(a[1], b[1])
                clash = any(min(w.box[2], v.box[2]) - max(w.box[0], v.box[0]) > 0.3 * min(w.box[2] - w.box[0], v.box[2] - v.box[0])
                            for w in ws for v in vs)
                # ศูนย์กลางแนวตั้งของคำต้องใกล้กัน (ไม่ใช้กรอบทั้งบรรทัด — คำสูงคำเดียวทำให้กรอบกินบรรทัดข้างเคียง)
                ca = statistics.median((w.box[1] + w.box[3]) / 2 for w in ws)
                cb = statistics.median((v.box[1] + v.box[3]) / 2 for v in vs)
                hb = statistics.median(v.box[3] - v.box[1] for v in vs)
                ha = statistics.median(w.box[3] - w.box[1] for w in ws)
                strong = vo > 0.6 * min(a[3] - a[1], b[3] - b[1]) and abs(ca - cb) < 0.6 * max(ha, hb)
                if vo > 0 and (abs(ca - cb) < 0.35 * hb or strong) and not clash:
                    vs.extend(ws)
                    vs.sort(key=lambda w: w.box[0])
                    del lines[i]
                    changed = True
                    break
            if changed:
                break
    lines.sort(key=lambda ws: box(ws)[1])
    return lines


def _rows_from(lines: list[list[Word]], leaders: list[Box], ctx: _Ctx, default_h: float,
               drop_single: bool = True) -> list[Row]:
    lines = _merge_line_fragments(lines)
    # บรรทัดที่เหลืออักขระเดียวหลังรวมแล้ว (จุดหมึก/เศษตัวอักษร) ไม่ใช่ข้อความ
    if drop_single:
        def near_leader(ws):   # "1." หน้าจุดไข่ปลา (จุดถูกนับเป็นส่วนของเส้นจุด)
            cy = statistics.median((w.box[1] + w.box[3]) / 2 for w in ws)
            return any(lb[1] - default_h <= cy <= lb[3] + default_h for lb in leaders)
        lines = [ws for ws in lines if sum(len(w.text.strip()) for w in ws) > 1 or near_leader(ws)]
    rows: list[Row] = []
    width = ctx.right - ctx.left
    for ws in lines:
        lb = (min(w.box[0] for w in ws), min(w.box[1] for w in ws), max(w.box[2] for w in ws), max(w.box[3] for w in ws))
        ch = _line_char_h(ctx.mask, lb, default_h, ws)
        full = lb[0] < ctx.left + 0.15 * width and lb[2] > ctx.right - 0.08 * width
        rows.append(Row(_segments(ws, ch, full, ctx.mask), ch))
    # จุดไข่ปลา: ต่อเข้าบรรทัดที่อยู่ระดับเดียวกัน ไม่งั้นเป็นบรรทัดของตัวเอง (บรรทัดว่างให้เขียน)
    for lb in leaders:
        cy = (lb[1] + lb[3]) / 2
        best = None
        for r in rows:
            b = r.box
            if b[1] - 0.3 * r.char_h <= cy <= b[3] + 0.3 * r.char_h:
                best = r
                break
        seg = Segment([], True, tuple(float(v) for v in lb))
        if best is not None:
            best.segments.append(seg)
            best.segments.sort(key=lambda s: s.box[0])
            # เส้นจุดที่ขาดเป็นช่วง ๆ ในบรรทัดเดียวกัน (ไม่มีข้อความคั่น) → เส้นเดียว
            merged: list[Segment] = []
            for sg in best.segments:
                if merged and sg.leader and merged[-1].leader:
                    a = merged[-1].box
                    merged[-1] = Segment([], True, (a[0], min(a[1], sg.box[1]), max(a[2], sg.box[2]), max(a[3], sg.box[3])))
                else:
                    merged.append(sg)
            best.segments = merged
        else:
            h = default_h
            rows.append(Row([seg], h))
    rows.sort(key=lambda r: r.box[1])
    # จุดไข่ปลาที่ต่อจากข้อความ: ขยายแถวจุดให้เริ่มต่อจากคำก่อนหน้า (กรอบ OCR ของจุดถูกลบไปแล้ว)
    return rows


def layout_page(pa: PageAnalysis, dpi: float, page_w_pt: float, page_h_pt: float) -> PageLayout:
    k = 72.0 / dpi
    a = np.asarray(pa.text_gray)
    mask = a <= ocr_thai.otsu_threshold(a) if a.size else np.zeros((1, 1), bool)
    lines = ocr_words(pa)
    mark_bold(lines, mask, pa.char_h)

    cx0, cy0, cx1, cy1 = pa.content
    ctx = _Ctx(pa, dpi, cx0, cx1, mask)

    # คำในตาราง/กรอบ → ช่อง · ที่เหลือ → เนื้อหาหลัก
    grid_words: dict[int, list[Word]] = {i: [] for i in range(len(pa.grids))}
    body_lines: list[list[Word]] = []
    for ws in lines:
        rest = []
        for w in ws:
            ib = tuple(int(v) for v in w.box)
            gi = next((i for i, g in enumerate(pa.grids) if inside(ib, g.box, 0.6)), None)
            if gi is None:
                rest.append(w)
            else:
                grid_words[gi].append(w)
        if rest:
            body_lines.append(rest)
    body_leaders = [ld.box for ld in pa.leaders if not any(inside(ld.box, g.box, 0.6) for g in pa.grids)]
    rows = _rows_from(body_lines, body_leaders, ctx, pa.char_h)

    blocks: list = []
    paras = build_paragraphs(rows, ctx)
    body_size = _snap_sizes(paras)
    blocks.extend(paras)
    for gi, g in enumerate(pa.grids):
        t = _table(g, grid_words[gi], [ld.box for ld in pa.leaders if inside(ld.box, g.box, 0.6)], ctx)
        _snap_sizes([p for c in t.cells for p in c.paragraphs])
        blocks.append(t)
    for g in pa.graphics:
        blocks.append(_picture(g, ctx, rows))
    blocks.sort(key=lambda b: b.top)
    # ข้อความข้างโลโก้ (หัวจดหมาย) ที่บังเอิญอยู่กลางหน้า: ถ้าจัดกึ่งกลาง ข้อความ Sarabun ที่กว้างขึ้นจะล้นทับโลโก้
    # → ชิดซ้ายที่ตำแหน่งเดิมแทน
    for p in (b for b in blocks if isinstance(b, Paragraph) and b.align == "center"):
        for pic in (b for b in blocks if isinstance(b, Picture)):
            if min(p.bottom, pic.bottom) - max(p.top, pic.top) > 0 and pic.x + pic.w <= ctx.pt(cx0) + p.ink_left + 2:
                p.align, p.left = "left", p.ink_left
                break

    margins = (ctx.pt(cx0), max(18.0, ctx.pt(cy0) - 6), max(18.0, page_w_pt - ctx.pt(cx1)), max(18.0, page_h_pt - ctx.pt(cy1) - 6))
    _vertical_spacing(blocks, margins[1])
    _fit_page(blocks, page_h_pt - margins[1] - margins[3], page_w_pt - margins[0] - margins[2])
    _anchor_floats(blocks)
    return PageLayout(page_w_pt, page_h_pt, margins, blocks)


def _anchor_floats(blocks: list) -> None:
    """รูปลอยยึดกับย่อหน้าที่อยู่ระดับเดียวกัน (ตำแหน่งแนวตั้งเทียบย่อหน้า) — ถ้าข้อความเลื่อนขึ้นลงเพราะ
    ระยะบรรทัดของ Sarabun ต่างจากต้นฉบับ รูปจะเลื่อนตาม ไม่ทับข้อความ"""
    paras = [b for b in blocks if isinstance(b, Paragraph) and b.runs]
    for pic in (b for b in blocks if isinstance(b, Picture) and b.floating):
        if not paras:
            continue
        covering = [p for p in paras if p.top - 2 <= pic.y <= p.bottom + 2]
        host = covering[0] if covering else min(paras, key=lambda p: abs(p.top - pic.y))
        size = host.runs[0].size
        line = host.line or 1.3 * size
        pic.host = host
        pic.rel_y = round(pic.y - host.top + max(0.0, (line - size) / 2), 1)


def _snap_sizes(paras: list[Paragraph], body: float | None = None) -> float:
    """ขนาดอักษรที่ใกล้ขนาดเนื้อหาหลัก (±22%) ให้เท่ากัน — ค่าที่วัดจากภาพแกว่งทีละบรรทัด"""
    weights: dict[float, int] = {}
    for p in paras:
        n = sum(len(r.text) for r in p.runs)
        if p.runs:
            weights[p.runs[0].size] = weights.get(p.runs[0].size, 0) + n
    if body is None:
        body = max(weights, key=weights.get) if weights else 11.0
    for p in paras:
        for r in p.runs:
            if abs(r.size - body) <= 0.22 * body:
                r.size = body
        if p.line and p.runs:
            p.line = round(max(p.line, 1.22 * p.runs[0].size), 1)
    return body


def _picture(g: Graphic, ctx: _Ctx, rows: list[Row]) -> Picture:
    x0, y0, x1, y1 = g.box
    pic = Picture(g.box, g.kind, top=ctx.pt(y0), bottom=ctx.pt(y1), x=ctx.pt(x0), y=ctx.pt(y0),
                  w=ctx.pt(x1 - x0), h=ctx.pt(y1 - y0))
    # อยู่ระดับเดียวกับข้อความ (โลโก้ข้างหัวจดหมาย บาร์โค้ดแนวตั้งข้างที่อยู่) → วางลอยตำแหน่งเดิม
    for r in rows:
        rb = r.box
        if min(rb[3], y1) - max(rb[1], y0) > 0.3 * r.char_h and (rb[2] < x0 or rb[0] > x1 or overlap(
                tuple(int(v) for v in rb), g.box) == 0):
            pic.floating = True
            break
    width = ctx.right - ctx.left
    center = (x0 + x1) / 2
    if abs(center - (ctx.left + ctx.right) / 2) < 0.06 * width:
        pic.align = "center"
    elif x1 > ctx.right - 0.05 * width and x0 > ctx.left + 0.4 * width:
        pic.align = "right"
    else:
        pic.left = max(0.0, ctx.pt(x0 - ctx.left))
    return pic


def _table(g: Grid, words: list[Word], leaders: list[Box], ctx: _Ctx) -> Table:
    cols = [ctx.pt(g.cols[i + 1] - g.cols[i]) for i in range(len(g.cols) - 1)]
    rows_h = [ctx.pt(g.rows[i + 1] - g.rows[i]) for i in range(len(g.rows) - 1)]
    # คำ → บรรทัด → ช่อง
    by_cell: dict[int, list[Word]] = {i: [] for i in range(len(g.cells))}
    for w in words:
        cxw, cyw = (w.box[0] + w.box[2]) / 2, (w.box[1] + w.box[3]) / 2
        for i, c in enumerate(g.cells):
            if c.box[0] <= cxw <= c.box[2] and c.box[1] <= cyw <= c.box[3]:
                by_cell[i].append(w)
                break
    cells = []
    for i, c in enumerate(g.cells):
        pad = 0.25 * ctx.pa.char_h
        sub = _Ctx(ctx.pa, 72.0 / ctx.k, c.box[0] + pad, c.box[2] - pad, ctx.mask)
        lines = _group_lines(by_cell[i])
        lds = [b for b in leaders if inside(b, c.box, 0.6)]
        rows = _rows_from(lines, lds, sub, ctx.pa.char_h, drop_single=False)
        paras = build_paragraphs(rows, sub)
        if g.is_box:
            _vertical_spacing(paras, ctx.pt(c.box[1] + pad))
        else:
            for p in paras:
                p.space_before = 0.0
                if p.align == "left" and len(paras) and _centered_in(p, c.box, ctx):
                    p.align, p.left = "center", 0.0
        # เครื่องหมายถูกในช่องตาราง: OCR อ่านเป็น "/", "v", "vw", "J" ... → ✓
        if len(paras) == 1 and paras[0].runs and _CHECKMARK.fullmatch("".join(r.text for r in paras[0].runs).strip()):
            paras[0].runs = [Run("\u2713", False, paras[0].runs[0].size)]
            paras[0].align, paras[0].left = "center", 0.0
        shade = None
        if any(inside(c.box, inv, 0.7) for inv in ctx.pa.inverted):
            shade = _dark_shade(ctx.pa.color, c.box)
            for p in paras:
                for r in p.runs:
                    r.color = "FFFFFF"
        cells.append(TableCell(c.row, c.col, c.row_span, c.col_span, paras, shade))
    return Table(cols, rows_h, cells, left=max(0.0, ctx.pt(g.box[0] - ctx.left)), top=ctx.pt(g.box[1]),
                 bottom=ctx.pt(g.box[3]), is_box=g.is_box)


def _dark_shade(color, box: Box) -> str:
    """สีพื้นเข้มของช่อง (ค่ามัธยฐานของพิกเซลเข้มในช่อง) เป็น hex"""
    x0, y0, x1, y1 = box
    a = np.asarray(color.crop((x0, y0, x1, y1)).convert("RGB")).reshape(-1, 3)
    dark = a[a.sum(axis=1) < 300]
    if not len(dark):
        return "000000"
    r, g, b = (int(v) for v in np.median(dark, axis=0))
    return f"{r:02X}{g:02X}{b:02X}"


def _centered_in(p: Paragraph, cell_box: Box, ctx: _Ctx) -> bool:
    # ใช้ตำแหน่งที่บันทึกไว้ไม่ได้ (ย่อหน้าเก็บเฉพาะเยื้อง) — ประมาณจากเยื้องซ้ายเทียบความกว้างช่อง
    width = ctx.pt(cell_box[2] - cell_box[0])
    return p.lines == 1 and p.left > 0.15 * width


def _group_lines(words: list[Word]) -> list[list[Word]]:
    """คำในช่องตาราง → บรรทัด (คำที่ศูนย์กลางแนวตั้งใกล้กัน)"""
    out: list[list[Word]] = []
    for w in sorted(words, key=lambda w: ((w.box[1] + w.box[3]) / 2, w.box[0])):
        cy = (w.box[1] + w.box[3]) / 2
        h = w.box[3] - w.box[1]
        if out:
            last = out[-1]
            ly = statistics.median((x.box[1] + x.box[3]) / 2 for x in last)
            if abs(cy - ly) < 0.45 * h:
                last.append(w)
                continue
        out.append([w])
    for ln in out:
        ln.sort(key=lambda w: w.box[0])
    return out


def _vertical_spacing(blocks: list, start_pt: float) -> None:
    """ระยะห่างก่อนแต่ละบล็อก (space before) ให้ตำแหน่งแนวตั้งใกล้ต้นฉบับ — นับเฉพาะบล็อกในบรรทัด
    (รูปลอยไม่กินพื้นที่)"""
    cursor = start_pt
    for b in blocks:
        if isinstance(b, Picture) and b.floating:
            continue
        if isinstance(b, Paragraph):
            size = b.runs[0].size if b.runs else 11.0
            line = b.line or 1.32 * size
            # หมึกบนสุดอยู่ต่ำกว่าขอบบนกล่องบรรทัด ~ (line − ความสูงหมึก)/2
            ink = 1.0 * size
            want = b.top - max(0.0, (line - ink) / 2)
            b.space_before = round(max(0.0, want - cursor), 1)
            cursor = max(cursor, want) + line * b.lines
        elif isinstance(b, Table):
            b.space_before = round(max(0.0, b.top - cursor), 1)
            cursor = max(cursor, b.top) + (b.bottom - b.top)
        else:
            b.space_before = round(max(0.0, b.top - cursor), 1)
            cursor = max(cursor, b.top) + (b.bottom - b.top)


# ---------------------------------------------------------------- ให้พอดีหนึ่งหน้า

_FONT = None


def _text_width(text: str, size: float, bold: bool) -> float:
    global _FONT
    import fitz

    from app.services.scan_docx.writer import FONT_FILES, FONTS_DIR

    if _FONT is None:
        _FONT = {b: fitz.Font(fontfile=str(FONTS_DIR / FONT_FILES["bold" if b else "regular"])) for b in (False, True)}
    return _FONT[bold].text_length(text, fontsize=size)


def _para_lines(p: Paragraph, width: float) -> int:
    """จำนวนบรรทัดโดยประมาณเมื่อพิมพ์ด้วย Sarabun ในความกว้างที่มี"""
    if p.tabs:
        return 1
    avail = max(20.0, width - p.left - max(0.0, p.first))
    total = sum(_text_width(r.text, r.size, r.bold) for r in p.runs)
    return max(1, int(-(-total // avail)))


def _block_height(b, width: float) -> float:
    if isinstance(b, Paragraph):
        size = b.runs[0].size if b.runs else 11.0
        return (b.line or 1.3 * size) * max(b.lines, _para_lines(b, width))
    if isinstance(b, Picture):
        return 0.0 if b.floating else b.h
    if isinstance(b, Table):
        # แถวที่ข้อความ Sarabun สูงกว่าช่องเดิมจะสูงขึ้น (atLeast)
        total = 0.0
        for r, h in enumerate(b.row_heights):
            need = 0.0
            for c in b.cells:
                if c.row == r and c.row_span == 1:
                    w = sum(b.col_widths[c.col:c.col + c.col_span]) - 10
                    need = max(need, sum(_block_height(p, w) for p in c.paragraphs) + 4)
            total += max(h, need)
        return total + 9
    return b.bottom - b.top


def _fit_page(blocks: list, avail: float, width: float) -> None:
    """ข้อความ Sarabun อาจกินที่มากกว่าต้นฉบับ (ตัดบรรทัดต่างกัน) — ถ้าเกินหนึ่งหน้า ลดระยะห่างระหว่างบล็อก
    ก่อน แล้วค่อยลดระยะบรรทัด (ไม่ต่ำกว่า 1.12 เท่าของขนาดอักษร) ให้แต่ละหน้าสแกนยังเป็นหนึ่งหน้า"""
    for b in blocks:
        if isinstance(b, Paragraph):
            b.lines = max(b.lines, _para_lines(b, width))
    spaces = sum(b.space_before for b in blocks if not (isinstance(b, Picture) and b.floating))
    content = sum(_block_height(b, width) for b in blocks)
    budget = avail * 0.92
    over = spaces + content - budget
    if over <= 0:
        return
    if spaces > 0:
        k = max(0.0, (spaces - over) / spaces)
        for b in blocks:
            b.space_before = round(b.space_before * k, 1)
        over -= spaces * (1 - k)
    if over <= 0:
        return
    paras = [b for b in blocks if isinstance(b, Paragraph) and b.runs]
    shrinkable = sum((b.line or 1.3 * b.runs[0].size) * b.lines - 1.12 * b.runs[0].size * b.lines for b in paras)
    if shrinkable <= 0:
        return
    k = min(1.0, over / shrinkable)
    for b in paras:
        size = b.runs[0].size
        line = b.line or 1.3 * size
        b.line = round(line - k * (line - 1.12 * size), 1)
