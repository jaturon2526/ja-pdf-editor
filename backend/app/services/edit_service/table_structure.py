"""แก้ไขโครงสร้างตาราง (v1.46.0): เพิ่ม/ลบแถว · เพิ่ม/ลบคอลัมน์ · รวมเซลล์ · แยกเซลล์

ต่อยอดจาก ``tables.py`` (v1.40.0) โดยใช้โมเดลตารางเดียวกัน ({id, bbox, xs, ys, cells})
และลงทะเบียนผลลัพธ์ใน ``session.text_edits[page_number][table_key]`` เพื่อให้เครื่องมือ
ปรับขนาด/ย้ายตาราง และ Undo/Redo ทำงานต่อเนื่องได้ทันที
"""
from __future__ import annotations

import uuid
from typing import Literal

import fitz

from app.core.session import PDFSession
from app.services.edit_service.tables import (
    MIN_CELL_PT,
    TableOverlapError,
    _align,
    _cell_content,
    _content_page,
    _drop_degenerate_rects,
    _match,
    _place,
    _prune_empty_xobjects,
    _redraw,
    page_tables,
)
from app.services.pdf_service import PDFError, require_unlocked

TableStructureOp = Literal[
    "insert_row",
    "delete_row",
    "insert_col",
    "delete_col",
    "merge_cells",
    "split_cell",
]


def _detect_table_style(
    inside_drawings: list[dict],
    xs: list[float],
    ys: list[float],
    cells: list[dict],
) -> tuple[tuple[float, ...], float, dict[tuple[int, int], tuple[float, ...]]]:
    """สุ่มสี/ความหนาเส้นขอบเดิมของตาราง และสีพื้นของแต่ละเซลล์ (ถ้ามี เช่น แถวหัวตาราง)"""
    stroke_colors: list[tuple[float, ...]] = []
    stroke_widths: list[float] = []
    fill_rects: list[tuple[fitz.Rect, tuple[float, ...]]] = []

    for d in inside_drawings:
        dtype = d.get("type") or ""
        if "s" in dtype and d.get("color") is not None:
            stroke_colors.append(tuple(d["color"]))
            w = d.get("width")
            if w and w > 0:
                stroke_widths.append(float(w))
        if "f" in dtype and d.get("fill") is not None:
            fill = tuple(d["fill"])
            # ข้ามสีขาวล้วน (พื้นหลังปกติ)
            if not all(ch >= 0.98 for ch in fill):
                r = fitz.Rect(d["rect"]).normalize()
                if r.width > 4 and r.height > 4:
                    fill_rects.append((r, fill))

    border_color = stroke_colors[0] if stroke_colors else (0.0, 0.0, 0.0)
    if stroke_widths:
        stroke_widths.sort()
        mid = stroke_widths[len(stroke_widths) // 2]
        border_width = max(0.5, min(2.0, mid))
    else:
        border_width = 0.75

    cell_fills: dict[tuple[int, int], tuple[float, ...]] = {}
    for c in cells:
        cr = fitz.Rect(xs[c["c"]], ys[c["r"]], xs[c["c"] + c["colspan"]], ys[c["r"] + c["rowspan"]])
        center = fitz.Point((cr.x0 + cr.x1) / 2, (cr.y0 + cr.y1) / 2)
        for fr, fcol in fill_rects:
            if fr.contains(center):
                cell_fills[(c["r"], c["c"])] = fcol
                break

    return border_color, border_width, cell_fills


def _draw_table_grid(
    page: fitz.Page,
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    border_color: tuple[float, ...],
    border_width: float,
    new_cell_fills: dict[tuple[int, int], tuple[float, ...]],
) -> None:
    """วาดพื้นสีเซลล์ (ถ้ามี) และเส้นขอบของทุกเซลล์ในตารางใหม่"""
    if new_cell_fills:
        fill_shape = page.new_shape()
        for c in cells:
            fcol = new_cell_fills.get((c["r"], c["c"]))
            if not fcol:
                continue
            r = fitz.Rect(xs[c["c"]], ys[c["r"]], xs[c["c"] + c["colspan"]], ys[c["r"] + c["rowspan"]])
            fill_shape.draw_rect(r)
            fill_shape.finish(color=None, fill=fcol, width=0)
        fill_shape.commit()

    shape = page.new_shape()
    for c in cells:
        r = fitz.Rect(xs[c["c"]], ys[c["r"]], xs[c["c"] + c["colspan"]], ys[c["r"] + c["rowspan"]])
        shape.draw_rect(r)
    shape.finish(color=border_color, fill=None, width=border_width)
    shape.commit()


def _cell_at(cells: list[dict], r: int, c: int) -> dict | None:
    for cell in cells:
        if cell["r"] <= r < cell["r"] + cell["rowspan"] and cell["c"] <= c < cell["c"] + cell["colspan"]:
            return cell
    return None


def _plan_insert_row(
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    r0: int,
    position: str,
) -> tuple[list[float], list[float], list[dict], list[tuple[int, dict, bool]]]:
    n_rows = len(ys) - 1
    n_cols = len(xs) - 1
    if not (0 <= r0 < n_rows):
        raise PDFError("ตำแหน่งแถวไม่อยู่ในตาราง")
    insert_at = r0 if position == "above" else r0 + 1
    row_h = max(MIN_CELL_PT, ys[r0 + 1] - ys[r0])

    ny = list(ys[:insert_at]) + [ys[insert_at]] + [y + row_h for y in ys[insert_at:]]
    new_cells: list[dict] = []
    moves: list[tuple[int, dict, bool]] = []
    covered_cols: set[int] = set()

    for idx, cell in enumerate(cells):
        r, c, rs, cs = cell["r"], cell["c"], cell["rowspan"], cell["colspan"]
        if r < insert_at < r + rs:
            nc = {"r": r, "c": c, "rowspan": rs + 1, "colspan": cs}
            covered_cols.update(range(c, c + cs))
        elif r >= insert_at:
            nc = {"r": r + 1, "c": c, "rowspan": rs, "colspan": cs}
        else:
            nc = {"r": r, "c": c, "rowspan": rs, "colspan": cs}
        new_cells.append(nc)
        moves.append((idx, nc, False))

    for col in range(n_cols):
        if col not in covered_cols:
            new_cells.append({"r": insert_at, "c": col, "rowspan": 1, "colspan": 1})

    new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
    return list(xs), ny, new_cells, moves


def _plan_delete_row(
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    r0: int,
) -> tuple[list[float], list[float], list[dict], list[tuple[int, dict, bool]]]:
    n_rows = len(ys) - 1
    if n_rows <= 1:
        raise PDFError("ตารางต้องมีอย่างน้อย 1 แถว")
    if not (0 <= r0 < n_rows):
        raise PDFError("ตำแหน่งแถวไม่อยู่ในตาราง")

    row_h = ys[r0 + 1] - ys[r0]
    ny = list(ys[: r0 + 1]) + [y - row_h for y in ys[r0 + 2 :]]
    new_cells: list[dict] = []
    moves: list[tuple[int, dict, bool]] = []

    for idx, cell in enumerate(cells):
        r, c, rs, cs = cell["r"], cell["c"], cell["rowspan"], cell["colspan"]
        if r == r0 and rs == 1:
            continue
        if r <= r0 < r + rs:
            nc = {"r": r, "c": c, "rowspan": rs - 1, "colspan": cs}
        elif r > r0:
            nc = {"r": r - 1, "c": c, "rowspan": rs, "colspan": cs}
        else:
            nc = {"r": r, "c": c, "rowspan": rs, "colspan": cs}
        new_cells.append(nc)
        moves.append((idx, nc, False))

    new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
    return list(xs), ny, new_cells, moves


def _plan_insert_col(
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    c0: int,
    position: str,
) -> tuple[list[float], list[float], list[dict], list[tuple[int, dict, bool]]]:
    n_rows = len(ys) - 1
    n_cols = len(xs) - 1
    if not (0 <= c0 < n_cols):
        raise PDFError("ตำแหน่งคอลัมน์ไม่อยู่ในตาราง")
    insert_at = c0 if position == "left" else c0 + 1
    col_w = max(MIN_CELL_PT, xs[c0 + 1] - xs[c0])

    nx = list(xs[:insert_at]) + [xs[insert_at]] + [x + col_w for x in xs[insert_at:]]
    new_cells: list[dict] = []
    moves: list[tuple[int, dict, bool]] = []
    covered_rows: set[int] = set()

    for idx, cell in enumerate(cells):
        r, c, rs, cs = cell["r"], cell["c"], cell["rowspan"], cell["colspan"]
        if c < insert_at < c + cs:
            nc = {"r": r, "c": c, "rowspan": rs, "colspan": cs + 1}
            covered_rows.update(range(r, r + rs))
        elif c >= insert_at:
            nc = {"r": r, "c": c + 1, "rowspan": rs, "colspan": cs}
        else:
            nc = {"r": r, "c": c, "rowspan": rs, "colspan": cs}
        new_cells.append(nc)
        moves.append((idx, nc, False))

    for row in range(n_rows):
        if row not in covered_rows:
            new_cells.append({"r": row, "c": insert_at, "rowspan": 1, "colspan": 1})

    new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
    return nx, list(ys), new_cells, moves


def _plan_delete_col(
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    c0: int,
) -> tuple[list[float], list[float], list[dict], list[tuple[int, dict, bool]]]:
    n_cols = len(xs) - 1
    if n_cols <= 1:
        raise PDFError("ตารางต้องมีอย่างน้อย 1 คอลัมน์")
    if not (0 <= c0 < n_cols):
        raise PDFError("ตำแหน่งคอลัมน์ไม่อยู่ในตาราง")

    col_w = xs[c0 + 1] - xs[c0]
    nx = list(xs[: c0 + 1]) + [x - col_w for x in xs[c0 + 2 :]]
    new_cells: list[dict] = []
    moves: list[tuple[int, dict, bool]] = []

    for idx, cell in enumerate(cells):
        r, c, rs, cs = cell["r"], cell["c"], cell["rowspan"], cell["colspan"]
        if c == c0 and cs == 1:
            continue
        if c <= c0 < c + cs:
            nc = {"r": r, "c": c, "rowspan": rs, "colspan": cs - 1}
        elif c > c0:
            nc = {"r": r, "c": c - 1, "rowspan": rs, "colspan": cs}
        else:
            nc = {"r": r, "c": c, "rowspan": rs, "colspan": cs}
        new_cells.append(nc)
        moves.append((idx, nc, False))

    new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
    return nx, list(ys), new_cells, moves


def _plan_merge_cells(
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    r0: int,
    c0: int,
    r1: int,
    c1: int,
) -> tuple[list[float], list[float], list[dict], list[tuple[int, dict, bool]]]:
    n_rows = len(ys) - 1
    n_cols = len(xs) - 1
    min_r, max_r = min(r0, r1), max(r0, r1)
    min_c, max_c = min(c0, c1), max(c0, c1)
    if not (0 <= min_r <= max_r < n_rows and 0 <= min_c <= max_c < n_cols):
        raise PDFError("ช่วงเซลล์ที่เลือกอยู่นอกตาราง")

    # ขยายกรอบให้ครอบเซลล์ผสานเดิมที่คาบเกี่ยวกับช่วงที่เลือกจนเสถียร
    changed = True
    while changed:
        changed = False
        for cell in cells:
            cr0, cc0 = cell["r"], cell["c"]
            cr1, cc1 = cr0 + cell["rowspan"] - 1, cc0 + cell["colspan"] - 1
            if cr1 >= min_r and cr0 <= max_r and cc1 >= min_c and cc0 <= max_c:
                if cr0 < min_r or cr1 > max_r or cc0 < min_c or cc1 > max_c:
                    min_r = min(min_r, cr0)
                    max_r = max(max_r, cr1)
                    min_c = min(min_c, cc0)
                    max_c = max(max_c, cc1)
                    changed = True

    merged = {"r": min_r, "c": min_c, "rowspan": max_r - min_r + 1, "colspan": max_c - min_c + 1}
    new_cells: list[dict] = [merged]
    moves: list[tuple[int, dict, bool]] = []
    merged_count = 0

    for idx, cell in enumerate(cells):
        cr0, cc0 = cell["r"], cell["c"]
        if min_r <= cr0 <= max_r and min_c <= cc0 <= max_c:
            merged_count += 1
            # preserve_pos=True เพื่อคงตำแหน่งเดิมของแต่ละเซลล์ลูกภายในกรอบเซลล์ที่รวม ไม่ให้ข้อความซ้อนกัน
            moves.append((idx, merged, True))
        else:
            nc = dict(cell)
            new_cells.append(nc)
            moves.append((idx, nc, False))

    if merged_count < 2:
        raise PDFError("กรุณาเลือกอย่างน้อย 2 เซลล์เพื่อรวมเซลล์")

    new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
    return list(xs), list(ys), new_cells, moves


def _plan_split_cell(
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    r0: int,
    c0: int,
    direction: str,
) -> tuple[list[float], list[float], list[dict], list[tuple[int, dict, bool]]]:
    target = _cell_at(cells, r0, c0)
    if target is None:
        raise PDFError("ไม่พบเซลล์ที่เลือกในตาราง")
    target_idx = cells.index(target)

    # กรณี 1: เซลล์ที่ผสานอยู่แล้ว → ยกเลิกการผสานกลับเป็นเซลล์ 1×1
    if target["rowspan"] > 1 or target["colspan"] > 1:
        new_cells: list[dict] = []
        moves: list[tuple[int, dict, bool]] = []
        for idx, cell in enumerate(cells):
            if idx == target_idx:
                top_left = {"r": cell["r"], "c": cell["c"], "rowspan": 1, "colspan": 1}
                for rr in range(cell["r"], cell["r"] + cell["rowspan"]):
                    for cc in range(cell["c"], cell["c"] + cell["colspan"]):
                        new_cells.append(top_left if (rr == cell["r"] and cc == cell["c"]) else {"r": rr, "c": cc, "rowspan": 1, "colspan": 1})
                moves.append((idx, top_left, False))
            else:
                nc = dict(cell)
                new_cells.append(nc)
                moves.append((idx, nc, False))
        new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
        return list(xs), list(ys), new_cells, moves

    # กรณี 2: เซลล์ 1×1 → แยกเป็น 2 คอลัมน์ หรือ 2 แถว โดยขยาย span ของเซลล์อื่นที่พาดผ่านเส้นใหม่
    if direction == "rows":
        h = ys[target["r"] + 1] - ys[target["r"]]
        if h < MIN_CELL_PT * 2:
            raise PDFError("ความสูงเซลล์น้อยเกินไปที่จะแยกเป็น 2 แถว")
        mid = round((ys[target["r"]] + ys[target["r"] + 1]) / 2, 2)
        split_at = target["r"] + 1
        ny = list(ys[:split_at]) + [mid] + list(ys[split_at:])
        new_cells = []
        moves = []
        for idx, cell in enumerate(cells):
            r, c, rs, cs = cell["r"], cell["c"], cell["rowspan"], cell["colspan"]
            if idx == target_idx:
                top_c = {"r": r, "c": c, "rowspan": 1, "colspan": cs}
                bot_c = {"r": r + 1, "c": c, "rowspan": 1, "colspan": cs}
                new_cells.extend([top_c, bot_c])
                moves.append((idx, top_c, False))
            elif r <= target["r"] < r + rs:
                nc = {"r": r, "c": c, "rowspan": rs + 1, "colspan": cs}
                new_cells.append(nc)
                moves.append((idx, nc, False))
            elif r > target["r"]:
                nc = {"r": r + 1, "c": c, "rowspan": rs, "colspan": cs}
                new_cells.append(nc)
                moves.append((idx, nc, False))
            else:
                nc = dict(cell)
                new_cells.append(nc)
                moves.append((idx, nc, False))
        new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
        return list(xs), ny, new_cells, moves

    w = xs[target["c"] + 1] - xs[target["c"]]
    if w < MIN_CELL_PT * 2:
        raise PDFError("ความกว้างเซลล์น้อยเกินไปที่จะแยกเป็น 2 คอลัมน์")
    mid = round((xs[target["c"]] + xs[target["c"] + 1]) / 2, 2)
    split_at = target["c"] + 1
    nx = list(xs[:split_at]) + [mid] + list(xs[split_at:])
    new_cells = []
    moves = []
    for idx, cell in enumerate(cells):
        r, c, rs, cs = cell["r"], cell["c"], cell["rowspan"], cell["colspan"]
        if idx == target_idx:
            left_c = {"r": r, "c": c, "rowspan": rs, "colspan": 1}
            right_c = {"r": r, "c": c + 1, "rowspan": rs, "colspan": 1}
            new_cells.extend([left_c, right_c])
            moves.append((idx, left_c, False))
        elif c <= target["c"] < c + cs:
            nc = {"r": r, "c": c, "rowspan": rs, "colspan": cs + 1}
            new_cells.append(nc)
            moves.append((idx, nc, False))
        elif c > target["c"]:
            nc = {"r": r, "c": c + 1, "rowspan": rs, "colspan": cs}
            new_cells.append(nc)
            moves.append((idx, nc, False))
        else:
            nc = dict(cell)
            new_cells.append(nc)
            moves.append((idx, nc, False))
    new_cells.sort(key=lambda cell: (cell["r"], cell["c"]))
    return nx, list(ys), new_cells, moves


def _compute_plan(
    xs: list[float],
    ys: list[float],
    cells: list[dict],
    op: TableStructureOp,
    r0: int,
    c0: int,
    r1: int,
    c1: int,
    position: str,
    direction: str,
):
    if op == "insert_row":
        return _plan_insert_row(xs, ys, cells, r0, position)
    if op == "delete_row":
        return _plan_delete_row(xs, ys, cells, r0)
    if op == "insert_col":
        return _plan_insert_col(xs, ys, cells, c0, position)
    if op == "delete_col":
        return _plan_delete_col(xs, ys, cells, c0)
    if op == "merge_cells":
        return _plan_merge_cells(xs, ys, cells, r0, c0, r1, c1)
    if op == "split_cell":
        return _plan_split_cell(xs, ys, cells, r0, c0, direction)
    raise PDFError(f"ไม่รองรับคำสั่งโครงสร้างตาราง: {op}")


def edit_table_structure(
    session: PDFSession,
    page_number: int,
    bbox: dict,
    op: TableStructureOp,
    r0: int,
    c0: int,
    r1: int | None = None,
    c1: int | None = None,
    position: str = "below",
    direction: str = "cols",
    allow_overlap: bool = False,
) -> dict:
    """แก้ไขโครงสร้างตาราง (เพิ่ม/ลบแถว, เพิ่ม/ลบคอลัมน์, รวม/แยกเซลล์) แล้ววาดตารางใหม่พร้อมเนื้อหาเดิม"""
    doc = require_unlocked(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
    page = doc[page_number]
    if page.rotation:
        raise PDFError("ยังแก้ตารางในหน้าที่หมุนไม่ได้ — หมุนหน้ากลับเป็นแนวเดิมก่อน")

    table = _match(page_tables(session, page), bbox)
    xs, ys, cells = table["xs"], table["ys"], table["cells"]
    nx, ny, new_cells, moves = _compute_plan(
        xs, ys, cells, op, r0, c0, r0 if r1 is None else r1, c0 if c1 is None else c1, position, direction
    )

    new_box = fitz.Rect(nx[0], ny[0], nx[-1], ny[-1])
    if not page.rect.contains(new_box + (1, 1, -1, -1)):
        raise PDFError("ตารางเกินขอบกระดาษ — ลองย่อขนาดตารางก่อนเพิ่มแถวหรือคอลัมน์")

    old_box = fitz.Rect(xs[0], ys[0], xs[-1], ys[-1])
    area = old_box + (-2, -2, 2, 2)

    overlaps = any(
        fitz.Rect(w[:4]).intersects(new_box) and not fitz.Rect(w[:4]).intersects(area)
        for w in _content_page(page).get_text("words")
    )
    if overlaps and not allow_overlap:
        raise TableOverlapError("ตารางหลังปรับโครงสร้างจะทับข้อความอื่นในหน้า")

    # อ่านเส้น/สีพื้นเดิมก่อนลบ
    inside, crossing = [], []
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"]).normalize()
        if r.x1 < area.x0 or r.x0 > area.x1 or r.y1 < area.y0 or r.y0 > area.y1:
            continue
        within = r.x0 >= area.x0 and r.x1 <= area.x1 and r.y0 >= area.y0 and r.y1 <= area.y1
        (inside if within else crossing).append(d)

    border_color, border_width, old_fills = _detect_table_style(inside, xs, ys, cells)

    # เตรียมสำเนาหน้าต้นทางสำหรับตัดเนื้อหาแต่ละเซลล์ที่ยังคงอยู่
    src = fitz.open()
    src.insert_pdf(doc, from_page=page_number, to_page=page_number, annots=False)
    base = src[0]
    base.clean_contents()
    _drop_degenerate_rects(src, base)
    pw, ph = base.rect.width, base.rect.height
    for rr in (
        fitz.Rect(0, 0, pw, area.y0),
        fitz.Rect(0, area.y1, pw, ph),
        fitz.Rect(0, area.y0, area.x0, area.y1),
        fitz.Rect(area.x1, area.y0, pw, area.y1),
    ):
        if rr.width > 0 and rr.height > 0:
            base.add_redact_annot(rr)
    base.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    base.add_redact_annot(area)
    base.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
        text=fitz.PDF_REDACT_TEXT_NONE,
    )

    for _ in moves[1:]:
        src.fullcopy_page(0)

    def old_rect_of(c: dict) -> fitz.Rect:
        return fitz.Rect(xs[c["c"]], ys[c["r"]], xs[c["c"] + c["colspan"]], ys[c["r"] + c["rowspan"]])

    contents: list[dict] = []
    for k, (old_idx, _target_cell, _preserve_pos) in enumerate(moves):
        sp = src[k]
        rect = old_rect_of(cells[old_idx])
        for rr in (
            fitz.Rect(0, 0, pw, rect.y0),
            fitz.Rect(0, rect.y1, pw, ph),
            fitz.Rect(0, rect.y0, rect.x0, rect.y1),
            fitz.Rect(rect.x1, rect.y0, pw, rect.y1),
        ):
            if rr.width > 0 and rr.height > 0:
                sp.add_redact_annot(rr)
        sp.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        _prune_empty_xobjects(src, sp)
        contents.append(_cell_content(sp, rect))

    # Map background fills to new cells
    new_fills: dict[tuple[int, int], tuple[float, ...]] = {}
    for old_idx, target_cell, _preserve_pos in moves:
        oc = cells[old_idx]
        fcol = old_fills.get((oc["r"], oc["c"]))
        if fcol and (target_cell["r"], target_cell["c"]) not in new_fills:
            new_fills[(target_cell["r"], target_cell["c"])] = fcol

    # ลบตารางเดิมแล้ววาดเส้นตารางใหม่ + คืนเส้นที่พาดผ่านขอบ
    page.add_redact_annot(area, fill=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    _prune_empty_xobjects(doc, page)
    _redraw(page, crossing)
    _draw_table_grid(page, nx, ny, new_cells, border_color, border_width, new_fills)

    # วางเนื้อหาของแต่ละเซลล์กลับเข้ากรอบใหม่
    for k, (old_idx, target_cell, preserve_pos) in enumerate(moves):
        cb = contents[k]["bbox"]
        if cb.is_empty:
            continue
        orect = old_rect_of(cells[old_idx])
        nrect = fitz.Rect(
            nx[target_cell["c"]],
            ny[target_cell["r"]],
            nx[target_cell["c"] + target_cell["colspan"]],
            ny[target_cell["r"] + target_cell["rowspan"]],
        )
        clip = (cb + (-0.5, -0.5, 0.5, 0.5)) & orect
        w, h = clip.width, clip.height
        if w <= 0 or h <= 0:
            continue
        if preserve_pos:
            # merge_cells: คงพิกัดเดิมภายในกรอบที่รวมไว้เพื่อไม่ให้ข้อความหลายเซลล์ซ้อนทับกัน
            page.show_pdf_page(clip, src, k, clip=clip, keep_proportion=False)
        else:
            h_mode = _align(cb.x0 - orect.x0, orect.x1 - cb.x1, orect.width)
            v_mode = _align(cb.y0 - orect.y0, orect.y1 - cb.y1, orect.height)
            scale = min(1.0, (nrect.width - 1) / w if w else 1.0, (nrect.height - 1) / h if h else 1.0)
            sw, sh = w * scale, h * scale
            x = _place(nrect.x0, nrect.x1, sw, cb.x0 - orect.x0, orect.x1 - cb.x1, h_mode)
            y = _place(nrect.y0, nrect.y1, sh, cb.y0 - orect.y0, orect.y1 - cb.y1, v_mode)
            page.show_pdf_page(fitz.Rect(x, y, x + sw, y + sh), src, k, clip=clip, keep_proportion=False)

    src.close()

    # ล้างทะเบียน text_edits เก่าที่ซ้อนกรอบตาราง แล้วอัปเดตทะเบียนตารางใหม่
    page_edits = session.text_edits.setdefault(page_number, {})
    stale = [
        e for e, rec in page_edits.items()
        if rec.get("kind") != "table"
        and fitz.Rect(*[rec["rect"][k] for k in ("x0", "y0", "x1", "y1")]).intersects(old_box)
    ]
    for edit_id in stale:
        page_edits.pop(edit_id, None)
    table_key = table["id"] if table["id"].startswith("table-") else f"table-{uuid.uuid4().hex[:10]}"
    page_edits[table_key] = {"kind": "table", "xs": nx, "ys": ny, "cells": new_cells}

    session.mark_dirty()
    return {
        "id": table_key,
        "xs": nx,
        "ys": ny,
        "cells": new_cells,
        "overlaps_content": overlaps,
    }
