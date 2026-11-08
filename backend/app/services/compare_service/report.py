"""รายงานผลเปรียบเทียบเป็น PDF — หน้าสรุป (จำนวน + ตารางจุดต่าง) แล้วหน้าคู่ A | B เคียงข้างพร้อมไฮไลต์และเลขจุดต่าง

ข้อความไทยใช้ fitz.Story (HTML + ฟอนต์ Sarabun, จัดรูปด้วย HarfBuzz) ตัดหน้าให้เอง · ภาพหน้าเอกสารใส่เป็น JPEG
(หน้าที่หมุนแล้วแสดงตรงกับในแอป และพิกัดจุดต่างใช้ได้ตรง ๆ)
"""
from __future__ import annotations

import html
import io
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import fitz
from PIL import Image

from app.core.config import settings

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
A4 = fitz.paper_rect("a4")
A4_LAND = fitz.paper_rect("a4-l")
MARGIN = 36
RENDER_DPI = 110

# สีต่อชนิด (RGB 0–1) — ตรงกับหน้าเว็บ
COLORS = {
    "delete": (0.86, 0.15, 0.15), "insert": (0.09, 0.64, 0.29), "replace": (0.92, 0.55, 0.05),
    "visual": (0.55, 0.27, 0.80), "page_insert": (0.09, 0.64, 0.29), "page_delete": (0.86, 0.15, 0.15),
    "page_size": (0.92, 0.55, 0.05),
}
LABELS = {
    "insert": "เพิ่มข้อความ", "delete": "ลบข้อความ", "replace": "แก้ไขข้อความ", "visual": "ภาพ/กราฟิกต่างกัน",
    "page_insert": "หน้าที่เพิ่ม", "page_delete": "หน้าที่ถูกลบ", "page_size": "ขนาดหน้าเปลี่ยน",
}


def _css() -> str:
    return """
    @font-face { font-family: sarabun; src: url(Sarabun-Regular.ttf); }
    @font-face { font-family: sarabun; src: url(Sarabun-Bold.ttf); font-weight: bold; }
    * { font-family: sarabun; font-size: 10pt; }
    h1 { font-size: 17pt; margin: 0 0 4pt 0; }
    p.meta { color: #555; margin: 0 0 2pt 0; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 0.5pt solid #bbb; padding: 2pt 4pt; vertical-align: top; text-align: left; }
    th { background-color: #f1f5f9; }
    td.del { color: #b91c1c; } td.ins { color: #15803d; }
    span.sw { font-weight: bold; }
    """


def _summary_html(result: dict, name_a: str, name_b: str, max_rows: int) -> str:
    s = result["summary"]
    now = datetime.now(ZoneInfo(settings.APP_TIMEZONE)).strftime("%d/%m/%Y %H:%M")
    counts = " · ".join(f"{LABELS[k]} {s[k]}" for k in LABELS if s.get(k))
    rows = []
    for c in result["changes"][:max_rows]:
        pa = ", ".join(sorted({str(r["page"] + 1) for r in c["a_rects"]})) or (
            str(c["a_anchor"]["page"] + 1) if c.get("a_anchor") else "-")
        pb = ", ".join(sorted({str(r["page"] + 1) for r in c["b_rects"]})) or (
            str(c["b_anchor"]["page"] + 1) if c.get("b_anchor") else "-")
        color = "#%02x%02x%02x" % tuple(int(v * 255) for v in COLORS[c["kind"]])
        rows.append(
            f"<tr><td>{c['id']}</td><td><span class='sw' style='color:{color}'>{LABELS[c['kind']]}</span></td>"
            f"<td>{pa}</td><td>{pb}</td><td class='del'>{html.escape(c['a_text'][:300])}</td>"
            f"<td class='ins'>{html.escape((c['b_text'] or c.get('note') or '')[:300])}</td></tr>")
    more = len(result["changes"]) - max_rows
    notes = "".join(f"<p class='meta'>หมายเหตุ: {html.escape(n)}</p>" for n in result.get("notes", []))
    ocr = []
    for side, name in (("a", "ไฟล์เดิม"), ("b", "ไฟล์ใหม่")):
        if result[side]["ocr_pages"]:
            ocr.append(f"{name} หน้า {', '.join(str(p + 1) for p in result[side]['ocr_pages'])}")
    ocr_note = f"<p class='meta'>อ่านข้อความจากภาพ (OCR): {' · '.join(ocr)} — อาจคลาดเคลื่อนได้</p>" if ocr else ""
    body = (
        "<h1>รายงานเปรียบเทียบเอกสาร</h1>"
        f"<p class='meta'>ไฟล์เดิม (A): <b>{html.escape(name_a)}</b> · {result['a']['pages']} หน้า</p>"
        f"<p class='meta'>ไฟล์ใหม่ (B): <b>{html.escape(name_b)}</b> · {result['b']['pages']} หน้า</p>"
        f"<p class='meta'>สร้างเมื่อ {now} น. · JA PDF Editor</p>{ocr_note}{notes}"
    )
    if result["identical"]:
        return body + "<p><b>ไม่พบจุดต่าง</b> — ข้อความและภาพของทั้งสองไฟล์ตรงกัน</p>"
    body += f"<p><b>พบ {s['total']} จุดต่าง</b> — {counts}</p>"
    body += ("<table><tr><th>#</th><th>ชนิด</th><th>หน้า A</th><th>หน้า B</th><th>เดิม (A)</th><th>ใหม่ (B)</th></tr>"
             + "".join(rows) + "</table>")
    if more > 0:
        body += f"<p class='meta'>…และอีก {more} จุด (ดูได้ในหน้าเปรียบเทียบของแอป)</p>"
    return body


def _story_pages(html_body: str) -> bytes:
    story = fitz.Story(html=html_body, user_css=_css(), archive=str(FONT_DIR))
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    more = True
    while more:
        dev = writer.begin_page(A4)
        more, _ = story.place(A4 + (MARGIN, MARGIN, -MARGIN, -MARGIN))
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()


def _page_image(doc: fitz.Document, pno: int) -> bytes:
    pix = doc[pno].get_pixmap(dpi=RENDER_DPI, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=80)
    return out.getvalue()


def _label(page: fitz.Page, point: fitz.Point, text: str, color) -> None:
    w = 5 + 5 * len(text)
    box = fitz.Rect(point.x, point.y - 9, point.x + w, point.y)
    page.draw_rect(box, color=color, fill=color)
    page.insert_text((box.x0 + 2, box.y1 - 2), text, fontsize=7, color=(1, 1, 1), fontname="helv")


def _text(page: fitz.Page, rect: fitz.Rect, text: str, size: float, color: str = "#000") -> None:
    """ข้อความไทยบนหน้ารายงาน (จัดสระ/วรรณยุกต์ถูกต้อง — insert_text ธรรมดาไม่จัดรูปอักษรไทย)"""
    page.insert_htmlbox(rect, f"<p style='font-size:{size}pt;color:{color};margin:0'>{html.escape(text)}</p>",
                        css=_css(), archive=fitz.Archive(str(FONT_DIR)))


def _draw_side(out_page: fitz.Page, frame: fitz.Rect, doc: Optional[fitz.Document], pno: Optional[int],
               size, marks: list[tuple[int, str, dict]], caption: str) -> None:
    _text(out_page, fitz.Rect(frame.x0, frame.y0 - 14, frame.x1, frame.y0), caption, 8, "#555")
    if doc is None or pno is None:
        out_page.draw_rect(frame, color=(0.8, 0.8, 0.8), dashes="[3] 0", width=0.5)
        return
    w, h = size
    k = min(frame.width / w, frame.height / h)
    target = fitz.Rect(frame.x0, frame.y0, frame.x0 + w * k, frame.y0 + h * k)
    out_page.insert_image(target, stream=_page_image(doc, pno))
    out_page.draw_rect(target, color=(0.75, 0.75, 0.75), width=0.5)
    for cid, kind, r in marks:
        rect = fitz.Rect(target.x0 + r["x0"] * k, target.y0 + r["y0"] * k, target.x0 + r["x1"] * k, target.y0 + r["y1"] * k)
        color = COLORS[kind]
        if rect.width < 2:
            rect.x0 -= 1
            rect.x1 += 1
        out_page.draw_rect(rect, color=color, fill=color, fill_opacity=0.18, width=0.8)
        _label(out_page, fitz.Point(rect.x0, rect.y0), str(cid), color)


def build_report(doc_a: fitz.Document, doc_b: fitz.Document, result: dict, name_a: str, name_b: str,
                 max_rows: int = 400) -> bytes:
    out = fitz.open("pdf", _story_pages(_summary_html(result, name_a, name_b, max_rows)))
    by_page: dict[tuple[str, int], list] = {}
    for c in result["changes"]:
        for side in ("a", "b"):
            rects = c[f"{side}_rects"] or ([c[f"{side}_anchor"]] if c.get(f"{side}_anchor") else [])
            for r in rects:
                by_page.setdefault((side, r["page"]), []).append((c["id"], c["kind"], r))
    gap = 18
    frame_w = (A4_LAND.width - 2 * MARGIN - gap) / 2
    for pa, pb in result["pairs"]:
        marks_a = by_page.get(("a", pa), []) if pa is not None else []
        marks_b = by_page.get(("b", pb), []) if pb is not None else []
        if not marks_a and not marks_b:
            continue  # คู่หน้าที่ตรงกันทั้งหมด ไม่ต้องใส่ในรายงาน
        page = out.new_page(width=A4_LAND.width, height=A4_LAND.height)
        title = (f"หน้า {pa + 1 if pa is not None else '-'} (A) กับหน้า {pb + 1 if pb is not None else '-'} (B)"
                 f" · {len({m[0] for m in marks_a + marks_b})} จุดต่าง")
        _text(page, fitz.Rect(MARGIN, MARGIN - 22, A4_LAND.width - MARGIN, MARGIN), title, 11)
        top = MARGIN + 16
        frame_a = fitz.Rect(MARGIN, top, MARGIN + frame_w, A4_LAND.height - MARGIN)
        frame_b = fitz.Rect(frame_a.x1 + gap, top, frame_a.x1 + gap + frame_w, A4_LAND.height - MARGIN)
        _draw_side(page, frame_a, doc_a, pa, result["a"]["page_sizes"][pa] if pa is not None else None, marks_a,
                   f"เดิม (A): {name_a[:60]}" + ("" if pa is not None else " — ไม่มีหน้านี้"))
        _draw_side(page, frame_b, doc_b, pb, result["b"]["page_sizes"][pb] if pb is not None else None, marks_b,
                   f"ใหม่ (B): {name_b[:60]}" + ("" if pb is not None else " — หน้านี้ถูกลบ"))
    out.set_metadata({"title": f"เปรียบเทียบ {name_a} กับ {name_b}", "producer": "JA PDF Editor", "creator": "JA PDF Editor"})
    return out.tobytes(garbage=3, deflate=True)
