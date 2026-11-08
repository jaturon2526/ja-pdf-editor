"""แก้ข้อจำกัดของ pdf2docx ตอนแปลง PDF ที่ออกแบบด้วยโปรแกรมกราฟิก (Canva/Figma/PDFium ฯลฯ)

pdf2docx อ่านรูปทรงจาก page.get_cdrawings() แล้วใช้แค่สีเติม (fill) โดยไม่สนความโปร่งใส (fill_opacity)
ไฟล์แบบนี้มักมีรูปทรง "โปร่งใส 100%" สีดำวางทับกล่อง/ข้อความ (ใช้เป็นกรอบจัดกลุ่ม) และรูปทรงที่เติมด้วย
gradient (pattern) ซึ่ง PyMuPDF รายงานเป็นสีดำโปร่งใสเช่นกัน — ผลคือใน Word กลายเป็นกล่อง/เซลล์สีดำทึบ
ทับข้อความจนอ่านไม่ได้

วิธีแก้: ก่อนให้ pdf2docx ใช้รูปทรง ปรับสีตามสิ่งที่ "มองเห็นจริง" บนหน้า
- โปร่งใสเกือบหมด: ดูสีจริงจากภาพที่เรนเดอร์ ถ้าเป็นพื้นขาวทิ้งรูปทรงไป ถ้ามีสี (เช่น gradient) ใช้สีเฉลี่ยนั้นแทน
- โปร่งใสบางส่วน: ผสมสีกับพื้นขาวตามค่า opacity
"""
from __future__ import annotations

import contextlib
import itertools
import logging
import re

import fitz

logger = logging.getLogger("pdf2docx_fixes")

_TRANSPARENT = 0.05  # opacity ต่ำกว่านี้ถือว่ามองไม่เห็น
_RENDER_DPI = 36
_WHITE_THRESHOLD = 0.93


def _region_color(pix: fitz.Pixmap, rect: fitz.Rect, scale: float):
    """สีกลาง (median ต่อช่องสี) ของบริเวณ rect บนภาพที่เรนเดอร์ไว้ — 0..1"""
    x0 = max(0, int(rect.x0 * scale)); y0 = max(0, int(rect.y0 * scale))
    x1 = min(pix.width, int(rect.x1 * scale) + 1); y1 = min(pix.height, int(rect.y1 * scale) + 1)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    n = pix.n
    samples = pix.samples
    step = max(1, ((x1 - x0) * (y1 - y0)) // 400)  # สุ่มไม่เกิน ~400 จุด
    reds, greens, blues = [], [], []
    i = 0
    for y in range(y0, y1):
        row = y * pix.stride
        for x in range(x0, x1):
            if i % step == 0:
                o = row + x * n
                reds.append(samples[o]); greens.append(samples[o + 1]); blues.append(samples[o + 2])
            i += 1
    if not reds:
        return None
    med = lambda v: sorted(v)[len(v) // 2] / 255.0  # noqa: E731
    return (med(reds), med(greens), med(blues))


def sanitize_drawings(page: fitz.Page, raw_paths: list) -> list:
    """คืนรายการ drawing ที่ปรับสีตามความโปร่งใสแล้ว (ใช้แทนผลของ page.get_cdrawings())"""
    pix = None
    scale = _RENDER_DPI / 72.0
    result = []
    for path in raw_paths:
        fill = path.get("fill")
        opacity = path.get("fill_opacity", 1.0)
        if fill is None or opacity is None or opacity >= 0.999:
            result.append(path)
            continue
        path = dict(path)
        if opacity < _TRANSPARENT:
            if pix is None:
                pix = page.get_pixmap(dpi=_RENDER_DPI, alpha=False, annots=False)
            color = _region_color(pix, fitz.Rect(path["rect"]) & page.rect, scale)
            if color is None or min(color) >= _WHITE_THRESHOLD:
                if path.get("color") is None:
                    continue  # รูปทรงล่องหนบนพื้นขาว — ทิ้ง
                path["fill"] = None  # เหลือแค่เส้นขอบ
                path["type"] = "s"
            else:
                path["fill"] = color
                path["fill_opacity"] = 1.0
        else:
            path["fill"] = tuple(opacity * c + (1 - opacity) for c in fill)
            path["fill_opacity"] = 1.0
        result.append(path)
    return result


_WS = " \u00a0\t"


def phantom_space_flags(chars: list[dict]) -> list[bool]:
    """chars (rawdict ของแถวเดียว เรียงตามลำดับข้อความ) → True ที่ช่องว่าง "ปลอม" ที่วางซ้อนใต้ตัวอักษรก่อนหน้า

    PDF จาก Word มักมีช่องว่างที่ตำแหน่งซ้อนอยู่ใต้ตัวอักษรตัวก่อน (เช่น "หมายเหตุ:" ที่ PDF เก็บเป็น
    "หมายเหตุ" + " :") มองไม่เห็นใน PDF แต่ตัวแปลงใส่เป็นช่องว่างจริง → ใน Word กลายเป็น "หมายเหตุ :"
    ช่องว่างที่จุดกึ่งกลางอยู่ก่อนขอบขวาของตัวอักษรที่ผ่านมาในแถวเดียวกันจึงถือว่าไม่มีอยู่จริง
    """
    flags = []
    right = None      # ขอบขวาสุดของตัวอักษร (ไม่ใช่ช่องว่าง) ที่ผ่านมา
    for ch in chars:
        x0, x1 = ch["bbox"][0], ch["bbox"][2]
        if ch["c"] in _WS:
            flags.append(right is not None and (x0 + x1) / 2 < right - 0.3)
        else:
            right = x1 if right is None else max(right, x1)
            flags.append(False)
    return flags


def _same_row(a, b) -> bool:
    """กรอบ (x0, y0, x1, y1) สองกรอบอยู่แถวเดียวกัน (ซ้อนกันแนวตั้งอย่างน้อยครึ่งหนึ่งของกรอบที่เตี้ยกว่า)"""
    return min(a[3], b[3]) - max(a[1], b[1]) >= 0.5 * min(a[3] - a[1], b[3] - b[1])


def drop_overlapping_spaces(text_blocks: list) -> int:
    """ลบช่องว่างปลอม (ดู phantom_space_flags) ใน rawdict ของ PyMuPDF ในที่ คืนจำนวนที่ลบ

    ทำต่อแถว: บรรทัดของบล็อกเดียวกันที่อยู่แถวเดียวกัน (PyMuPDF มักแยก "หมายเหตุ" กับ " :" เป็นคนละบรรทัด)
    """
    removed = 0
    for block in text_blocks:
        row_lines, row_box = [], None

        def flush(row_lines):
            nonlocal removed
            items = [(span, ch) for ln in row_lines for span in ln.get("spans", []) for ch in (span.get("chars") or [])]
            drop = phantom_space_flags([ch for _, ch in items])
            gone = {id(ch) for (_, ch), d in zip(items, drop) if d}
            if not gone:
                return
            removed += len(gone)
            for ln in row_lines:
                for span in ln.get("spans", []):
                    if not span.get("chars"):
                        continue
                    keep = [c for c in span["chars"] if id(c) not in gone]
                    if len(keep) != len(span["chars"]):
                        span["chars"] = keep
                        if keep:
                            b = span["bbox"]
                            span["bbox"] = (min(c["bbox"][0] for c in keep), b[1], max(c["bbox"][2] for c in keep), b[3])
                ln["spans"] = [sp for sp in ln.get("spans", []) if sp.get("chars") is None or sp["chars"]]

        for line in block.get("lines", []):
            d = line.get("dir", (1, 0))
            horizontal = abs(d[1]) < 1e-3 and d[0] > 0
            if row_lines and horizontal and row_box is not None and _same_row(row_box, line["bbox"]):
                row_lines.append(line)
                continue
            flush(row_lines)
            row_lines, row_box = ([line], line["bbox"]) if horizontal else ([], None)
        flush(row_lines)
        block["lines"] = [ln for ln in block.get("lines", []) if ln.get("spans")]
    return removed


def _row_lines(shape, blocks) -> list:
    """บรรทัดข้อความแนวนอนที่อยู่แถวเดียวกับรูปทรง (ซ้อนกันแนวตั้งอย่างน้อยครึ่งหนึ่งของบรรทัดหรือของรูปทรง)"""
    sb = shape.bbox
    out = []
    for block in blocks:
        for line in (getattr(block, "lines", None) or [block]):
            lb = getattr(line, "bbox", None)
            if lb is None or not getattr(line, "is_horizontal_text", True):
                continue
            if lb.x1 < sb.x0 - 2 or lb.x0 > sb.x1 + 2:
                continue
            ov = min(lb.y1, sb.y1 + 2) - max(lb.y0, sb.y0 - 2)
            if ov >= 0.5 * min(lb.height, max(sb.height, 1.0)):
                out.append(line)
    return out


class _Union:
    """บรรทัดสมมุติที่ครอบหลายบรรทัด — ใช้แทน Line ตอนเรียก _semantic_type"""
    is_horizontal_text = True

    def __init__(self, lines):
        self.bbox = fitz.Rect(lines[0].bbox)
        for ln in lines[1:]:
            self.bbox |= ln.bbox


def _luminance(color) -> float:
    """สีแบบ int 0xRRGGBB (ของ pdf2docx) → ความสว่าง 0..1"""
    if not isinstance(color, int):
        return 1.0
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def refine_semantic_type(shape, blocks) -> None:
    """แก้การจัดประเภทเส้น/พื้นสีที่ pdf2docx ตัดสินจาก "บรรทัดแรกที่ชน" เพียงบรรทัดเดียว

    - เส้นใต้ที่ยาวคลุมข้อความสองบรรทัดย่อยในแถวเดียวกัน (เช่น "หมายเหตุ" + ":") ถูกนับเป็นเส้นขอบตาราง → เส้นใต้หาย
    - แถบไฮไลต์ที่คลุมทั้ง bullet และข้อความถูกนับเป็นพื้นเซลล์ตาราง → ใน Word เป็นสีทั้งเซลล์ ยาวเกินข้อความ
    วิธีแก้: ถ้าผลเดิมเป็นเส้นขอบ/พื้นเซลล์ ลองเทียบกับ "ทุกบรรทัดในแถวเดียวกันรวมกัน" อีกครั้ง
    """
    from pdf2docx.common.share import RectType
    from pdf2docx.shape.Shape import Fill, Stroke

    if isinstance(shape, Stroke):
        if shape._potential_type != RectType.BORDER.value or not shape.horizontal:
            return
        lines = [ln for ln in _row_lines(shape, blocks)
                 if ln.bbox.y0 - 1 <= shape.bbox.y0 and shape.bbox.y1 <= ln.bbox.y1 + 2]
        if len(lines) < 2:
            return
        lines.sort(key=lambda ln: ln.bbox.x0)
        h = max(ln.bbox.height for ln in lines)
        reach = lines[0].bbox.x1
        for ln in lines[1:]:          # ต้องเป็นข้อความต่อเนื่องกัน ไม่ใช่ข้อความคนละเซลล์ที่ห่างกัน
            if ln.bbox.x0 - reach > 0.5 * h:
                return
            reach = max(reach, ln.bbox.x1)
        t = shape._semantic_type(_Union(lines))
        if t != RectType.BORDER.value:
            shape._potential_type = t
    elif isinstance(shape, Fill):
        if not (shape._potential_type & RectType.SHADING.value):
            return
        if _luminance(shape.color) < 0.5:
            return            # พื้นสีเข้ม (เช่น กล่องดำปิดข้อมูล) — ไม่ใช่ปากกาไฮไลต์ คงเป็นพื้นตามเดิม
        lines = _row_lines(shape, blocks)
        if not lines:
            return
        h = max(ln.bbox.height for ln in lines)
        if shape.bbox.height > 1.6 * h or shape.bbox.width <= shape.bbox.height:
            return            # สูงเกินหนึ่งบรรทัด หรือเป็นแท่งแนวตั้ง — เป็นพื้นหลังจริง
        u = _Union(lines).bbox
        if shape.bbox.x0 >= u.x0 - 2 and shape.bbox.x1 <= u.x1 + 2:
            shape._potential_type = RectType.HIGHLIGHT.value


def text_block_parse_format(block, shapes) -> bool:
    """แทน TextBlock.parse_text_format ของ pdf2docx: ให้รูปทรงที่เป็นไฮไลต์/เส้นใต้/ขีดฆ่าแล้ว ใช้กับบล็อกถัดไปได้อีก

    ของเดิมให้รูปทรงหนึ่งใช้ได้กับบล็อกเดียว — แถบไฮไลต์ที่คลุมทั้ง bullet และข้อความ (คนละบล็อก/คนละเซลล์)
    จึงไปติดแค่ bullet ส่วนข้อความไม่มีไฮไลต์ การแบ่ง span ใช้เฉพาะอักขระที่อยู่ในรูปทรง จึงใช้ซ้ำได้ปลอดภัย
    รูปทรงที่ถูกตัดสินเป็นเส้นขอบ/พื้นตารางแล้วยังข้ามเหมือนเดิม
    """
    from pdf2docx.common.share import RectType

    reusable = (RectType.HYPERLINK, RectType.HIGHLIGHT, RectType.UNDERLINE, RectType.STRIKE)
    flag = False
    for shape in shapes:
        if shape.is_determined and not any(shape.equal_to_type(t) for t in reusable):
            continue
        if not block.bbox.intersects(shape.bbox):
            continue
        if block.lines.parse_text_format(shape):
            flag = True
    return flag


_BULLET_START = re.compile("^[\\s]*([\u2022\u25aa\u25cf\u25e6\u2023\u2043\u25a0\u25c6\u27a2\u2713\u2714\u2219\u00b7*\uf000-\uf0ff]|[-\u2013]\\s)")


_SECTION_START = re.compile(r"^\s*\d+(\.\d+)+\.?\s")   # เลขหัวข้อ เช่น "2.1.6 "


def _span_style(line, last: bool = False):
    """(ตัวหนา, ขนาด) ของ span ตัวแรก/ตัวสุดท้ายที่มีตัวอักษร — ใช้ดูว่าแถวถัดไปเป็นหัวข้อ (รูปแบบต่างจากเนื้อความ)"""
    spans = [sp for sp in line.spans if getattr(sp, "text", "").strip()]
    if not spans:
        return None
    sp = spans[-1] if last else spans[0]
    bold = bool(getattr(sp, "flags", 0) & 16) or "bold" in (getattr(sp, "font", "") or "").lower()
    return bold, round(getattr(sp, "size", 0))


def _row_text(lines) -> str:
    return "".join(ln.text for ln in lines)


def refine_line_breaks(lines_obj, bbox) -> int:
    """เติมการขึ้นบรรทัดที่ pdf2docx พลาด (หลัง Lines.parse_line_break เดิม) คืนจำนวนที่เติม

    pdf2docx วัด "ที่ว่างท้ายบรรทัด" เทียบกับความกว้างของบล็อกเอง — บล็อกที่บรรทัดยาวเท่ากันหมดจึงไม่ถูกตัด
    แม้ใน PDF จะเป็นคนละย่อหน้า ผลคือหัวข้อ/bullet ถัดไปต่อท้ายบรรทัดก่อนหน้าใน Word ขึ้นบรรทัดใหม่เมื่อ:
    - แถวถัดไปขึ้นต้นด้วย bullet (•, ▪, ฟอนต์ Symbol ฯลฯ)
    - แถวถัดไปเริ่มด้วย tab (เยื้องเข้า เช่น บรรทัดต่อของ bullet แบบ hanging indent) — tab กลางบรรทัดไม่มีความหมาย
    - แถวนี้จบก่อนขอบขวาของหน้า/ช่องตารางเกิน 15% แถวถัดไปเยื้องออกทางซ้าย และเป็นหัวข้อ (ขึ้นต้นด้วยเลขหัวข้อ
      หรือตัวหนา/ขนาดต่างจากท้ายแถวนี้) — ไม่ใช้แค่ "เยื้องออก" เพราะย่อหน้าที่เยื้องบรรทัดแรกก็เป็นแบบนั้น
    """
    block = lines_obj.parent
    if not block.is_horizontal_text:
        return 0
    rows = lines_obj.group_by_physical_rows()
    layout_width = bbox[2] - bbox[0]
    if layout_width <= 0:
        return 0
    added = 0
    for cur, nxt in itertools.pairwise(rows):
        end = cur[-1]
        if end.line_break:
            continue
        first = nxt[0]
        free = bbox[2] - max(ln.bbox[2] for ln in cur)
        outdent = min(ln.bbox[0] for ln in cur) - first.bbox[0]
        size = max((sp.size for ln in cur for sp in ln.spans if hasattr(sp, "size")), default=10)
        if (_BULLET_START.match(_row_text(nxt))
                or first.tab_stop
                or (free > 0.15 * layout_width and outdent > 0.5 * size
                    and (_SECTION_START.match(_row_text(nxt)) or _span_style(cur[-1], last=True) != _span_style(first)))):
            end.line_break = 1
            added += 1
    return added


def _char_in_rect(char, rect, horizontal: bool = True) -> bool:
    """แทน Char.contained_in_rect ของ pdf2docx: ตัดสินจากจุดกึ่งกลางตามแนวข้อความเท่านั้น

    ของเดิมต้องให้กล่องตัวอักษรอยู่ในรูปทรงทั้งกล่องหรือซ้อนเกินครึ่งความกว้าง — สระบน/วรรณยุกต์ไทย
    (กว้าง 0 และสูงพ้นแถบไฮไลต์) จึงไม่นับ และเพราะ pdf2docx นับจำนวนตัวที่อยู่ในรูปทรงแล้วตัดต่อเนื่อง
    จากตัวแรก ไฮไลต์/เส้นใต้จึงจบก่อนข้อความจริงเท่าจำนวนวรรณยุกต์ (เช่น "ปรับแก" ไฮไลต์ แต่ "้" ไม่)
    """
    b, r = char.bbox, rect.bbox
    if horizontal:
        c = (b.x0 + b.x1) / 2
        return r.x0 - 0.5 <= c <= r.x1 + 0.5
    c = (b.y0 + b.y1) / 2
    return r.y0 - 0.5 <= c <= r.y1 + 0.5


@contextlib.contextmanager
def patched_pdf2docx():
    """ใช้ครอบการเรียก Converter.convert() — ติดตั้งการแก้ทั้งหมดในไฟล์นี้เข้า pdf2docx ชั่วคราว"""
    from pdf2docx.page import RawPageFitz as module
    from pdf2docx.shape.Paths import Paths
    from pdf2docx.shape.Shape import Shape
    from pdf2docx.text.Char import Char
    from pdf2docx.text.TextBlock import TextBlock

    original = module.RawPageFitz._init_paths
    original_block_format = TextBlock.parse_text_format
    from pdf2docx.text.Lines import Lines
    original_line_break = Lines.parse_line_break
    original_text = module.RawPageFitz._preprocess_text
    original_semantic = Shape.parse_semantic_type
    original_contained = Char.contained_in_rect

    def _init_paths(self, **settings):
        try:
            raw = sanitize_drawings(self.page_engine, self.page_engine.get_cdrawings())
        except Exception:
            logger.warning("ปรับสีรูปทรงก่อนแปลงไม่สำเร็จ ใช้ข้อมูลเดิม", exc_info=True)
            raw = self.page_engine.get_cdrawings()
        return Paths(parent=self).restore(raw)

    def _preprocess_text(self, **settings):
        blocks = original_text(self, **settings)
        try:
            drop_overlapping_spaces(blocks)
        except Exception:
            logger.warning("ลบช่องว่างซ้อนไม่สำเร็จ", exc_info=True)
        return blocks

    def parse_line_break(self, bbox, line_break_width_ratio, line_break_free_space_ratio):
        original_line_break(self, bbox, line_break_width_ratio, line_break_free_space_ratio)
        try:
            refine_line_breaks(self, bbox)
        except Exception:
            logger.warning("ปรับการขึ้นบรรทัดไม่สำเร็จ", exc_info=True)

    def block_parse_text_format(self, shapes):
        return text_block_parse_format(self, shapes)

    def parse_semantic_type(self, blocks=None):
        original_semantic(self, blocks)
        try:
            refine_semantic_type(self, blocks or [])
        except Exception:
            logger.warning("ปรับประเภทรูปทรงไม่สำเร็จ", exc_info=True)

    module.RawPageFitz._init_paths = _init_paths
    module.RawPageFitz._preprocess_text = _preprocess_text
    TextBlock.parse_text_format = block_parse_text_format
    Lines.parse_line_break = parse_line_break
    Shape.parse_semantic_type = parse_semantic_type
    Char.contained_in_rect = _char_in_rect
    try:
        yield
    finally:
        module.RawPageFitz._init_paths = original
        module.RawPageFitz._preprocess_text = original_text
        Shape.parse_semantic_type = original_semantic
        Char.contained_in_rect = original_contained
        TextBlock.parse_text_format = original_block_format
        Lines.parse_line_break = original_line_break


# ---------- ปรับฟอนต์ใน DOCX ให้ Word แสดงภาษาไทยถูกต้อง ----------
# pdf2docx ใส่ชื่อฟอนต์ตามชื่อภายในไฟล์ PDF (เช่น "NotoSansThai", "ABCDEF+Sarabun-Bold") และตั้งแค่
# w:ascii/w:hAnsi + w:sz — แต่ Word แสดงอักษรไทยด้วยค่าของ "complex script" (w:cs, w:szCs, w:bCs) ซึ่ง
# pdf2docx ไม่ได้ตั้ง ผลคือข้อความไทยใช้ฟอนต์/ขนาดดีฟอลต์ (ตัวเล็กกว่าตัวเลข/ภาษาอังกฤษในบรรทัดเดียวกัน
# และหนาไม่ตรง) — ฟังก์ชันนี้ทำให้ทุก run ใช้ฟอนต์และขนาดเดียวกันทั้งอักษรละตินและไทย


# ฟอนต์ที่มีแต่อักษรไทย (ไม่มีตัวเลข/ละติน) — ต้องแยกฟอนต์ละตินเป็นอีกตัว ไม่งั้นตัวเลขหายเป็นช่องว่าง
_THAI_ONLY_FONTS = {
    "notosansthai": ("Noto Sans", "Noto Sans Thai"),
    "notosansthailooped": ("Noto Sans", "Noto Sans Thai Looped"),
    "notoserifthai": ("Noto Serif", "Noto Serif Thai"),
}
_KNOWN_FONTS = {
    "thsarabunnew": "TH Sarabun New",
    "thsarabunpsk": "TH SarabunPSK",
    "sarabun": "Sarabun",
    "kanit": "Kanit",
    "prompt": "Prompt",
    "mitr": "Mitr",
    "tahoma": "Tahoma",
    "angsananew": "Angsana New",
    "cordianew": "Cordia New",
    "browalliamew": "Browallia New",
    "leelawadee": "Leelawadee",
    "leelawadeeui": "Leelawadee UI",
}
_STYLE_SUFFIX = re.compile(r"[-,](bold|italic|regular|medium|semibold|light|black|thin|extrabold|bolditalic|mt|psmt)+$", re.I)


def normalize_font_name(name: str) -> tuple[str, str]:
    """ชื่อฟอนต์ภายใน PDF → (ฟอนต์สำหรับละติน/ตัวเลข, ฟอนต์สำหรับอักษรไทย) ที่ Word/ระบบรู้จัก"""
    if not name:
        return name, name
    base = name.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", name) else name
    base = _STYLE_SUFFIX.sub("", base)
    key = re.sub(r"[\s_-]", "", base).lower()
    if key in _THAI_ONLY_FONTS:
        return _THAI_ONLY_FONTS[key]
    if key in _KNOWN_FONTS:
        family = _KNOWN_FONTS[key]
    elif " " in base:
        family = base
    else:
        # CamelCase → คำแยก (เช่น "OpenSans" → "Open Sans") แต่คงตัวย่อพิมพ์ใหญ่ติดกันไว้
        family = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base)
    return family, family


def normalize_docx_fonts(document) -> int:
    """ตั้ง w:cs/w:szCs/w:bCs/w:iCs ให้ตรงกับค่าละตินของทุก run และแก้ชื่อฟอนต์ คืนจำนวน run ที่แก้"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    changed = 0
    for rpr in document.element.body.iter(qn("w:rPr")):
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is not None:
            name = fonts.get(qn("w:ascii")) or fonts.get(qn("w:hAnsi")) or fonts.get(qn("w:cs"))
            if name:
                latin, thai = normalize_font_name(name)
                for attr in ("w:ascii", "w:hAnsi", "w:eastAsia"):
                    fonts.set(qn(attr), latin)
                fonts.set(qn("w:cs"), thai)
        if fonts is not None and rpr.find(qn("w:lang")) is None:
            lang = OxmlElement("w:lang")
            lang.set(qn("w:bidi"), "th-TH")  # ให้ Word ตัดคำ/จัดบรรทัดภาษาไทยถูกต้อง
            rpr.append(lang)
        size = rpr.find(qn("w:sz"))
        if size is not None and rpr.find(qn("w:szCs")) is None:
            szcs = OxmlElement("w:szCs")
            szcs.set(qn("w:val"), size.get(qn("w:val")))
            size.addnext(szcs)
        for latin, cs in (("w:b", "w:bCs"), ("w:i", "w:iCs")):
            el = rpr.find(qn(latin))
            if el is not None and rpr.find(qn(cs)) is None:
                new = OxmlElement(cs)
                if el.get(qn("w:val")) is not None:
                    new.set(qn("w:val"), el.get(qn("w:val")))
                el.addnext(new)
        changed += 1
    return changed


# ---------- อักขระสัญลักษณ์ในพื้นที่ส่วนตัว (Private Use Area) ----------
# Word เก็บ bullet ของฟอนต์ Symbol/Wingdings เป็นรหัส U+F0xx (เช่น U+F0B7 = Symbol 0xB7) ซึ่งแสดงถูกเฉพาะเมื่อ
# เครื่องมีฟอนต์นั้น — PDF จาก LibreOffice ใช้ฟอนต์ "OpenSymbol" ที่ Mac/Windows ส่วนใหญ่ไม่มี ผลคือ bullet
# ใน Word เป็น "?" หรือกล่องว่าง จึงแปลงเป็นอักขระ Unicode มาตรฐานแล้วใช้ฟอนต์ทั่วไป
_SYMBOL_PUA = {   # Symbol / OpenSymbol
    0xB7: "\u2022", 0xD7: "\u22c5", 0xA8: "\u2666", 0xA7: "\u2663", 0xA9: "\u2665", 0xAA: "\u2660",
    0xAE: "\u2192", 0xDE: "\u21d2", 0xB0: "\u00b0", 0xB4: "\u00d7", 0x2D: "\u2212", 0x6F: "\u25cb",
}
_WINGDINGS_PUA = {
    0xA7: "\u25aa", 0x6C: "\u25cf", 0x6E: "\u25a0", 0x71: "\u2751", 0x75: "\u25c6", 0x76: "\u2756",
    0xA8: "\u25fb", 0xD8: "\u27a2", 0xFC: "\u2713", 0xFB: "\u2717", 0xFE: "\u2611", 0x9F: "\u2022",
    0xA1: "\u25cb", 0xE0: "\u2794", 0xE8: "\u2794", 0x77: "\u2b25",
}
_SYMBOL_FONT = "Arial"


def _pua_table(font: str) -> dict | None:
    key = re.sub(r"[\s_-]", "", font or "").lower()
    if "wingding" in key:
        return _WINGDINGS_PUA
    if "symbol" in key:      # Symbol, OpenSymbol, StarSymbol
        return _SYMBOL_PUA
    return None


def fix_symbol_chars(document) -> int:
    """แปลง bullet/สัญลักษณ์รหัส U+F0xx ของฟอนต์ Symbol/Wingdings เป็น Unicode มาตรฐาน คืนจำนวน run ที่แก้"""
    from docx.oxml.ns import qn

    changed = 0
    for run in document.element.body.iter(qn("w:r")):
        texts = [t for t in run.iter(qn("w:t")) if t.text and any(0xF000 <= ord(c) <= 0xF0FF for c in t.text)]
        if not texts:
            continue
        rpr = run.find(qn("w:rPr"))
        fonts = rpr.find(qn("w:rFonts")) if rpr is not None else None
        name = "" if fonts is None else (fonts.get(qn("w:ascii")) or fonts.get(qn("w:hAnsi")) or fonts.get(qn("w:cs")) or "")
        table = _pua_table(name)
        hit = False
        for t in texts:
            out = []
            for c in t.text:
                o = ord(c)
                if 0xF000 <= o <= 0xF0FF:
                    rep = (table or {}).get(o - 0xF000)
                    if rep is None and o == 0xF0B7:   # bullet ที่พบบ่อยที่สุด แม้ไม่รู้ชื่อฟอนต์
                        rep = "\u2022"
                    if rep is not None:
                        out.append(rep)
                        hit = True
                        continue
                out.append(c)
            t.text = "".join(out)
        if hit:
            if fonts is not None and table is not None:
                for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                    fonts.set(qn(attr), _SYMBOL_FONT)
            changed += 1
    return changed


# ---------- หัวข้อที่ติดอยู่ในย่อหน้าก่อนหน้า ----------
def _run_bold(r) -> bool:
    from docx.oxml.ns import qn

    rpr = r.find(qn("w:rPr"))
    b = rpr.find(qn("w:b")) if rpr is not None else None
    return b is not None and b.get(qn("w:val"), "1") not in ("0", "false")


def split_heading_paragraphs(document) -> int:
    """แยกหัวข้อ (ตัวหนา ขึ้นต้นด้วยเลขหัวข้อ เช่น "2.1.6 ...") ที่ pdf2docx รวมไว้ในย่อหน้าเดียวกับข้อความก่อน/หลัง
    (คั่นด้วยการขึ้นบรรทัด w:br) ออกเป็นย่อหน้าของตัวเอง — หัวข้อจึงมีระยะห่างและเลือก style หัวข้อใน Word ได้
    คืนจำนวนย่อหน้าที่แยกเพิ่ม
    """
    import copy

    from docx.oxml.ns import qn

    def text_of(runs):
        return "".join(t.text or "" for r in runs for t in r.iter(qn("w:t"))).replace("\u200b", "")

    added = 0
    for p in list(document.element.body.iter(qn("w:p"))):
        runs = [r for r in p if r.tag == qn("w:r")]
        if len(runs) != len([c for c in p if c.tag not in (qn("w:pPr"),)]):
            continue          # มี hyperlink/field ฯลฯ ปนอยู่ — ไม่แตะ
        # แบ่ง run เป็นบรรทัดตาม w:br (run ที่มี br ปิดท้ายบรรทัดนั้น)
        lines, cur = [], []
        for r in runs:
            cur.append(r)
            if r.find(qn("w:br")) is not None:
                lines.append(cur)
                cur = []
        if cur:
            lines.append(cur)
        if len(lines) < 2:
            continue
        heading = []
        for line in lines:
            body = [r for r in line if text_of([r]).strip()]
            heading.append(bool(body) and _SECTION_START.match(text_of(line)) is not None and all(_run_bold(r) for r in body))
        if not any(heading):
            continue
        # จุดตัด: ก่อนและหลังทุกบรรทัดหัวข้อ
        cuts = set()
        for i, h in enumerate(heading):
            if h:
                if i > 0:
                    cuts.add(i)
                if i + 1 < len(lines):
                    cuts.add(i + 1)
        groups, start = [], 0
        for i in sorted(cuts):
            groups.append((lines[start:i], heading[start]))
            start = i
        groups.append((lines[start:], heading[start]))
        anchor = p
        for gi, (glines, is_head) in enumerate(groups):
            target = p if gi == 0 else copy.deepcopy(p)
            if gi > 0:
                for child in list(target):
                    if child.tag != qn("w:pPr"):
                        target.remove(child)
                anchor.addnext(target)
                anchor = target
                added += 1
            grun = [r for line in glines for r in line]
            # br ที่ปิดท้ายกลุ่มไม่ต้องมีแล้ว (ขึ้นย่อหน้าใหม่แทน)
            last = grun[-1]
            br = last.find(qn("w:br"))
            if br is not None and gi < len(groups) - 1:
                last.remove(br)
            for r in grun:
                if r.getparent() is not target:
                    target.append(r)
            tppr = target.find(qn("w:pPr"))
            if tppr is not None and gi > 0:
                ind = tppr.find(qn("w:ind"))
                if ind is not None:
                    for a in ("w:firstLine", "w:hanging"):
                        if ind.get(qn(a)) is not None:
                            ind.set(qn(a), "0")
                if is_head:
                    sp = tppr.find(qn("w:spacing"))
                    if sp is not None:
                        sp.set(qn("w:before"), "120")
    return added


# ---------- ตาราง: ความกว้างคอลัมน์ ----------
def fix_table_grids(document) -> int:
    """ตั้ง w:tblGrid ให้ตรงกับความกว้างช่องจริง (w:tcW) และปัดค่าทศนิยมในตารางเป็นจำนวนเต็ม คืนจำนวนตารางที่แก้

    pdf2docx ใส่ความกว้างไว้ที่แต่ละช่อง (tcW) แต่ tblGrid เป็นค่าเท่ากันทุกคอลัมน์ (ค่าเริ่มต้นของ python-docx)
    ตารางแบบ fixed layout จึงถูกจัดตาม grid ในบางโปรแกรม (LibreOffice ฯลฯ) — คอลัมน์แรกที่ควรกว้างกลับแคบเท่าคอลัมน์อื่น
    ค่าอย่าง w:tblInd="10.0" หรือเส้นขอบ w:sz="4.0" ผิดสเปก (ต้องเป็นจำนวนเต็ม) ก็ปัดให้ด้วย
    """
    from docx.oxml.ns import qn

    fixed = 0
    for tbl in document.element.body.iter(qn("w:tbl")):
        changed = False
        for el in tbl.iter():
            for attr in (qn("w:w"), qn("w:sz")):
                v = el.get(attr)
                if v and "." in v:
                    try:
                        el.set(attr, str(int(round(float(v)))))
                        changed = True
                    except ValueError:
                        pass
        grid = tbl.find(qn("w:tblGrid"))
        cols = grid.findall(qn("w:gridCol")) if grid is not None else []
        if cols:
            widths: list = [None] * len(cols)
            for tr in tbl.findall(qn("w:tr")):
                idx = 0
                for tc in tr.findall(qn("w:tc")):
                    tcpr = tc.find(qn("w:tcPr"))
                    span_el = tcpr.find(qn("w:gridSpan")) if tcpr is not None else None
                    span = int(span_el.get(qn("w:val"), "1")) if span_el is not None else 1
                    tcw = tcpr.find(qn("w:tcW")) if tcpr is not None else None
                    w = tcw.get(qn("w:w")) if tcw is not None and tcw.get(qn("w:type"), "dxa") == "dxa" else None
                    if span == 1 and idx < len(widths) and widths[idx] is None and w and w.isdigit() and int(w) > 0:
                        widths[idx] = int(w)
                    idx += span
            for col, w in zip(cols, widths):
                if w is not None and col.get(qn("w:w")) != str(w):
                    col.set(qn("w:w"), str(w))
                    changed = True
        fixed += changed
    return fixed


_BREAK_TAGS = ("tab", "br", "cr", "ptab")


def paragraph_text_groups(paragraph) -> list[list]:
    """โหนด w:t ของย่อหน้า แบ่งเป็นกลุ่มตาม tab/ขึ้นบรรทัด (ข้อความคนละช่วงที่ไม่ควรจัดรูป/ตัดคำข้ามกัน)
    ข้าม run ที่เป็นรูปภาพ/กล่องข้อความ (ย่อหน้าซ้อนข้างในเป็นอีกย่อหน้า)"""
    from docx.oxml.ns import qn

    p = paragraph._p if hasattr(paragraph, "_p") else paragraph
    runs = p.xpath("./w:r | ./w:hyperlink/w:r | ./w:ins/w:r | ./w:smartTag/w:r | ./w:fldSimple/w:r")
    groups: list[list] = [[]]
    for r in runs:
        if r.find(qn("w:drawing")) is not None or r.find(qn("w:pict")) is not None:
            continue
        for child in r:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "t":
                groups[-1].append(child)
            elif tag in _BREAK_TAGS and groups[-1]:
                groups.append([])
    return [g for g in groups if g]


def replace_group_text(nodes: list, new_text: str) -> None:
    """แทนข้อความของกลุ่มโหนด w:t (ต่อกันเป็นสายเดียว) ด้วย new_text โดย "คงรูปแบบของแต่ละ run":
    จับคู่อักขระเดิมกับใหม่ (difflib) แล้วใส่อักขระใหม่กลับเข้าโหนดของอักขระเดิมที่ตรงกัน — ส่วนที่แทรกเพิ่ม
    (ZWSP, ำ ที่ประกอบใหม่) ติดไปกับอักขระก่อนหน้า · ส่วนที่ถูกแทนที่กระจายตามสัดส่วน

    เดิม (set_paragraph_text) ย้ายข้อความทั้งย่อหน้าไปไว้ใน run แรก — คำที่เป็นตัวหนา/สีต่างกันกลายเป็นแบบเดียว
    และข้อความไปกองอยู่ก่อน run ที่ขึ้นบรรทัด/tab ทำให้ลำดับบรรทัดเพี้ยน"""
    from difflib import SequenceMatcher

    old = "".join(n.text or "" for n in nodes)
    if old == new_text or not nodes:
        return
    owner = [k for k, n in enumerate(nodes) for _ in (n.text or "")]
    buckets: list[list[str]] = [[] for _ in nodes]

    def node_of(i: int) -> int:
        return owner[min(max(i, 0), len(owner) - 1)] if owner else 0

    for op, i1, i2, j1, j2 in SequenceMatcher(None, old, new_text, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                buckets[owner[i1 + k]].append(new_text[j1 + k])
        elif op in ("replace", "insert"):
            for j in range(j1, j2):
                src = i1 + (j - j1) * (i2 - i1) // (j2 - j1) if i2 > i1 else i1 - 1
                buckets[node_of(src)].append(new_text[j])
    for n, chars in zip(nodes, buckets):
        n.text = "".join(chars)
        if n.text != n.text.strip():
            n.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


# ---------- ข้อความสีอ่อนที่สูญเสียพื้นหลัง ----------
# หัวข้อแบบ "ตัวอักษรสีขาวบนแถบสี" บางจุด pdf2docx จับแถบสีไม่ได้ (แต่จับข้อความได้) ผลคือข้อความสีขาวบน
# พื้นขาว มองไม่เห็นใน Word — เก็บสีพื้นหลังจริงของข้อความสีอ่อนจาก PDF ต้นฉบับ แล้วใส่เป็นพื้นหลัง
# ย่อหน้าให้ ถ้าย่อหน้านั้นยังไม่มีพื้นหลังที่เข้มพอ

_ZW = dict.fromkeys(map(ord, "​‌‍﻿ \t"), None)


def _norm_text(text: str) -> str:
    return (text or "").translate(_ZW)


def _is_light(rgb) -> bool:
    return min(rgb) >= 0.85


def collect_light_text_backgrounds(pdf_path: str) -> dict[str, str]:
    """{ข้อความ (ตัดช่องว่าง) : สีพื้นหลัง hex} ของบรรทัดที่ตัวอักษรสีอ่อนและพื้นหลังเข้ม"""
    result: dict[str, str] = {}
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = None
            scale = _RENDER_DPI / 72.0
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                    if not spans:
                        continue
                    color = spans[0].get("color", 0)
                    rgb = ((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255
                    if not _is_light(rgb):
                        continue
                    if pix is None:
                        pix = page.get_pixmap(dpi=_RENDER_DPI, alpha=False, annots=False)
                    bg = _region_color(pix, fitz.Rect(line["bbox"]) & page.rect, scale)
                    if bg is None or _is_light(bg):
                        continue
                    key = _norm_text("".join(s["text"] for s in spans))
                    result[key] = "{:02X}{:02X}{:02X}".format(*(int(round(c * 255)) for c in bg))
    return result


def _has_dark_background(paragraph) -> bool:
    from docx.oxml.ns import qn

    el = paragraph._p
    while el is not None:
        if el.tag in (qn("w:p"), qn("w:tc")):
            props = el.find(qn("w:pPr") if el.tag == qn("w:p") else qn("w:tcPr"))
            shd = props.find(qn("w:shd")) if props is not None else None
            fill = (shd.get(qn("w:fill")) or "").lower() if shd is not None else ""
            if fill and fill not in ("auto", "ffffff"):
                r, g, b = (int(fill[i:i + 2], 16) / 255 for i in (0, 2, 4))
                if not _is_light((r, g, b)):
                    return True
        el = el.getparent()
    return False


def restore_light_text_backgrounds(document, backgrounds: dict[str, str]) -> int:
    """ใส่พื้นหลังให้ย่อหน้าข้อความสีอ่อนที่ตรงกับ backgrounds และยังไม่มีพื้นหลังเข้ม คืนจำนวนที่แก้"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    if not backgrounds:
        return 0
    fixed = 0
    for paragraph in document.element.body.iter(qn("w:p")):
        from docx.text.paragraph import Paragraph

        p = Paragraph(paragraph, None)
        key = _norm_text(p.text)
        if not key:
            continue
        fill = backgrounds.get(key)
        if fill is None:
            # ข้อความใน PDF อาจถูกแบ่งเป็นหลายบรรทัด/รวมกัน — ลองจับแบบขึ้นต้นตรงกัน
            fill = next((v for k, v in backgrounds.items() if len(k) >= 6 and (key.startswith(k) or k.startswith(key))), None)
        if fill is None or _has_dark_background(p):
            continue
        ppr = paragraph.get_or_add_pPr()
        shd = ppr.find(qn("w:shd"))
        if shd is None:
            shd = OxmlElement("w:shd")
            ppr.append(shd)
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        fixed += 1
    return fixed


# ---------------------------------------------------------------------------
# หน้าที่ถูกหมุน (/Rotate) — pdf2docx สร้างหน้าแนวนอน + ข้อความแนวตั้ง (textDirection btLr) ที่อ่าน/แก้ยาก
# และมักล้นไปอีกหน้า (ผู้ใช้เจอกับไฟล์ที่กดหมุนหน้าใน Editor แล้วค่อยแปลง) — ก่อนแปลงจึงเลือกทิศที่ทำให้
# ข้อความ "อ่านจากซ้ายไปขวาแนวนอน" มากที่สุดต่อหน้า:
#   - เนื้อหาเดิมตั้งตรงอยู่แล้ว แค่ถูกหมุนทีหลัง → ตั้ง /Rotate กลับเป็น 0 (ได้หน้าแนวตั้งตามต้นฉบับ)
#   - เนื้อหาเดิมวาดตะแคง และ /Rotate คือสิ่งที่ทำให้อ่านได้ (เช่น ตารางแนวนอน) → อบการหมุนลงเนื้อหา
#     (remove_rotation) ได้หน้าแนวนอนที่ข้อความตั้งตรง
# ---------------------------------------------------------------------------

def _ltr_text_share(page: fitz.Page) -> float:
    """สัดส่วนตัวอักษรที่อยู่ในบรรทัดแนวนอนซ้าย→ขวา (0 ถ้าหน้าไม่มีข้อความ)"""
    total = horizontal = 0
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            n = sum(len(span.get("text", "").strip()) for span in line.get("spans", []))
            total += n
            if line.get("dir", (1, 0))[0] > 0.9:
                horizontal += n
    return horizontal / total if total else 0.0


def _page_variant(doc: fitz.Document, page_number: int, upright: bool) -> fitz.Document:
    tmp = fitz.open()
    tmp.insert_pdf(doc, from_page=page_number, to_page=page_number)
    if upright:
        tmp[0].set_rotation(0)
    else:
        tmp[0].remove_rotation()
    return tmp


def upright_rotated_pages(pdf_bytes: bytes) -> bytes:
    """คืน PDF ที่ทุกหน้าไม่มี /Rotate โดยเลือกทิศที่ข้อความอ่านแนวนอนได้ (ไม่มีหน้าหมุน → คืนไบต์เดิม)"""
    try:
        with fitz.open("pdf", pdf_bytes) as doc:
            if doc.needs_pass or not any(page.rotation for page in doc):
                return pdf_bytes
            for page in doc:
                if not page.rotation:
                    continue
                with _page_variant(doc, page.number, upright=True) as plain, \
                        _page_variant(doc, page.number, upright=False) as baked:
                    keep_upright = _ltr_text_share(plain[0]) >= _ltr_text_share(baked[0])
                if keep_upright:
                    page.set_rotation(0)
                else:
                    page.remove_rotation()
            return doc.tobytes(garbage=1, deflate=True)
    except Exception:  # กันการแปลงทั้งไฟล์ล้มเพราะขั้นตอนเสริมนี้
        logger.warning("ปรับทิศหน้าที่หมุนก่อนแปลงไม่สำเร็จ — ใช้ไฟล์เดิม", exc_info=True)
        return pdf_bytes
