"""แก้ไขโครงตาราง (v1.40.0, ผู้ใช้ขอ 2026-11-20): ย้ายตาราง · ย่อขยายทั้งตาราง · ความกว้างคอลัมน์ · ความสูงแถว

PDF ไม่มีวัตถุ "ตาราง" — มีแค่เส้น/สี่เหลี่ยมพื้น + ข้อความวางตามพิกัด จึงทำแบบ "ตรวจหา แล้ววาดใหม่":
1. ตรวจหาตารางที่มีเส้นด้วย ``page.find_tables()`` → เส้นแบ่งคอลัมน์ ``xs`` / แถว ``ys`` + เซลล์ (รวมเซลล์ผสาน)
2. ผู้ใช้ส่งตำแหน่งเส้นใหม่ ``xs_new``/``ys_new`` (จำนวนเท่าเดิม) — ย้ายทั้งตาราง = เลื่อนทุกเส้นเท่ากัน
3. วาดใหม่ (``rebuild_table``):
   - เส้น/พื้นสีทุกชิ้นในกรอบตาราง แปลงพิกัดแบบ piecewise-linear (เส้นที่ x = xs[i] ไปอยู่ที่ xs_new[i]) แล้ววาดใหม่ด้วย
     สี/ความหนา/เส้นประเดิม → เส้นที่มีอยู่จริงเท่านั้นถูกวาด (ตารางที่มีแต่เส้นแนวนอนก็ยังเหมือนเดิม)
   - เนื้อหาแต่ละเซลล์: หน้าสำเนาที่ **ตัดทุกอย่างนอกเซลล์ออก** (redact) แล้ว ``show_pdf_page`` ไปวางที่เซลล์ใหม่
     ขนาดเท่าเดิม จัดชิดซ้าย/กลาง/ขวา และบน/กลาง/ล่าง ตามตำแหน่งเดิมในเซลล์ → ยังเป็นเวกเตอร์ ค้นหา/คัดลอก/แก้ข้อความได้
     (ใช้ทั้งหน้าเป็นต้นทางเดียวไม่ได้: ข้อความทั้งหน้าจะอยู่ซ้ำใน XObject ของทุกเซลล์ แม้มองเห็นแค่ส่วนที่ clip —
     ค้นหา/คัดลอก/แก้ข้อความเพี้ยน · ทดลอง ke2: 3,537 กล่องข้อความแทน 78)
   - เซลล์ข้อความที่แคบกว่าเนื้อหา → **ตัดบรรทัดใหม่** (ผู้ใช้เลือก) ด้วยระบบแก้ข้อความเดิม (``replace_text`` โหมดแทรก —
     ฟอนต์อาจเปลี่ยนเป็นฟอนต์ระบบที่ใกล้เคียง) และแถวสูงขึ้นอัตโนมัติให้พอ · เซลล์ที่มีรูป → ย่อทั้งเซลล์ตามสัดส่วน
   - แถวที่เตี้ยกว่าเนื้อหาเดิม → ขยายให้พอ (คืน ``adjusted_rows`` ให้หน้าเว็บบอกผู้ใช้)
4. ลบของเดิมในกรอบตาราง: redaction ข้อความ + พิกเซลรูป + เส้น (``REMOVE_IF_TOUCHED`` — ``COVERED`` ทิ้งเส้นไว้ 57 จาก 86 เส้น
   ในไฟล์ทดสอบ) · รูปทรงที่แค่แตะขอบตารางแต่ยื่นออกไปนอกตาราง ถูกวาดคืนตามเดิม

ข้อจำกัด: ตารางต้องมีเส้น (``find_tables`` แบบ lines) · แก้ทีละหน้า · ไฟล์สแกน (ตารางเป็นภาพ) ไม่รองรับ
"""
from __future__ import annotations

import bisect
import re
import uuid

import fitz

from app.core.session import PDFSession
from app.services import font_inspect, fonts
from app.services.pdf_service import PDFError, require_unlocked

MIN_CELL_PT = 6.0


class TableOverlapError(PDFError):
    """ตารางใหม่จะทับข้อความอื่นในหน้า — หน้าเว็บถามยืนยันแล้วส่ง allow_overlap=True มาใหม่"""
_CLUSTER_PT = 1.5
_MATCH_PT = 3.0


# ---------- ตรวจหาตาราง ----------

def _cluster(values: list[float]) -> list[float]:
    out: list[list[float]] = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= _CLUSTER_PT:
            out[-1].append(v)
        else:
            out.append([v])
    return [round(sum(g) / len(g), 2) for g in out]


def _index(edges: list[float], v: float) -> int:
    return min(range(len(edges)), key=lambda i: abs(edges[i] - v))


def _content_page(page: fitz.Page) -> fitz.Page:
    from app.services.pdf_service.text_index import content_page

    return content_page(page)


def find_tables(page: fitz.Page) -> list[dict]:
    """ตารางที่มีเส้นในหน้า → [{id, bbox, xs, ys, cells:[{r, c, rowspan, colspan}]}] (พิกัด pt ของหน้า)"""
    out = []
    for t in _content_page(page).find_tables().tables:
        rects = [fitz.Rect(c) for c in t.cells if c]
        if not rects:
            continue
        xs = _cluster([r.x0 for r in rects] + [r.x1 for r in rects])
        ys = _cluster([r.y0 for r in rects] + [r.y1 for r in rects])
        if len(xs) < 2 or len(ys) < 2 or (len(xs) - 1) * (len(ys) - 1) < 2:
            continue
        cells, seen = [], set()
        for r in rects:
            c0, c1 = _index(xs, r.x0), _index(xs, r.x1)
            r0, r1 = _index(ys, r.y0), _index(ys, r.y1)
            if c1 <= c0 or r1 <= r0 or (r0, c0) in seen:
                continue
            seen.add((r0, c0))
            cells.append({"r": r0, "c": c0, "rowspan": r1 - r0, "colspan": c1 - c0})
        cells.sort(key=lambda c: (c["r"], c["c"]))
        out.append({
            "id": f"t{len(out)}",
            "bbox": {"x0": xs[0], "y0": ys[0], "x1": xs[-1], "y1": ys[-1]},
            "xs": xs,
            "ys": ys,
            "cells": cells,
        })
    return out


def _registered(session: PDFSession, page_number: int) -> list[dict]:
    """ตารางที่วาดใหม่ไปแล้วในเซสชันนี้ — เก็บในทะเบียน text_edits (kind "table") ซึ่งย้อนตาม undo/redo และเลื่อนตาม
    การแทรก/ลบ/ย้ายหน้าอยู่แล้ว · ใช้แทนการตรวจหาซ้ำ: เนื้อหาเซลล์ที่ย้ายด้วย show_pdf_page มีเศษรูปทรงที่มองไม่เห็น
    (เช่น แท่งบาร์โค้ดกว้าง 0) ที่ find_tables นับเป็นเส้น → ได้ตารางเพี้ยน"""
    out = []
    for key, rec in session.text_edits.get(page_number, {}).items():
        if rec.get("kind") == "table":
            xs, ys = rec["xs"], rec["ys"]
            out.append({"id": key, "bbox": {"x0": xs[0], "y0": ys[0], "x1": xs[-1], "y1": ys[-1]},
                        "xs": list(xs), "ys": list(ys), "cells": [dict(c) for c in rec["cells"]]})
    return out


def _overlap(a: dict, b: dict) -> bool:
    return min(a["x1"], b["x1"]) > max(a["x0"], b["x0"]) and min(a["y1"], b["y1"]) > max(a["y0"], b["y0"])


def page_tables(session: PDFSession, page: fitz.Page) -> list[dict]:
    known = _registered(session, page.number)
    found = [t for t in find_tables(page) if not any(_overlap(t["bbox"], k["bbox"]) for k in known)]
    for i, t in enumerate(found):
        t["id"] = f"t{i}"
    return known + found


def get_tables(session: PDFSession, page_number: int) -> list[dict]:
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    return page_tables(session, doc[page_number])


# ---------- แปลงพิกัด ----------

def _mapper(old: list[float], new: list[float]):
    """piecewise-linear: old[i] → new[i] · นอกช่วงเลื่อนตามเส้นปลาย"""
    def f(v: float) -> float:
        if v <= old[0]:
            return new[0] + (v - old[0])
        if v >= old[-1]:
            return new[-1] + (v - old[-1])
        i = bisect.bisect_right(old, v) - 1
        span = old[i + 1] - old[i]
        t = (v - old[i]) / span if span else 0.0
        return new[i] + t * (new[i + 1] - new[i])
    return f


def _redraw(page: fitz.Page, paths: list[dict], fx=None, fy=None) -> None:
    """วาดรูปทรงจาก ``get_drawings()`` ใหม่ (ถ้ามี fx/fy = แปลงพิกัดแต่ละจุด) ด้วยสี/ความหนา/เส้นประเดิม"""
    def pt(p):
        return fitz.Point(fx(p.x) if fx else p.x, fy(p.y) if fy else p.y)

    for path in paths:
        shape = page.new_shape()
        for item in path["items"]:
            kind = item[0]
            if kind == "l":
                shape.draw_line(pt(item[1]), pt(item[2]))
            elif kind == "c":
                shape.draw_bezier(pt(item[1]), pt(item[2]), pt(item[3]), pt(item[4]))
            elif kind == "re":
                r = fitz.Rect(item[1])
                shape.draw_rect(fitz.Rect(pt(r.tl), pt(r.br)))
            elif kind == "qu":
                q = item[1]
                shape.draw_quad(fitz.Quad(pt(q.ul), pt(q.ur), pt(q.ll), pt(q.lr)))
        stroke = path.get("type") in ("s", "fs")
        fill = path.get("type") in ("f", "fs")
        line_cap = path.get("lineCap") or (0,)
        shape.finish(
            color=path.get("color") if stroke else None,
            fill=path.get("fill") if fill else None,
            width=(path.get("width") or 1) if stroke else 0,
            dashes=path.get("dashes") or None,
            even_odd=bool(path.get("even_odd")),
            closePath=bool(path.get("closePath")),
            lineCap=max(line_cap) if isinstance(line_cap, (tuple, list)) else int(line_cap or 0),
            lineJoin=int(path.get("lineJoin") or 0),
            fill_opacity=path.get("fill_opacity") if path.get("fill_opacity") is not None else 1,
            stroke_opacity=path.get("stroke_opacity") if path.get("stroke_opacity") is not None else 1,
        )
        shape.commit()


# ---------- เนื้อหาเซลล์ ----------

_NUM = rb"[-+]?(?:\d+\.?\d*|\.\d+)"
_DEGENERATE_RE = re.compile(rb"(?<![\w.])" + _NUM + rb"\s+" + _NUM + rb"\s+(" + _NUM + rb")\s+(" + _NUM + rb")\s+re\b")


def _drop_degenerate_rects(doc: fitz.Document, page: fitz.Page) -> None:
    """ลบสี่เหลี่ยมกว้าง/สูง 0 (``x y 0 h re``) ออกจาก content stream ของหน้าและฟอร์มในหน้า — วาดแล้วไม่เห็นอะไร
    แต่ redaction ลบไม่ได้ (พื้นที่ตัดกันเป็น 0) จึงติดไปทุกเซลล์ และพอวาดซ้อนหลายรอบ MuPDF แสดงเป็นเส้นบาง ๆ
    (เจอจากแท่งบาร์โค้ดกว้าง 0 ในไฟล์ทดสอบ)"""
    def clean(match: re.Match) -> bytes:
        w, h = float(match.group(1)), float(match.group(2))
        return b"" if w == 0 or h == 0 else match.group(0)

    xrefs = list(page.get_contents()) + [x[0] for x in page.get_xobjects()]
    for xref in xrefs:
        try:
            data = doc.xref_stream(xref)
        except Exception:  # noqa: BLE001 — ไม่ใช่ stream (เช่น รูป) ข้าม
            continue
        if not data or b" re" not in data:
            continue
        new = _DEGENERATE_RE.sub(clean, data)
        if new != data:
            doc.update_stream(xref, new)

def _cell_content(page: fitz.Page, rect: fitz.Rect) -> dict:
    """เนื้อหาในเซลล์ (หน้าสำเนาที่ตัดนอกเซลล์ออกแล้ว): กรอบรวม, ข้อความ, span สำหรับสรุปฟอนต์, มีรูปไหม"""
    raw = page.get_text("dict", clip=rect)
    bbox = fitz.Rect()
    lines, span_chars = [], []
    for block in raw.get("blocks", []):
        if block.get("type") == 1:
            bbox |= fitz.Rect(block["bbox"]) & rect
            continue
        for line in block.get("lines", []):
            text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not text:
                continue
            lines.append(text)
            for s in line.get("spans", []):
                if s.get("text", "").strip():
                    bbox |= fitz.Rect(s["bbox"]) & rect
                    span_chars.append((s, len(s["text"].strip())))
    has_image = any(fitz.Rect(i["bbox"]).intersects(rect) for i in page.get_image_info())
    drawings = [d for d in page.get_drawings() if fitz.Rect(d["rect"]).intersects(rect)]
    for d in drawings:  # ไอคอน/เส้นเล็ก ๆ ในเซลล์ (เส้นตารางถูกลบไปแล้ว) — ถือเป็นเนื้อหาที่ตัดบรรทัดไม่ได้
        bbox |= fitz.Rect(d["rect"]) & rect
    return {"bbox": bbox, "lines": lines, "span_chars": span_chars,
            "text_only": bool(lines) and not has_image and not drawings}


def _join_lines(lines: list[str]) -> str:
    """บรรทัดในเซลล์ → ย่อหน้าเดียว: ไทยต่อกันเลย (ตัดบรรทัดตรงขอบคำอยู่แล้ว) อังกฤษ/ตัวเลขคั่นด้วยช่องว่าง"""
    out = ""
    for line in lines:
        if out and (out[-1].isascii() and out[-1].isalnum()) and (line[0].isascii() and line[0].isalnum()):
            out += " "
        out += line
    return out


def _align(gap_a: float, gap_b: float, size: float) -> str:
    if abs(gap_a - gap_b) <= max(2.0, 0.15 * size):
        return "center"
    return "start" if gap_a < gap_b else "end"


def _place(start: float, end: float, length: float, gap_a: float, gap_b: float, mode: str) -> float:
    room = (end - start) - length
    if mode == "center":
        return start + room / 2
    if mode == "start":
        return start + max(0.0, min(gap_a, room))
    return end - length - max(0.0, min(gap_b, room))


def _wrapped_height(text: str, fontname: str, size: float, width: float, user_id) -> float:
    from app.services.edit_service.layout import _LINE_HEIGHT_RATIO, _wrap_text

    _key, path = fonts.resolve_font_path(fontname, user_id=user_id)
    lines = _wrap_text(text, path, size, max(width, 1.0)) if path else [text]
    return len(lines) * size * _LINE_HEIGHT_RATIO


# ---------- วาดใหม่ ----------

def _match(tables: list[dict], bbox: dict) -> dict:
    for t in tables:
        b = t["bbox"]
        if all(abs(b[k] - bbox[k]) <= _MATCH_PT for k in ("x0", "y0", "x1", "y1")):
            return t
    raise PDFError("ไม่พบตารางนี้ในหน้าแล้ว — โหลดหน้าใหม่แล้วลองอีกครั้ง")


def _validate(old: list[float], new: list[float], label: str) -> list[float]:
    if len(new) != len(old):
        raise PDFError(f"จำนวนเส้น{label}ไม่ตรงกับตาราง")
    new = [float(v) for v in new]
    if any(b - a < MIN_CELL_PT for a, b in zip(new, new[1:])):
        raise PDFError(f"{label}ต้องกว้างอย่างน้อย {MIN_CELL_PT:g} pt")
    return new


def rebuild_table(session: PDFSession, page_number: int, bbox: dict, xs_new: list[float], ys_new: list[float],
                  allow_overlap: bool = False) -> dict:
    """วาดตารางใหม่ตามเส้นแบ่งใหม่ — คืน {xs, ys (หลังขยายแถวอัตโนมัติ), adjusted_rows, wrapped_cells}"""
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    page = doc[page_number]
    if page.rotation:
        raise PDFError("ยังแก้ตารางในหน้าที่หมุนไม่ได้ — หมุนหน้ากลับเป็นแนวเดิมก่อน")
    table = _match(page_tables(session, page), bbox)
    xs, ys = table["xs"], table["ys"]
    nx = _validate(xs, xs_new, "คอลัมน์")
    ny = _validate(ys, ys_new, "แถว")
    old_box = fitz.Rect(xs[0], ys[0], xs[-1], ys[-1])
    area = old_box + (-2, -2, 2, 2)

    # ต้นทาง: สำเนาหน้า (ไม่มี annotation) ที่ลบเส้น/พื้นในกรอบตารางออก แล้วทำสำเนาหนึ่งหน้าต่อเซลล์ (ใช้ทรัพยากรร่วมกัน)
    src = fitz.open()
    src.insert_pdf(doc, from_page=page_number, to_page=page_number, annots=False)
    base = src[0]
    base.clean_contents()
    _drop_degenerate_rects(src, base)
    pw, ph = base.rect.width, base.rect.height
    # 1) ทุกอย่างนอกกรอบตาราง (ข้อความ รูป รูปทรง เช่น บาร์โค้ด) ไม่ต้องอยู่ในต้นทาง
    for rr in (fitz.Rect(0, 0, pw, area.y0), fitz.Rect(0, area.y1, pw, ph),
               fitz.Rect(0, area.y0, area.x0, area.y1), fitz.Rect(area.x1, area.y0, pw, area.y1)):
        if rr.width > 0 and rr.height > 0:
            base.add_redact_annot(rr)
    base.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    # 2) เส้น/พื้นของตาราง (วาดใหม่ทีหลัง) — เก็บข้อความ/รูปในเซลล์ไว้
    base.add_redact_annot(area)
    base.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                          text=fitz.PDF_REDACT_TEXT_NONE)
    cells = table["cells"]
    for _ in cells[1:]:
        src.fullcopy_page(0)
    width, height = src[0].rect.width, src[0].rect.height

    def old_rect(c):
        return fitz.Rect(xs[c["c"]], ys[c["r"]], xs[c["c"] + c["colspan"]], ys[c["r"] + c["rowspan"]])

    contents = []
    for k, c in enumerate(cells):
        sp, rect = src[k], old_rect(c)
        for rr in (fitz.Rect(0, 0, width, rect.y0), fitz.Rect(0, rect.y1, width, height),
                   fitz.Rect(0, rect.y0, rect.x0, rect.y1), fitz.Rect(rect.x1, rect.y0, width, rect.y1)):
            if rr.width > 0 and rr.height > 0:
                sp.add_redact_annot(rr)
        # graphics: ลบรูปทรงทุกชิ้นที่ไม่อยู่ในเซลล์ทั้งชิ้น — ไม่งั้นรูปทรงทั้งหน้า (เช่น บาร์โค้ด) ติดไปในทุกเซลล์
        # (มองไม่เห็นเพราะ clip แต่ไฟล์บวมและ find_tables รอบถัดไปเห็นเป็นเส้นตาราง)
        sp.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        contents.append(_cell_content(sp, rect))

    # ตัดบรรทัด/ขยายแถว: ความสูงที่แต่ละแถวต้องมีอย่างน้อย (เฉพาะเซลล์ที่ไม่ผสานแถว)
    wraps: dict[int, dict] = {}
    need = [0.0] * (len(ys) - 1)
    for k, c in enumerate(cells):
        info = contents[k]
        cb = info["bbox"]
        if cb.is_empty:
            continue
        rect = old_rect(c)
        pad_x = max(0.5, min(cb.x0 - rect.x0, rect.x1 - cb.x1, 3.0))
        pad_y = max(0.5, min(cb.y0 - rect.y0, rect.y1 - cb.y1, 3.0))
        new_w = nx[c["c"] + c["colspan"]] - nx[c["c"]]
        h = cb.height + 2 * pad_y
        # ตัดบรรทัดเมื่อเนื้อหาชิดเส้นจริง ๆ เท่านั้น (ยอมให้ระยะขอบในเซลล์หดเหลือ 0.5 pt) — ย่อทั้งตารางนิดเดียว
        # ไม่ควรทำให้ทุกช่องที่พอดีอยู่แล้วกลายเป็นสองบรรทัด
        if cb.width > new_w - 1.0 and info["text_only"]:
            main = font_inspect.summarize_spans(info["span_chars"], font_inspect.font_table(src[k]))[0]
            fontname = fonts.match_pdf_font_name(main["name"], flag_bold=main["bold"], flag_italic=main["italic"])
            text = _join_lines(info["lines"])
            pad_x = min(pad_x, max(0.5, (new_w - MIN_CELL_PT) / 2))
            h = _wrapped_height(text, fontname, main["size"], new_w - 2 * pad_x, session.user_id) + 2 * pad_y
            wraps[k] = {"text": text, "fontname": fontname, "size": main["size"], "color": main["color"],
                        "pad_x": pad_x, "pad_y": pad_y}
        if c["rowspan"] == 1:
            need[c["r"]] = max(need[c["r"]], h)
    adjusted = []
    for r in range(len(ny) - 1):
        grow = need[r] - (ny[r + 1] - ny[r])
        if grow > 0.25:
            adjusted.append(r)
            for j in range(r + 1, len(ny)):
                ny[j] += grow
    new_box = fitz.Rect(nx[0], ny[0], nx[-1], ny[-1])
    if not page.rect.contains(new_box + (1, 1, -1, -1)):
        raise PDFError("ตารางเกินขอบกระดาษ — ย่อหรือย้ายตารางให้อยู่ในหน้าก่อน")

    # ตารางใหม่ทับข้อความอื่นในหน้า (เช่น ขยายแถวจนชนยอดรวมด้านล่าง) — วาดได้แต่บอกผู้ใช้
    overlaps = any(
        fitz.Rect(w[:4]).intersects(new_box) and not fitz.Rect(w[:4]).intersects(area)
        for w in _content_page(page).get_text("words")
    )
    if overlaps and not allow_overlap:
        grown = f" (แถว {', '.join(str(r + 1) for r in adjusted)} สูงขึ้นเพื่อให้ข้อความที่ตัดบรรทัดพอ)" if adjusted else ""
        raise TableOverlapError(f"ตารางตำแหน่งใหม่จะทับข้อความอื่นในหน้า{grown}")

    # รูปทรงในกรอบตาราง (แปลงพิกัด) และรูปทรงที่แค่แตะกรอบ (วาดคืนตามเดิม) — อ่านก่อนลบ
    inside, crossing = [], []
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"]).normalize()  # เส้นตรงมีความสูง/กว้างเป็น 0 — เทียบพิกัดเอง (Rect.contains/intersects ของกรอบว่างเป็นเท็จ)
        if r.x1 < area.x0 or r.x0 > area.x1 or r.y1 < area.y0 or r.y0 > area.y1:
            continue
        within = r.x0 >= area.x0 and r.x1 <= area.x1 and r.y0 >= area.y0 and r.y1 <= area.y1
        (inside if within else crossing).append(d)

    # ไม่ระบายสีทับ: สุ่มสีจากมุมกรอบได้สีเส้นตาราง (ทดลองได้กล่องสีเทาเข้ม) · พื้นสีของเซลล์ถูกวาดคืนจากรูปทรงเดิมอยู่แล้ว
    page.add_redact_annot(area, fill=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    _redraw(page, crossing)
    _redraw(page, inside, _mapper(xs, nx), _mapper(ys, ny))

    wrapped_cells = []
    for k, c in enumerate(cells):
        info = contents[k]
        cb = info["bbox"]
        if cb.is_empty:
            continue
        rect = old_rect(c)
        new = fitz.Rect(nx[c["c"]], ny[c["r"]], nx[c["c"] + c["colspan"]], ny[c["r"] + c["rowspan"]])
        h_mode = _align(cb.x0 - rect.x0, rect.x1 - cb.x1, rect.width)
        v_mode = _align(cb.y0 - rect.y0, rect.y1 - cb.y1, rect.height)
        if k in wraps:
            w = wraps[k]
            inner = new + (w["pad_x"], w["pad_y"], -w["pad_x"], -w["pad_y"])
            wrapped_cells.append({"r": c["r"], "c": c["c"], "rect": inner, **w,
                                  "align": {"start": "left", "center": "center", "end": "right"}[h_mode]})
            continue
        clip = (cb + (-0.5, -0.5, 0.5, 0.5)) & rect
        w, h = clip.width, clip.height
        scale = min(1.0, (new.width - 1) / w if w else 1, (new.height - 1) / h if h else 1)  # รูป/ไอคอนที่ไม่พอ → ย่อ
        w, h = w * scale, h * scale
        x = _place(new.x0, new.x1, w, cb.x0 - rect.x0, rect.x1 - cb.x1, h_mode)
        y = _place(new.y0, new.y1, h, cb.y0 - rect.y0, rect.y1 - cb.y1, v_mode)
        page.show_pdf_page(fitz.Rect(x, y, x + w, y + h), src, k, clip=clip, keep_proportion=False)
    src.close()

    # ทะเบียนข้อความที่เคยแก้ในกรอบตาราง: กลายเป็นเนื้อหาเซลล์ไปแล้ว (ตำแหน่งในทะเบียนไม่ตรงอีก) — ให้เลือกแก้ใหม่แบบข้อความปกติ
    page_edits = session.text_edits.setdefault(page_number, {})
    stale = [e for e, rec in page_edits.items() if rec.get("kind") != "table"
             and fitz.Rect(*[rec["rect"][k] for k in ("x0", "y0", "x1", "y1")]).intersects(old_box)]
    for edit_id in stale:
        page_edits.pop(edit_id, None)
    table_key = table["id"] if table["id"].startswith("table-") else f"table-{uuid.uuid4().hex[:10]}"
    page_edits[table_key] = {"kind": "table", "xs": nx, "ys": ny, "cells": cells}

    # เซลล์ที่ต้องตัดบรรทัดใหม่: วาดด้วยระบบแก้ข้อความ (โหมดแทรก — ไม่ลบอะไรใต้กล่อง) → เลือกแก้ไขต่อได้
    from app.models.schemas import Rect
    from app.services.edit_service.text import replace_text

    for wc in wrapped_cells:
        r = wc["rect"]
        color = tuple(int(wc["color"][i:i + 2], 16) / 255 for i in (1, 3, 5))
        replace_text(session, page_number, Rect(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1), wc["text"], wc["size"],
                     wc["fontname"], color, block_id=f"insert-table-{uuid.uuid4().hex[:8]}", align=wc["align"])
    session.mark_dirty()
    return {"id": table_key, "xs": nx, "ys": ny, "adjusted_rows": adjusted, "overlaps_content": overlaps,
            "wrapped_cells": [{"r": w["r"], "c": w["c"]} for w in wrapped_cells]}
