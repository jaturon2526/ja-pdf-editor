"""อ่าน/แก้ไขข้อความในหน้า PDF (get_text_blocks, replace_text) — แนวทาง "redact แล้ววาดใหม่" ดู NOTES.md"""
from __future__ import annotations

import re
import uuid

import fitz  # PyMuPDF
from fpdf import FPDF

from app.core.session import PDFSession
from app.models.schemas import Rect, TextBlock
from app.services import fonts, thai_text
from app.services.pdf_service import PDFError, require_unlocked
from app.services.edit_service.layout import (
    _measure_width,
    _LINE_HEIGHT_RATIO,
    _PARAGRAPH_WRAP_RATIO,
    _TEXT_INSET,
    _TRACKED_EDIT_PREFIX,
    _UNDERLINE_MIN_WIDTH_PT,
    _UNDERLINE_OFFSET_RATIO,
    _UNDERLINE_WIDTH_RATIO,
    _rgb01_to_int,
    _sample_background_color,
    _wrap_text,
)


def get_text_blocks(session: PDFSession, page_number: int) -> list[TextBlock]:
    """คืนข้อความในหน้าโดยจัดกลุ่มเป็นระดับ "ย่อหน้า" — รวมเฉพาะบรรทัดที่ดู "wrap" มาจริงๆ จาก
    ย่อหน้าเดียวกัน (ไม่ใช่เชื่อ block ของ PyMuPDF ตรงๆ ดูหมายเหตุ "แก้บั๊กสำคัญ #3" ด้านบนของไฟล์)
    เพื่อให้ frontend เลือกแก้ไขได้ทีเดียวทั้งย่อหน้า — bbox ที่คืนไปคือกรอบรวมของทุกบรรทัดในกลุ่ม
    ส่วน fontname/fontsize/color เป็นค่าจาก span แรกของกลุ่ม ใช้เป็นค่าเริ่มต้นให้ properties
    panel ฝั่ง frontend เท่านั้น (ค่าจริงที่ใช้วาดตอนแก้ไขมาจากที่ผู้ใช้เลือกใน TextEditRequest)
    """
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    page = doc[page_number]
    from app.services.pdf_service.text_index import content_page

    text_page = content_page(page)  # ไม่รวมข้อความในกล่องข้อความ/กรอบ/ช่องฟอร์ม (เป็น annotation ไม่ใช่เนื้อหน้า)
    # จัดรูปข้อความไทย (PUA, สระอำแตก/หาย, ลำดับสระ-วรรณยุกต์) ก่อนส่งให้ผู้ใช้แก้ไข — ดู services/thai_text.py
    # rawdict (มีกรอบรายตัวอักษร) เพื่อแยกข้อความที่ PyMuPDF รวมเป็นบรรทัดเดียวข้ามช่องตาราง ("ระดับ 1 ระดับ 2 ...")
    raw = thai_text.normalize_page_dict(text_page.get_text("rawdict"), text_page)
    rules = _vertical_rules(page)
    hrules = _horizontal_rules(page) if rules else []

    # รวบรวมกรอบกล่องข้อความ (FreeText) เพื่อกรองบรรทัดที่อยู่ใต้กล่องออก (กล่องแก้ไขข้อความจะซ้อนกล่องข้อความ)
    # — ไม่รวมกรอบสี่เหลี่ยม (Square): เดิมวาดกรอบล้อมย่อหน้าไว้ แล้วแก้ไขข้อความในย่อหน้านั้นไม่ได้อีกเลย
    annot_rects: list[fitz.Rect] = [
        fitz.Rect(a.rect)
        for a in page.annots()
        if a.type[0] == fitz.PDF_ANNOT_FREE_TEXT
    ]

    def _overlaps_any_annot(line_bbox: tuple) -> bool:
        """ตรวจว่า line bbox ซ้อนทับกับ annotation rect มากกว่า 20% หรือไม่"""
        lx0, ly0, lx1, ly1 = line_bbox
        line_rect = fitz.Rect(lx0, ly0, lx1, ly1)
        for ar in annot_rects:
            inter = line_rect & ar
            if inter.is_empty:
                continue
            line_area = line_rect.get_area()
            annot_area = ar.get_area()
            inter_area = inter.get_area()
            if line_area > 0 and inter_area / line_area > 0.2:
                return True
            if annot_area > 0 and inter_area / annot_area > 0.2:
                return True
        return False


    blocks: list[TextBlock] = []
    all_groups: list[tuple[str, list[dict]]] = []
    for b_idx, block in enumerate(raw.get("blocks", [])):
        if block.get("type") != 0:  # 0 = text block, 1 = image block
            continue

        line_infos: list[dict] = []
        # ดึงกรอบ overlay_rect ของข้อความที่เพิ่งแก้ไขไป (เพื่อใช้กรองออกไม่ให้ซ้ำ)
        edit_overlays = []
        for rec in session.text_edits.get(page_number, {}).values():
            if "overlay_rect" in rec:
                o = rec["overlay_rect"]
                edit_overlays.append(fitz.Rect(o["x0"], o["y0"], o["x1"], o["y1"]))
            else:
                r = rec["rect"]
                edit_overlays.append(fitz.Rect(r["x0"] - 10, r["y0"] - 20, r["x1"] + 10, r["y1"] + 10))

        for line in block.get("lines", []):
            for seg in _line_segments(line, rules):
                lx0, ly0, lx1, ly1 = seg["bbox"]
                # กรองบรรทัดที่เป็นข้อความที่เราเพิ่งแทรกเข้าไปด้วย fpdf2 ออก (เพราะเราจะ append มันเองตอนท้าย)
                # อาศัยเช็คว่าจุดศูนย์กลางของบรรทัดตกอยู่ใน overlay_rect ที่เราจำไว้หรือไม่
                line_center = fitz.Point((lx0 + lx1) / 2, (ly0 + ly1) / 2)
                if any(er.contains(line_center) for er in edit_overlays):
                    continue
                # กรองบรรทัดที่ตกอยู่ในพื้นที่ annotation (freetext/rect) ออก
                if _overlaps_any_annot(seg["bbox"]):
                    continue
                seg["col"] = _cell_key(rules, seg["bbox"])
                seg["cell_w"] = _cell_width(rules, seg["bbox"])
                line_infos.append(seg)

        if not line_infos:
            continue

        # ความกว้างสูงสุดของบรรทัดแยกตามช่องตาราง (นอกตาราง = ทั้ง block) — ใช้ตัดสินว่าบรรทัดก่อนหน้า "wrap" มาหรือไม่
        col_width: dict = {}
        for li in line_infos:
            col_width[li["col"]] = max(col_width.get(li["col"], 0.0), li["bbox"][2] - li["bbox"][0])

        # รวมบรรทัดต่อเนื่องเป็นกลุ่มเดียวกันเฉพาะเมื่อ (1) อยู่ช่องตารางเดียวกัน (2) อยู่ "ใต้" บรรทัดก่อนหน้าและทับแนวนอนกัน
        # (บรรทัดที่วางเคียงข้างกันในแถวเดียวกันคือคนละช่อง/field) และ (3) บรรทัดก่อนหน้ากว้างเกือบเต็มความกว้างสุดของช่องนั้น
        # (แปลว่าน่าจะ wrap ต่อมาจริงๆ) ไม่งั้นถือเป็นย่อหน้า/field ใหม่
        groups: list[list[dict]] = []
        last_of_col: dict = {}
        for li in line_infos:
            gi = last_of_col.get(li["col"])
            if gi is not None:
                prev = groups[gi][-1]
                px0, py0, px1, py1 = prev["bbox"]
                x0, y0, x1, _y1 = li["bbox"]
                below = y0 >= py1 - 0.35 * (py1 - py0)
                overlap_x = min(x1, px1) > max(x0, px0)
                # ในช่องตาราง เทียบกับความกว้างของช่อง (ไม่ใช่บรรทัดที่กว้างสุดในช่อง — ป้ายสั้น ๆ ซ้อนกันในช่องเดียวกันไม่ใช่ย่อหน้าเดียวกัน)
                ref = prev.get("cell_w") or col_width[li["col"]]
                wide = ref > 0 and (px1 - px0) >= _PARAGRAPH_WRAP_RATIO * ref
                if (gi == len(groups) - 1 or li["col"] is not None) and below and overlap_x and wide \
                        and not (li["col"] is not None and _LIST_ITEM.match(li["text"])):
                    groups[gi].append(li)
                    continue
            groups.append([li])
            last_of_col[li["col"]] = len(groups) - 1

        for g_idx, group in enumerate(groups):
            all_groups.append((f"{b_idx}-{g_idx}", group))

    for block_id, group in _merge_cell_paragraphs(all_groups, rules, hrules):
        gx0 = min(li["bbox"][0] for li in group)
        gy0 = min(li["bbox"][1] for li in group)
        gx1 = max(li["bbox"][2] for li in group)
        gy1 = max(li["bbox"][3] for li in group)
        first_span = group[0]["span"]
        
        # คำนวณขนาดฟอนต์จากความสูงของ bounding box (bbox_height) ของบรรทัดแรก
        # เนื่องจากฟอนต์แต่ละตัวมีอัตราส่วน EM square ไม่เท่ากัน (เช่น TH Sarabun PSK จะดูเล็กกว่า Sarabun มากใน size เดียวกัน)
        # เราใช้ Google Sarabun เป็นหลัก ซึ่งมี bbox_height ประมาณ 1.35 เท่าของ point size
        # การคำนวณแบบนี้จะทำให้ UI เริ่มต้นด้วยขนาดฟอนต์ที่ตรงกับ visual size ของฟอนต์เดิมเป๊ะๆ
        first_line_bbox = group[0]["bbox"]
        bbox_height = first_line_bbox[3] - first_line_bbox[1]
        calculated_size = round(bbox_height / 1.35, 1)

        # ดึง span flags เพื่อตรวจ bold/italic (ตาม PyMuPDF: bit 4=bold, bit 1=italic)
        raw_flags = first_span.get("flags", 0)
        flag_bold   = bool(raw_flags & (1 << 4))
        flag_italic = bool(raw_flags & (1 << 1))

        # Auto-match font name: แปลงชื่อ raw PDF font เป็น key ที่มีอยู่ในระบบ
        raw_font = first_span.get("font", "")
        matched_font = fonts.match_pdf_font_name(raw_font, flag_bold=flag_bold, flag_italic=flag_italic)

        blocks.append(
            TextBlock(
                block_id=block_id,
                text="\n".join(li["text"] for li in group),
                rect=Rect(x0=gx0, y0=gy0, x1=gx1, y1=gy1),
                fontname=matched_font,
                fontsize=calculated_size,
                color=first_span.get("color", 0),
                # ข้อความดิบใน PDF ยังไม่เคยถูกแก้ไขในเซสชันนี้ — ไม่รู้การจัดวางเดิมจากไฟล์จริง
                # (PyMuPDF ไม่คืนค่านี้มาให้) ใช้ "left" เป็นค่าเริ่มต้นเสมอ เช่นเดียวกับ underline
                # (PyMuPDF ไม่บอกว่าข้อความเดิมมีเส้นขีดใต้วาดแยกอยู่หรือเปล่า ใช้ False เป็นค่าเริ่มต้น)
                align="left",
                valign="top",
                underline=False,
                is_bold=flag_bold or ("-bold" in matched_font),
                is_italic=flag_italic or ("-italic" in matched_font),
            )
        )

    # ต่อท้ายด้วยย่อหน้าที่เคยแก้ไขไปแล้วในเซสชันนี้ (ไม่โผล่มาจาก page.get_text('dict') อีกต่อไป
    # เพราะกลายเป็นรูปภาพไปแล้ว — ดูหมายเหตุ "แก้บั๊กสำคัญ #6" ด้านบนของไฟล์) ให้ยังคลิกแก้ไขซ้ำได้
    for edit_id, rec in session.text_edits.get(page_number, {}).items():
        r = rec["rect"]
        blocks.append(
            TextBlock(
                block_id=edit_id,
                text=rec["text"],
                rect=Rect(x0=r["x0"], y0=r["y0"], x1=r["x1"], y1=r["y1"]),
                fontname=rec["fontname"],
                fontsize=rec["fontsize"],
                color=rec["color_int"],
                # rec.get(...) กัน session เก่าที่แก้ไขไว้ก่อนฟีเจอร์นี้ (ยังไม่มี key "align"/"underline"
                # ในทะเบียน) ไม่ error — fallback เป็นค่าเดิม/ปิดเหมือนพฤติกรรมเดิม
                align=rec.get("align", "left"),
                valign=rec.get("valign", "top"),
                underline=rec.get("underline", False),
            )
        )
    return blocks


def _horizontal_rules(page: fitz.Page) -> list[tuple[float, float, float]]:
    """เส้นแนวนอนบนหน้า (เส้นแบ่งแถวตาราง) → [(y, x0, x1)]"""
    out = []
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return out
    for d in drawings:
        stroked = "s" in (d.get("type") or "")
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 1.0 and abs(a.x - b.x) >= _RULE_MIN_LEN:
                    out.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
            elif it[0] == "re":
                r = fitz.Rect(it[1])
                if r.width < _RULE_MIN_LEN:
                    continue
                if r.height < 2.5:
                    out.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
                elif stroked:
                    out.append((r.y0, r.x0, r.x1))
                    out.append((r.y1, r.x0, r.x1))
    return out


def _merge_cell_paragraphs(groups: list[tuple[str, list[dict]]], rules, hrules) -> list[tuple[str, list[dict]]]:
    """ย่อหน้าในช่องตารางที่ PyMuPDF แยกเป็นคนละ block (บรรทัดที่ wrap ในช่องเดียวกัน เช่น "3. พัฒนาระบบ ... ผู้รับจ้าง" +
    "โครงการ") → รวมเป็นย่อหน้าเดียว เมื่ออยู่ช่องเดียวกัน ติดกันแนวตั้ง ทับกันแนวนอน บรรทัดบนกว้างเกือบเต็มช่อง
    และไม่มีเส้นแบ่งแถวคั่นระหว่างกัน"""
    if not rules or len(groups) < 2:
        return groups
    order = sorted(range(len(groups)), key=lambda i: groups[i][1][0]["bbox"][1])
    merged_into: dict[int, int] = {}
    for pos, i in enumerate(order):
        top = groups[i][1]
        col = top[0]["col"]
        if col is None or i in merged_into:
            continue
        for j in order[pos + 1:]:
            if j in merged_into:
                continue
            below = groups[j][1]
            if below[0]["col"] != col:
                continue
            last, first = top[-1]["bbox"], below[0]["bbox"]
            h = last[3] - last[1]
            if first[1] - last[3] > 0.8 * h:
                break                                        # ห่างเกินไป — กลุ่มถัด ๆ ไปยิ่งห่าง
            if first[1] < last[3] - 0.35 * h or min(first[2], last[2]) <= max(first[0], last[0]):
                continue
            if abs(first[0] - top[0]["bbox"][0]) > 0.2 * h or _LIST_ITEM.match(below[0]["text"]):
                break                                        # ไม่ได้เริ่มที่ขอบซ้ายเดิม (ข้อความจัดกลาง) / เป็นข้อใหม่ของรายการ
            xs = _rules_at(rules, (last[1] + last[3]) / 2)
            left = max((x for x in xs if x <= last[0] + 1), default=None)
            right = min((x for x in xs if x >= last[2] - 1), default=None)
            if left is None or right is None or (last[2] - last[0]) < 0.8 * (right - left):
                break                                        # บรรทัดบนสั้น — ไม่ใช่ข้อความที่ wrap ต่อ
            cx = (last[0] + last[2]) / 2
            if any(last[3] - 1 <= y <= first[1] + 1 and x0 <= cx <= x1 for y, x0, x1 in hrules):
                break                                        # มีเส้นแบ่งแถวคั่น
            top.extend(below)
            merged_into[j] = i
            break
    return [g for k, g in enumerate(groups) if k not in merged_into]


_RULE_MIN_LEN = 6.0
_LIST_ITEM = re.compile(r"\s*(?:\d{1,3}[.)]|[๑-๙]{1,3}[.)]|[-•●▪*]\s|\(\d{1,3}\)|[ก-ฮ][.)]\s)")       # เส้นแนวตั้งที่สั้นกว่านี้ (pt) ไม่นับเป็นเส้นแบ่งช่องตาราง


def _vertical_rules(page: fitz.Page) -> list[tuple[float, float, float]]:
    """เส้นแนวตั้งบนหน้า (เส้นแบ่งคอลัมน์ตาราง) → [(x, y0, y1)] — จากเส้นตรง, สี่เหลี่ยมบาง ๆ และขอบซ้าย/ขวาของ
    สี่เหลี่ยมที่วาดเส้นขอบ (ช่องตารางที่วาดเป็นกรอบ)"""
    rules = []
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001 — หน้าเสีย/วาดแปลก ๆ: แค่ไม่แยกตามช่องตาราง
        return rules
    for d in drawings:
        stroked = "s" in (d.get("type") or "")
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.x - b.x) < 1.0 and abs(a.y - b.y) >= _RULE_MIN_LEN:
                    rules.append(((a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y)))
            elif it[0] == "re":
                r = fitz.Rect(it[1])
                if r.height < _RULE_MIN_LEN:
                    continue
                if r.width < 2.5:
                    rules.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif stroked:
                    rules.append((r.x0, r.y0, r.y1))
                    rules.append((r.x1, r.y0, r.y1))
    return rules


def _rules_at(rules, y: float) -> list[float]:
    return sorted(x for x, y0, y1 in rules if y0 - 1 <= y <= y1 + 1)


def _cell_key(rules, bbox) -> int | None:
    """ช่องตาราง (ลำดับช่องระหว่างเส้นแนวตั้ง) ที่ข้อความอยู่ — None ถ้าไม่มีเส้นแนวตั้งผ่านแนวบรรทัดนั้น"""
    xs = _rules_at(rules, (bbox[1] + bbox[3]) / 2)
    if not xs:
        return None
    cx = (bbox[0] + bbox[2]) / 2
    return round(max((x for x in xs if x <= cx), default=-1.0), 1)


def _cell_width(rules, bbox) -> float | None:
    """ความกว้างของช่องตารางที่ข้อความอยู่ (ระยะระหว่างเส้นแนวตั้งซ้าย/ขวา) — None ถ้าไม่มีเส้นครบสองข้าง"""
    xs = _rules_at(rules, (bbox[1] + bbox[3]) / 2)
    left = max((x for x in xs if x <= bbox[0] + 1), default=None)
    right = min((x for x in xs if x >= bbox[2] - 1), default=None)
    return (right - left) if left is not None and right is not None and right > left else None


def _line_segments(line: dict, rules) -> list[dict]:
    """บรรทัดจาก rawdict → ส่วนย่อยที่แยกตามเส้นแบ่งช่องตาราง [{"text", "bbox", "span"}]
    (PyMuPDF รวมข้อความคนละช่องในแถวเดียวกันเป็นบรรทัด/span เดียวได้ เช่น "ระดับ 1 ระดับ 2 ระดับ 3")"""
    chars = []
    for span in line.get("spans", []):
        if "chars" in span:
            for ch in span["chars"]:
                chars.append((ch.get("c", ""), ch["bbox"], span))
        elif span.get("text"):
            chars.append((span["text"], span["bbox"], span))
    ys = [c[1] for c in chars if c[0].strip()]
    if not ys:
        return []
    ymid = (min(b[1] for b in ys) + max(b[3] for b in ys)) / 2
    xs = _rules_at(rules, ymid)
    segs: list[list] = [[]]
    prev_ink = None
    for c, bbox, span in chars:
        if c.strip() and prev_ink is not None and any(prev_ink[2] - 1 <= x <= bbox[0] + 1 for x in xs):
            segs.append([])
        segs[-1].append((c, bbox, span))
        if c.strip():
            prev_ink = bbox
    out = []
    for seg in segs:
        ink = [(c, b, sp) for c, b, sp in seg if c.strip()]
        text = "".join(c for c, _b, _sp in seg).strip()
        if not ink or not text:
            continue
        out.append({"text": text,
                    "bbox": (min(b[0] for _c, b, _s in ink), min(b[1] for _c, b, _s in ink),
                             max(b[2] for _c, b, _s in ink), max(b[3] for _c, b, _s in ink)),
                    "span": ink[0][2]})
    return out


def _widen_for_single_line(page: fitz.Page, rect: fitz.Rect, text: str, font_path: str, size: float,
                           align: str) -> fitz.Rect:
    need = _measure_width(text, font_path, size) + 2 * _TEXT_INSET + 0.5
    if need <= rect.width:
        return rect
    ymid = (rect.y0 + rect.y1) / 2
    left_lim, right_lim = page.rect.x0 + 18, page.rect.x1 - 18
    for x in _rules_at(_vertical_rules(page), ymid):
        if x >= rect.x1 - 0.5:
            right_lim = min(right_lim, x - 1.5)
        elif x <= rect.x0 + 0.5:
            left_lim = max(left_lim, x + 1.5)
    for b in page.get_text("dict").get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                if not sp.get("text", "").strip():
                    continue
                r = fitz.Rect(sp["bbox"])
                if min(r.y1, rect.y1) - max(r.y0, rect.y0) < 0.5 * min(r.height, rect.height):
                    continue
                if r.x0 >= rect.x1 - 0.5:
                    right_lim = min(right_lim, r.x0 - 2)
                elif r.x1 <= rect.x0 + 0.5:
                    left_lim = max(left_lim, r.x1 + 2)
    extra = need - rect.width
    out = fitz.Rect(rect)
    if align == "right":
        out.x0 = max(left_lim, rect.x0 - extra)
    elif align == "center":
        out.x0 = max(left_lim, rect.x0 - extra / 2)
        out.x1 = min(right_lim, rect.x1 + extra / 2)
    else:
        out.x1 = min(right_lim, rect.x1 + extra)
    out.x0, out.x1 = min(out.x0, rect.x0), max(out.x1, rect.x1)
    return out


_VALID_ALIGNS = ("left", "center", "right")
_VALID_VALIGNS = ("top", "middle", "bottom")


def _find_background_shape(page: fitz.Page, text_rect: fitz.Rect) -> dict | None:
    """แถบสี/กล่องทึบที่ข้อความนี้วางอยู่ (เล็กที่สุดที่ครอบจุดต้นข้อความ) — None ถ้าไม่มี

    ข้ามพื้นหลังขาว/เกือบขาว และรูปทรงใหญ่ (กรอบทั้งหน้า/กล่องใหญ่) ซึ่งไม่ใช่ "แถบของข้อความนี้"
    คืน {"rect", "fill", "pad_right", "pad_bottom"} — pad คือระยะจากข้อความเดิมถึงขอบแถบ ใช้ตอนขยาย
    """
    probe = fitz.Point(text_rect.x0 + min(12.0, text_rect.width / 2), (text_rect.y0 + text_rect.y1) / 2)
    page_area = abs(page.rect)
    best = None
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        rect = fitz.Rect(drawing["rect"])
        if not fill or min(fill) > 0.94 or not rect.contains(probe):
            continue
        if abs(rect) > page_area * 0.25 or rect.height > max(text_rect.height * 3, 80):
            continue
        if best is None or abs(rect) < abs(best[0]):
            best = (rect, tuple(fill))
    if best is None:
        return None
    rect, fill = best
    words = [fitz.Rect(w[:4]) for w in page.get_text("words", clip=rect)]
    text_right = max((w.x1 for w in words), default=text_rect.x1)
    text_bottom = max((w.y1 for w in words), default=text_rect.y1)
    return {
        "rect": rect,
        "fill": fill,
        "pad_right": min(max(rect.x1 - text_right, 6.0), 30.0),
        "pad_bottom": min(max(rect.y1 - text_bottom, 3.0), 12.0),
    }


def _extend_background(page: fitz.Page, background: dict, content_right: float, content_bottom: float) -> list:
    """ต่อแถบสีออกไปทางขวา/ลงล่าง ให้คลุมข้อความใหม่ที่ยาวเกินแถบเดิม (ไม่ย่อแถบเดิม)
    คืนรายการกรอบส่วนต่อ [x0, y0, x1, y1] ไว้ลบตอนแก้ไขซ้ำ"""
    rect = background["rect"]
    right = max(rect.x1, min(content_right + background["pad_right"], page.rect.x1))
    bottom = max(rect.y1, min(content_bottom + background["pad_bottom"], page.rect.y1))
    added = []
    if right > rect.x1 + 0.5:
        added.append(fitz.Rect(rect.x1 - 0.5, rect.y0, right, rect.y1))
    if bottom > rect.y1 + 0.5:
        added.append(fitz.Rect(rect.x0, rect.y1 - 0.5, right, bottom))
    # ตัดให้อยู่ในหน้า — ส่วนต่อที่ยื่นเลยขอบหน้าแม้นิดเดียว จะลบออกด้วย redaction ตอนแก้ซ้ำไม่ได้
    added = [ext & page.rect for ext in added]
    for ext in added:
        page.draw_rect(ext, color=None, fill=background["fill"])
    return [list(ext) for ext in added]


def replace_text(
    session: PDFSession,
    page_number: int,
    rect: Rect,
    new_text: str,
    fontsize: float | None,
    fontname: str | None,
    color: tuple[float, float, float] | None,
    block_id: str | None = None,
    previous_rect: Rect | None = None,
    align: str | None = "left",
    valign: str | None = "top",
    underline: bool | None = False,
) -> None:
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")

    align_mode = (align or "left").lower()
    if align_mode not in _VALID_ALIGNS:
        align_mode = "left"

    valign_mode = (valign or "top").lower()
    if valign_mode not in _VALID_VALIGNS:
        valign_mode = "top"

    page = doc[page_number]
    target_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)

    # ฟอนต์ที่เลือกไม่มีตัวอักษรที่พิมพ์ (เช่น ฟอนต์อังกฤษที่ติดตั้งเองกับข้อความไทย) — เดิมตัวอักษรนั้นหายไปเงียบๆ
    # ("ทดสอบ Test" เหลือ " Test") ตรวจก่อน redact ข้อความเดิม เอกสารจึงไม่ถูกแตะถ้าไม่ผ่าน
    if new_text and new_text.strip():
        _key, _path = fonts.resolve_font_path(fontname, user_id=session.user_id)
        missing = fonts.missing_core_glyphs(_path, new_text) if _path else []
        if missing:
            label = fonts.font_label(_key, session.user_id)
            raise PDFError(f"ฟอนต์ \"{label}\" ไม่มีตัวอักษร {' '.join(missing[:12])} — เลือกฟอนต์ที่รองรับ (เช่น Sarabun) "
                           "แล้วบันทึกอีกครั้ง")

    # ถ้า block_id ตรงกับทะเบียนที่เคยแก้ไปแล้ว (ดูหมายเหตุ "แก้บั๊กสำคัญ #6") ถือเป็นการแก้ไขซ้ำ —
    # ใช้ id เดิมต่อ (อัปเดตในทะเบียนแทนสร้างรายการใหม่) ไม่งั้นถือเป็นการแก้ครั้งแรก สร้าง id ใหม่ให้
    page_edits = session.text_edits.setdefault(page_number, {})
    is_re_edit = bool(block_id) and block_id in page_edits
    edit_id = block_id if is_re_edit else f"{_TRACKED_EDIT_PREFIX}{uuid.uuid4().hex[:10]}"

    # 1) ลบข้อความ/รูปข้อความเดิมด้วย redaction — ถ้าเป็นการแก้ไขซ้ำ ต้อง redact กรอบเดิม
    #    (previous_rect ที่รูปข้อความจาก edit ครั้งก่อนวาดอยู่จริง) รวมกับกรอบใหม่ด้วย ไม่งั้นรูป
    #    ข้อความเก่าจะเหลือค้างอยู่ (ดูหมายเหตุ "แก้บั๊กสำคัญ #6") — fill ด้วยสีพื้นหลังจริงที่สุ่มจาก
    #    มุมกรอบใหม่ (ไม่ใช่ขาวตายตัว — ดูหมายเหตุ "แก้บั๊กสำคัญ #4") ต้องสุ่มสีก่อน apply_redactions
    #    เพราะหลังจากนั้นเนื้อหาเดิมในกล่องจะถูกลบไปแล้ว
    previous_rect_f = fitz.Rect(previous_rect.x0, previous_rect.y0, previous_rect.x1, previous_rect.y1) if previous_rect else None
    redact_rect = fitz.Rect(target_rect)
    if previous_rect is not None:
        redact_rect |= fitz.Rect(previous_rect.x0, previous_rect.y0, previous_rect.x1, previous_rect.y1)
    # ไม่ระบายสีทับ (fill=False): ลบเฉพาะตัวอักษร พื้นหลังที่เป็นกราฟิก (แถบสี กล่อง เส้น) อยู่ครบ — เดิม fill
    # ด้วยสีที่สุ่มจากมุมกล่อง พอกล่องข้อความยื่นออกนอกแถบสี (เช่น หัวข้อตัวขาวบนแถบน้ำเงิน) จะสุ่มได้สีขาว
    # แล้วระบายทับแถบหาย + ข้อความใหม่สีขาวมองไม่เห็น ระบายสีเฉพาะเมื่อทับรูปภาพ (ข้อความในรูปสแกน/รูปข้อความ
    # จาก edit รุ่นเก่า) เพราะพิกเซลรูปที่ถูกลบจะกลายเป็นสีขาว
    # แก้ซ้ำ: ลบส่วนที่เคยต่อแถบสีออกไปจาก edit ครั้งก่อนก่อน (ลบเฉพาะรูปทรงที่อยู่ในกรอบส่วนต่อทั้งชิ้น —
    # แถบเดิมไม่ถูกแตะ) ข้อความใหม่สั้นลงแถบก็หดกลับ
    # แทรกข้อความใหม่ (เครื่องมือ "แทรกข้อความ" — block_id ขึ้นต้น insert-): ไม่ลบอะไรใต้กล่อง
    # เดิมใช้ขั้นตอนเดียวกับแก้ข้อความเดิม → ข้อความ/รูปที่อยู่ใต้กล่องที่ลากหายไปด้วย (เช่น วางกล่องเติมคำบนแบบฟอร์ม)
    is_insert = bool(block_id) and block_id.startswith("insert-") and previous_rect is None
    prev_entry = page_edits.get(edit_id, {}) if is_re_edit else {}
    if prev_entry.get("inserted"):
        # แก้ซ้ำข้อความที่แทรกไว้: ซ่อนเฉพาะข้อความที่เราวาดครั้งก่อน (Form XObject ของมัน) — ไม่ redact กรอบ
        # ซึ่งจะลบข้อความเดิมของเอกสารที่อยู่ใต้กล่องไปด้วย
        from app.services.edit_service.images import hide_xobject_name
        xobjs = page.get_xobjects()  # show_pdf_page คืน xref ของฟอร์มชั้นใน — ชื่อในหน้าเป็นของฟอร์มชั้นนอกที่เรียกมัน
        outer = {x[2] for x in xobjs if x[0] == prev_entry.get("form_xref")}
        names = [x[1] for x in xobjs if x[0] in outer and x[2] == 0]
        if names and hide_xobject_name(page, names[0]):
            is_insert = True
    background = None
    if not is_insert:
        old_extensions = page_edits.get(edit_id, {}).get("bg_extensions", []) if is_re_edit else []
        # ทีละชิ้น: ใส่หลายกรอบใน apply_redactions ครั้งเดียว MuPDF ลบรูปทรงที่ "ถูกคลุมทั้งชิ้น" ได้แค่บางชิ้น
        for ext in old_extensions:
            page.add_redact_annot(fitz.Rect(ext) + (-0.5, -0.5, 0.5, 0.5), fill=False)
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                text=fitz.PDF_REDACT_TEXT_NONE,
            )

        # แถบสี/กล่องพื้นหลังของข้อความเดิม (เช่น แถบหัวข้อสีน้ำเงิน) — ถ้าข้อความใหม่ยาวกว่าแถบจะขยายแถบตาม
        # (ดู NOTES.md ข้อ #11) ต้องหาก่อน redact เพราะต้องรู้ขอบข้อความเดิมด้วย
        background = _find_background_shape(page, previous_rect_f or target_rect)

        overlaps_image = any(fitz.Rect(info["bbox"]).intersects(redact_rect) for info in page.get_image_info())
        page.add_redact_annot(redact_rect, fill=_sample_background_color(page, redact_rect) if overlaps_image else False)
        # PDF_REDACT_IMAGE_PIXELS: ลบเฉพาะพิกเซลของรูปที่ทับกับกรอบ redact (รวมถึงรูปข้อความที่เราแทรกเอง
        # จาก edit ครั้งก่อน) โดยไม่ลบทั้ง object รูปถ้ามันยื่นออกไปนอกกรอบ — ปลอดภัยกว่า REMOVE เฉยๆ
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)

    if not new_text.strip():
        # ผู้ใช้ลบข้อความทิ้งเฉยๆ (ไม่ใส่ข้อความใหม่) — redact ให้แล้ว ถ้าเคยอยู่ในทะเบียนก็เอาออกด้วย
        # (ไม่งั้น get_text_blocks() จะยังคืนกล่องว่างๆ ให้คลิกแก้ไขอยู่)
        page_edits.pop(edit_id, None)
        session.mark_dirty()  # redact ข้างบนแก้ไข doc จริงแล้ว — กันบั๊ก saveIncr() ซ้อน (ดู session.py)
        return

    # 2) เลือก font ที่รองรับไทยจริง (bundle เอง — ดู app/services/fonts.py) แทน base-14 ของ PyMuPDF
    font_key, font_path = fonts.resolve_font_path(fontname, user_id=session.user_id)
    size = fontsize or 12
    fill_color = color or (0, 0, 0)

    if font_path and new_text.strip() and "\n" not in new_text.strip():
        # ข้อความบรรทัดเดียวที่ยาวกว่ากล่องเดิมเล็กน้อย (เช่น แก้ "92" เป็น "100" ในช่องตาราง) → ขยายกล่องออกไปในที่ว่าง
        # (ไม่เกินเส้นแบ่งช่องตาราง/ข้อความข้างเคียงในแนวเดียวกัน/ขอบหน้า) แทนการตัดคำกลางตัวเลข
        target_rect = _widen_for_single_line(page, target_rect, new_text.strip(), font_path, fontsize or 12, align_mode)

    usable_width = max(target_rect.width - 2 * _TEXT_INSET, 10.0)

    if not font_path:
        # ไม่มีไฟล์ font ให้ใช้เลย (deploy ผิดพลาด) — วาดดิบๆ ด้วย base-14 อย่างน้อยอังกฤษยังอ่านได้
        insert_point = fitz.Point(target_rect.x0 + _TEXT_INSET, target_rect.y0 + size * 0.85)
        page.insert_text(
            insert_point,
            new_text.split("\n"),
            fontsize=size,
            fontname=font_key,
            color=fill_color,
            lineheight=_LINE_HEIGHT_RATIO,
        )
        session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดู _doc_dirty ใน session.py
        return

    # 3) ตัดคำ + จัดบรรทัดที่ font size ตามที่ผู้ใช้เลือกตรงๆ (ไม่ย่อขนาดให้เองอีกต่อไป — ดูหมายเหตุ
    #    "แก้บั๊กสำคัญ #5" ด้านบนของไฟล์ ผู้ใช้ลากขยายกล่องเองได้ถ้าข้อความจะล้น)
    wrapped_lines = _wrap_text(new_text, font_path, size, usable_width)

    # 4) เรนเดอร์ข้อความผ่าน fpdf2 + uharfbuzz แล้ววางทับด้วย show_pdf_page
    content_bottom_pt = target_rect.y0

    # คำนวณความสูงของ micro-PDF เผื่อ headroom ให้วรรณยุกต์บนสุด (เช่น ไม้โท) ไม่ถูกตัด
    headroom_pt = size * 1.2  # 1.2 เท่าของขนาดฟอนต์ เพื่อให้พื้นที่ด้านบน baseline พอ
    
    num_lines = len([l for l in wrapped_lines if l.strip()])
    if num_lines == 0:
        micro_height = target_rect.height
        y_offset = 0
    else:
        last_baseline = headroom_pt + (num_lines - 1) * (size * _LINE_HEIGHT_RATIO)
        micro_height = last_baseline + size * 0.5
        
        # คำนวณ offset แนวตั้ง
        total_text_height = num_lines * size * _LINE_HEIGHT_RATIO
        y_offset = 0
        if valign_mode == "middle":
            y_offset = max(0, (target_rect.height - total_text_height) / 2)
        elif valign_mode == "bottom":
            y_offset = max(0, target_rect.height - total_text_height)

    micro_width = usable_width + 2 * _TEXT_INSET

    # สร้าง Micro-PDF
    pdf = FPDF(format=(micro_width, micro_height), unit="pt")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.add_font("Custom", "", font_path)
    pdf.set_font("Custom", size=size)
    r, g, b = [max(0, min(255, int(c * 255))) for c in fill_color]
    pdf.set_text_color(r, g, b)
    
    # เปิดการทำงานของ Text Shaping (uharfbuzz) ให้ FPDF (ต้องเปิดที่ระดับ instance ใน fpdf2 2.8+)
    pdf.set_text_shaping(True, script="thai", language="tha")

    line_count = 0
    content_right_pt = target_rect.x0
    underlines: list[tuple[float, float, float]] = []
    for line_text in wrapped_lines:
        if not line_text.strip():
            continue

        # ตำแหน่ง Y สำหรับวางข้อความใน Micro-PDF
        micro_baseline_y = headroom_pt + line_count * size * _LINE_HEIGHT_RATIO
        # ตำแหน่ง Y (baseline) จริงบนเอกสารหลัก สำหรับใช้วาดขีดเส้นใต้
        main_baseline_y = target_rect.y0 + y_offset + size * 0.85 + line_count * size * _LINE_HEIGHT_RATIO

        visible_width_pt = pdf.get_string_width(line_text)

        if align_mode == "center":
            line_x = (micro_width - visible_width_pt) / 2
        elif align_mode == "right":
            line_x = micro_width - _TEXT_INSET - visible_width_pt
        else:
            line_x = _TEXT_INSET

        # วาดข้อความลง Micro-PDF
        # ต้องใช้ cell() เพื่อให้ fpdf2 ประมวลผล text_shaping (เช่น วรรณยุกต์ไม่ซ้อนกัน)
        # เนื่องจาก pdf.text() ถูกยกเลิกการรองรับ shaping ไปในเวอร์ชันล่าสุด
        # สูตรหาตำแหน่งพิกัดให้ตรง baseline เดิม: y = baseline - 0.3 * font_size
        pdf.c_margin = 0
        pdf.set_xy(line_x, micro_baseline_y - 0.3 * size)
        pdf.cell(w=0, h=0, text=line_text, align="L")

        content_bottom_pt = max(content_bottom_pt, main_baseline_y + size * 0.3)

        content_right_pt = max(content_right_pt, target_rect.x0 + line_x + visible_width_pt)
        if underline and visible_width_pt > 0:
            underline_y = main_baseline_y + size * _UNDERLINE_OFFSET_RATIO
            underlines.append((target_rect.x0 + line_x, target_rect.x0 + line_x + visible_width_pt, underline_y))
        line_count += 1

    # ขยายแถบสีพื้นหลังให้คลุมข้อความใหม่ (วาดก่อนข้อความ/เส้นใต้ ไม่งั้นจะทับข้อความ)
    bg_extensions = []
    if background is not None and line_count:
        bg_extensions = _extend_background(page, background, content_right_pt, content_bottom_pt)
    for x0, x1, y in underlines:
        page.draw_line(
            fitz.Point(x0, y),
            fitz.Point(x1, y),
            color=fill_color,
            width=max(_UNDERLINE_MIN_WIDTH_PT, size * _UNDERLINE_WIDTH_RATIO),
        )

    # นำ Micro-PDF มาวางทับหน้าเอกสารหลัก
    # เลื่อน overlay ขึ้นเพื่อให้ micro_baseline แรก (headroom) ตรงกับ baseline ที่ตั้งใจไว้ในเอกสารหลัก (0.85)
    overlay_y0 = (target_rect.y0 + y_offset + size * 0.85) - headroom_pt
    micro_pdf_bytes = pdf.output()
    micro_doc = fitz.open("pdf", micro_pdf_bytes)
    overlay_rect = fitz.Rect(target_rect.x0, overlay_y0, target_rect.x0 + micro_width, overlay_y0 + micro_height)
    form_xref = page.show_pdf_page(overlay_rect, micro_doc, 0)

    # 5) อัปเดต/บันทึกลงทะเบียนย่อหน้าที่แก้ไขแล้ว (ดูหมายเหตุ "แก้บั๊กสำคัญ #6") ให้ get_text_blocks()
    #    เอากลับมาแสดงเป็นกล่องคลิกแก้ไขได้อีกในครั้งถัดไป (รวมถึง align ให้กลับมาแก้ไขซ้ำแล้วยังเห็น
    #    การจัดตัวหนังสือเดิมที่เคยเลือกไว้ ไม่รีเซ็ตกลับไปชิดซ้ายทุกครั้ง)
    # ขยาย rect ขอบล่างให้ครอบคลุมเนื้อหาจริงเสมอ (แก้บั๊กสำคัญ #8 ด้านบนของไฟล์ — กล่องเดิมอาจเล็กเกินไป
    # ถ้าผู้ใช้เพิ่งเลือกฟอนต์ขนาดใหญ่ขึ้นโดยไม่ได้ลากขยายกล่องเอง) ไม่ย่อกล่องให้เล็กลงแม้เนื้อหาจะสั้นกว่า
    # เดิม (เคารพขนาดที่ผู้ใช้ลากไว้เป็นอย่างน้อยเสมอ) เผื่อระยะขอบล่างเท่ากับ _TEXT_INSET เหมือนขอบอื่นๆ
    stored_y1 = max(target_rect.y1, content_bottom_pt + _TEXT_INSET)
    page_edits[edit_id] = {
        "rect": {"x0": target_rect.x0, "y0": target_rect.y0, "x1": target_rect.x1, "y1": stored_y1},
        "overlay_rect": {"x0": overlay_rect.x0, "y0": overlay_rect.y0, "x1": overlay_rect.x1, "y1": overlay_rect.y1},
        "text": new_text,
        "fontname": font_key,
        "fontsize": size,
        "color_int": _rgb01_to_int(fill_color),
        "align": align_mode,
        "valign": valign_mode,
        "underline": bool(underline),
        "bg_extensions": bg_extensions,
        "form_xref": form_xref,
        "inserted": is_insert,
    }
    session.mark_dirty()  # กันบั๊ก saveIncr() ซ้อนไม่มีอะไรเปลี่ยน — ดู _doc_dirty ใน session.py
