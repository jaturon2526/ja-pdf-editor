"""แปลง PDF เป็น Word แบบ "รักษาหน้าตา" (preserve layout)

เหมาะกับ PDF ที่ออกแบบเป็นกราฟิก (Canva/Figma/PowerPoint) ซึ่งการแปลงแบบปกติ (pdf2docx) สร้างโครงสร้าง
ย่อหน้า/ตารางใหม่ได้ไม่ตรงต้นฉบับ วิธีนี้ทำต่อหน้าดังนี้:

1. ภาพพื้นหลัง: เรนเดอร์หน้าเป็นภาพโดย "ลบเฉพาะตัวอักษร" ออก (redaction แบบไม่ระบายสี ไม่แตะรูป/เส้น)
   แล้ววางเป็นรูปลอยอยู่หลังข้อความ เต็มหน้ากระดาษ — กราฟิก สี gradient กล่องมน ฯลฯ จึงเหมือนต้นฉบับ
2. ข้อความ: ทุกบรรทัดเป็นกล่องข้อความวางตำแหน่งตายตัว (framed paragraph) ตรงพิกัดเดิม พร้อมฟอนต์/ขนาด/
   สี/ตัวหนาเดิม — แก้ไขข้อความใน Word ได้ (แต่ไม่ไหลต่อกันแบบเอกสารปกติ)
3. แถบไฮไลต์/เส้นใต้ที่ PDF วาดเป็นรูปทรง ถูกย้ายจากภาพพื้นหลังมาเป็นรูปแบบตัวอักษร (w:highlight/w:shd, w:u)
   เพราะเครื่องที่เปิดมักไม่มีฟอนต์ต้นฉบับ ความยาวข้อความจึงต่างจาก PDF — ถ้าแถบติดอยู่ในภาพจะยาว/สั้นไม่เท่าข้อความ

ข้อจำกัด: ถ้าพิมพ์ข้อความยาวขึ้นมาก กล่องจะล้นทับกราฟิกข้างเคียง (เหมาะกับการแก้คำ/กรอกช่องว่าง)
"""
from __future__ import annotations

import io
import logging

import fitz
from docx import Document
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Emu, Pt, RGBColor

from app.services import thai_text
from app.services.pdf2docx_fixes import (
    fix_symbol_chars,
    normalize_font_name,
    phantom_space_flags,
)

logger = logging.getLogger("layout_docx")

_BG_DPI = 150
_JPEG_QUALITY = 85
_EMU_PER_PT = 12700
_TWIPS_PER_PT = 20


def _erase_fills(pix: fitz.Pixmap, items: list, scale: float) -> fitz.Pixmap:
    """ลบแถบสี (ไฮไลต์) ออกจากภาพหน้าที่เรนเดอร์แล้ว โดยเติมสีพื้นรอบ ๆ แถบแทน

    ใช้แทนการลบรูปทรงใน PDF เพราะ Word/LibreOffice มักวาดแถบหลายช่วงเป็น path เดียว (เช่น ช่องว่างหลัง bullet
    ต่อกับแถบใต้ข้อความ) ซึ่ง MuPDF ลบแบบ "อยู่ในกรอบทั้งหมด" ไม่ได้ · พิกเซลที่เป็นสีแถบ หรือสีผสมระหว่างสีแถบกับ
    สีพื้น (ขอบ anti-alias) ถูกเปลี่ยนเป็นสีพื้น ส่วนเส้น/ขอบตารางสีเข้มที่ทับอยู่ไม่ถูกแตะ
    """
    if not items:
        return pix
    w, h, n, stride = pix.width, pix.height, pix.n, pix.stride
    buf = bytearray(pix.samples)

    def px(x, y):
        o = y * stride + x * n
        return buf[o], buf[o + 1], buf[o + 2]

    for rect, rgb in items:
        x0 = max(0, int(rect.x0 * scale) - 1); y0 = max(0, int(rect.y0 * scale) - 1)
        x1 = min(w - 1, int(rect.x1 * scale) + 1); y1 = min(h - 1, int(rect.y1 * scale) + 1)
        if x1 <= x0 or y1 <= y0:
            continue
        # สีพื้นรอบแถบ: สีที่พบบ่อยที่สุดในขอบนอก 2 px (ไม่นับสีแถบ) — ไม่พบใช้สีขาว
        counts: dict = {}
        sums: dict = {}
        ring = [(x, yy) for x in range(max(0, x0 - 2), min(w, x1 + 3)) for yy in (y0 - 2, y0 - 1, y1 + 1, y1 + 2) if 0 <= yy < h]
        ring += [(xx, y) for y in range(y0, y1 + 1) for xx in (x0 - 2, x0 - 1, x1 + 1, x1 + 2) if 0 <= xx < w]
        for x, y in ring:
            c = px(x, y)
            if sum((a - b) ** 2 for a, b in zip(c, rgb)) > 80 ** 2:
                key = (c[0] // 8, c[1] // 8, c[2] // 8)
                counts[key] = counts.get(key, 0) + 1
                acc = sums.setdefault(key, [0, 0, 0])
                acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]
        if counts:
            k = max(counts, key=counts.get)
            bg = tuple(round(v / counts[k]) for v in sums[k])     # ค่าเฉลี่ยจริงของกลุ่มสีที่พบบ่อยสุด
        else:
            bg = (255, 255, 255)
        d = [a - b for a, b in zip(rgb, bg)]
        dd = sum(v * v for v in d) or 1
        for y in range(y0, y1 + 1):
            row = y * stride
            for x in range(x0, x1 + 1):
                o = row + x * n
                e = (buf[o] - bg[0], buf[o + 1] - bg[1], buf[o + 2] - bg[2])
                t = (e[0] * d[0] + e[1] * d[1] + e[2] * d[2]) / dd       # 0 = สีพื้น, 1 = สีแถบ
                if t < 0.12:
                    continue
                res = sum((e[i] - t * d[i]) ** 2 for i in range(3))     # ห่างจากเส้นผสมสีแถบ↔พื้นแค่ไหน
                if res < 40 ** 2:
                    buf[o], buf[o + 1], buf[o + 2] = bg
    return fitz.Pixmap(pix.colorspace, w, h, bytes(buf), False)


def _background_jpeg(page: fitz.Page, erase: list | None = None, strokes: list | None = None) -> bytes:
    """ภาพหน้าที่ลบเฉพาะตัวอักษร (และแถบไฮไลต์/เส้นใต้ที่ย้ายไปเป็นรูปแบบตัวอักษรแล้ว) ออก

    รูปภาพ เส้นตาราง และสีพื้นอยู่ครบ — ไฮไลต์/เส้นใต้ต้องลบออกจากภาพ เพราะใน Word ข้อความใช้ฟอนต์ของเครื่อง
    ที่เปิด (เช่น Mac ไม่มี Norasi) ความยาวข้อความจึงไม่เท่าต้นฉบับ แถบที่ติดอยู่ในภาพจะยาวเกิน/สั้นกว่าข้อความ
    erase: [(rect, rgb)] แถบสีที่จะลบจากภาพ · strokes: [rect] เส้นใต้ที่วาดเป็นเส้น (ลบใน PDF ก่อนเรนเดอร์)
    """
    tmp = fitz.open()
    tmp.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    p = tmp[0]
    if strokes:
        # เส้น (stroke): ลบแบบ "แตะ" ด้วยกรอบแคบ ๆ ตามแนวเส้นพอดี (MuPDF ไม่นับเส้นว่า "อยู่ในกรอบ")
        for rect in strokes:
            r = fitz.Rect(rect)
            p.add_redact_annot(fitz.Rect(r.x0 + 0.2, r.y0 - 0.3, r.x1 - 0.2, r.y1 + 0.3), fill=False)
        p.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
            text=fitz.PDF_REDACT_TEXT_NONE,
        )
    for block in p.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    p.add_redact_annot(fitz.Rect(span["bbox"]), fill=False)
    p.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )
    pix = p.get_pixmap(dpi=_BG_DPI, alpha=False, annots=False)
    pix = _erase_fills(pix, erase or [], _BG_DPI / 72.0)
    data = pix.tobytes("jpeg", jpg_quality=_JPEG_QUALITY)
    tmp.close()
    return data


# ---------- ข้อความ: แถว → กล่องข้อความ พร้อมไฮไลต์/เส้นใต้เป็นรูปแบบตัวอักษร ----------
_WS = " \u00a0\t"


def _text_rows(raw: dict) -> list[dict]:
    """rawdict → แถวข้อความ [{"box": (x0,y0,x1,y1), "chars": [(char, span)]}]

    รวมบรรทัดของบล็อกเดียวกันที่อยู่แถวเดียวกันและชิด/ซ้อนกัน (PyMuPDF มักแยก "หมายเหตุ" กับ " :" เป็นคนละบรรทัด
    ที่ซ้อนกัน) ลบช่องว่างปลอมที่วางทับตัวอักษร และตัดช่องว่างหัว/ท้ายแถว (กล่องเริ่มที่ตัวอักษรตัวแรกจริง)
    """
    rows = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        groups: list[list[dict]] = []
        for line in sorted(block.get("lines", []), key=lambda ln: (round(ln["bbox"][1]), ln["bbox"][0])):
            d = line.get("dir", (1, 0))
            if abs(d[1]) > 1e-3 or d[0] <= 0:
                groups.append([line])
                continue
            for g in groups:
                gb = g[0]["bbox"]
                h = min(gb[3] - gb[1], line["bbox"][3] - line["bbox"][1])
                if (abs(g[0].get("dir", (1, 0))[1]) < 1e-3
                        and min(gb[3], line["bbox"][3]) - max(gb[1], line["bbox"][1]) >= 0.5 * h
                        and max(line["bbox"][0] - max(ln["bbox"][2] for ln in g),
                                min(ln["bbox"][0] for ln in g) - line["bbox"][2]) <= 0.2 * h):  # ต่อ/ซ้อนกันจริง ไม่ใช่คนละคอลัมน์
                    g.append(line)
                    break
            else:
                groups.append([line])
        for g in groups:
            g.sort(key=lambda ln: ln["bbox"][0])
            items = [(ch, span) for ln in g for span in ln.get("spans", []) for ch in span.get("chars", [])]
            items = [it for it in items if it[0]["c"]]
            drop = phantom_space_flags([ch for ch, _ in items])
            items = [it for it, d in zip(items, drop) if not d]
            while items and items[0][0]["c"] in _WS:
                items.pop(0)
            while items and items[-1][0]["c"] in _WS:
                items.pop()
            items = _space_gaps(items)
            if not items:
                continue
            y0 = min(ln["bbox"][1] for ln in g)
            y1 = max(ln["bbox"][3] for ln in g)
            x0 = min(ch["bbox"][0] for ch, _ in items)
            x1 = max(ch["bbox"][2] for ch, _ in items)
            rows.append({"box": (x0, y0, x1, y1), "chars": items})
    return rows


def _space_gaps(items: list) -> list:
    """ใส่ช่องว่างตรงที่ตัวอักษรห่างกันชัดเจนแต่ไม่มีช่องว่างจริง (เช่น bullet กับข้อความที่ PDF วางด้วยการเว้นระยะ)"""
    out = []
    for item in items:
        if out:
            prev, cur = out[-1][0], item[0]
            size = item[1].get("size", 10) or 10
            if (prev["c"] not in _WS and cur["c"] not in _WS
                    and cur["bbox"][0] - prev["bbox"][2] > 0.25 * size):
                out.append(({"c": " ", "bbox": (prev["bbox"][2], prev["bbox"][1], cur["bbox"][0], prev["bbox"][3])},
                            out[-1][1]))
        out.append(item)
    return out


def _rgb(color) -> tuple[int, int, int]:
    return tuple(max(0, min(255, round(c * 255))) for c in color[:3])


def _decorations(page: fitz.Page, rows: list[dict]):
    """แถบไฮไลต์และเส้นใต้ที่วาดเป็นรูปทรงใน PDF
    → (ไฮไลต์ [(rect, rgb)], เส้นใต้ [(rect, rgb, เป็นเส้น stroke)], แถบที่ต้องลบจากภาพ [(rect, rgb)])

    ไฮไลต์: พื้นสีอ่อน (ไม่ขาว) สูงไม่เกิน ~1 บรรทัด พอดีกับตัวอักษรที่อยู่ข้างบน · เส้นใต้: เส้นแนวนอนบาง ๆ ที่ช่วงล่าง
    ของแถวข้อความ และไม่ยาวเกินข้อความ (เส้นขอบตาราง/เส้นคั่นยาวกว่าข้อความจึงยังอยู่ในภาพพื้นหลัง)
    """
    highlights, underlines = [], []
    drawings = page.get_drawings()
    fills = [(fitz.Rect(d["rect"]), d["fill"]) for d in drawings if d.get("fill")]

    def on_same_color(r, fill) -> bool:
        """อยู่บนพื้นสีเดียวกันที่ใหญ่กว่า (Word วาดพื้นช่องตาราง + พื้นย่อหน้าในช่องซ้อนกัน) — ไม่ใช่ไฮไลต์"""
        return any(o != r and o.contains(r) and max(abs(a - b) for a, b in zip(f, fill)) < 0.02 for o, f in fills)

    for dr in drawings:
        r = fitz.Rect(dr["rect"])
        if r.width <= 1:
            continue
        fill = dr.get("fill")
        if fill and (dr.get("fill_opacity") or 1) >= 0.5 and r.height >= 3:
            lum = 0.299 * fill[0] + 0.587 * fill[1] + 0.114 * fill[2]
            if lum >= 0.5 and min(fill) < 0.93 and not on_same_color(r, fill):
                inside = [ch for row in rows
                          if min(r.y1, row["box"][3]) - max(r.y0, row["box"][1]) >= 0.5 * (row["box"][3] - row["box"][1])
                          and r.height <= 1.6 * (row["box"][3] - row["box"][1])
                          for ch, _ in row["chars"]
                          if r.x0 - 0.5 <= (ch["bbox"][0] + ch["bbox"][2]) / 2 <= r.x1 + 0.5]
                # ไฮไลต์จะพอดีกับตัวอักษร — พื้นช่องตารางมีระยะขอบเกินข้อความ จึงคงไว้ในภาพพื้นหลัง
                if (inside and r.x0 >= min(ch["bbox"][0] for ch in inside) - 2.5
                        and r.x1 <= max(ch["bbox"][2] for ch in inside) + 2.5):
                    highlights.append((r, _rgb(fill)))
                    continue
        thin = r.height <= 1.6
        color = dr.get("color") if dr.get("type") == "s" else fill
        if thin and color is not None and r.width > 2:
            y = (r.y0 + r.y1) / 2
            for row in rows:
                x0, y0, x1, y1 = row["box"]
                if not (y0 + 0.55 * (y1 - y0) <= y <= y1 + 2):
                    continue
                if r.x0 >= x0 - 2 and r.x1 <= x1 + 2 and r.x1 > x0 and r.x0 < x1:
                    underlines.append((r, _rgb(color), dr.get("type") == "s"))
                    break
    # แถบที่ต้องลบจากภาพ: ไฮไลต์ + ช่วงสีเดียวกันที่ต่อติดกันในแถวเดียวกัน (เช่น ช่องว่างระหว่าง bullet กับข้อความ)
    erase = list(highlights)
    for r, fill in fills:
        rgb = _rgb(fill)
        if any(r == e for e, _ in erase):
            continue
        for e, c in highlights:
            if (c == rgb and abs(r.y0 - e.y0) <= 3 and abs(r.y1 - e.y1) <= 3
                    and (abs(r.x1 - e.x0) <= 1 or abs(r.x0 - e.x1) <= 1)):
                erase.append((r, rgb))
                break
    erase += [(r, rgb) for r, rgb, stroke in underlines if not stroke]
    return highlights, underlines, erase


_WORD_HIGHLIGHTS = {
    (255, 255, 0): "yellow", (0, 255, 0): "green", (0, 255, 255): "cyan",
    (255, 0, 255): "magenta", (192, 192, 192): "lightGray",
}


def _char_marks(ch: dict, row_box, highlights, underlines):
    cx = (ch["bbox"][0] + ch["bbox"][2]) / 2
    hl = next((rgb for r, rgb in highlights
               if r.x0 - 0.5 <= cx <= r.x1 + 0.5 and r.y0 - 1 <= (row_box[1] + row_box[3]) / 2 <= r.y1 + 1), None)
    ul = next((rgb for r, rgb, _ in underlines
               if r.x0 - 0.5 <= cx <= r.x1 + 0.5 and row_box[1] <= (r.y0 + r.y1) / 2 <= row_box[3] + 2), None)
    return hl, ul


def _apply_marks(run, hl, ul) -> None:
    rpr = run._r.get_or_add_rPr()
    if hl is not None:
        name = _WORD_HIGHLIGHTS.get(tuple(hl))
        if name:
            el = OxmlElement("w:highlight")
            el.set(qn("w:val"), name)
        else:
            el = OxmlElement("w:shd")
            el.set(qn("w:val"), "clear")
            el.set(qn("w:color"), "auto")
            el.set(qn("w:fill"), "{:02X}{:02X}{:02X}".format(*hl))
        rpr.append(el)
    if ul is not None:
        el = OxmlElement("w:u")
        el.set(qn("w:val"), "single")
        if tuple(ul) != (0, 0, 0):
            el.set(qn("w:color"), "{:02X}{:02X}{:02X}".format(*ul))
        rpr.append(el)


def _anchor_behind_text(inline, width_emu: int, height_emu: int, shape_id: int):
    """แปลงรูปแบบ inline (ที่ python-docx สร้าง) เป็นรูปลอยหลังข้อความ ชิดมุมซ้ายบนของหน้า"""
    graphic = inline.find(qn("a:graphic"))
    doc_pr = inline.find(qn("wp:docPr"))
    anchor = parse_xml(
        f'<wp:anchor {nsdecls("wp", "a", "pic", "r")} distT="0" distB="0" distL="0" distR="0" simplePos="0" '
        f'relativeHeight="0" behindDoc="1" locked="1" layoutInCell="1" allowOverlap="1">'
        f'<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{width_emu}" cy="{height_emu}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:wrapNone/>'
        f'<wp:docPr id="{shape_id}" name="{doc_pr.get("name") if doc_pr is not None else "Background"}"/>'
        f'<wp:cNvGraphicFramePr/>'
        f'</wp:anchor>'
    )
    anchor.append(graphic)
    inline.getparent().replace(inline, anchor)


def _frame(paragraph, x_pt: float, y_pt: float, w_pt: float, h_pt: float) -> None:
    """ตั้งย่อหน้าเป็นกล่องข้อความตำแหน่งตายตัวบนหน้า (w:framePr)"""
    ppr = paragraph._p.get_or_add_pPr()
    fp = OxmlElement("w:framePr")
    fp.set(qn("w:w"), str(max(1, int(w_pt * _TWIPS_PER_PT))))
    fp.set(qn("w:h"), str(max(1, int(h_pt * _TWIPS_PER_PT))))
    fp.set(qn("w:hRule"), "atLeast")
    fp.set(qn("w:wrap"), "none")
    fp.set(qn("w:hAnchor"), "page")
    fp.set(qn("w:vAnchor"), "page")
    fp.set(qn("w:x"), str(int(x_pt * _TWIPS_PER_PT)))
    fp.set(qn("w:y"), str(int(y_pt * _TWIPS_PER_PT)))
    ppr.insert(0, fp)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)


def _style_run(run, span: dict) -> None:
    size = max(1.0, round(span.get("size", 11) * 2) / 2)
    run.font.size = Pt(size)
    color = span.get("color", 0)
    run.font.color.rgb = RGBColor((color >> 16) & 255, (color >> 8) & 255, color & 255)
    flags = span.get("flags", 0)
    bold = bool(flags & 16) or "bold" in span.get("font", "").lower()
    italic = bool(flags & 2) or "italic" in span.get("font", "").lower()
    run.bold = bold
    run.italic = italic
    latin, thai = normalize_font_name(span.get("font", ""))
    rpr = run._r.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    if latin:
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia"):
            fonts.set(qn(attr), latin)
        fonts.set(qn("w:cs"), thai or latin)
    # ค่า complex script ที่ Word ใช้กับอักษรไทย (ดู pdf2docx_fixes.normalize_docx_fonts)
    for tag, val in (("w:szCs", str(int(size * 2))),):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        rpr.append(el)
    if bold:
        rpr.append(OxmlElement("w:bCs"))
    if italic:
        rpr.append(OxmlElement("w:iCs"))
    lang = OxmlElement("w:lang")
    lang.set(qn("w:bidi"), "th-TH")
    rpr.append(lang)


def _setup_section(section, page: fitz.Page) -> None:
    section.page_width = Emu(int(page.rect.width * _EMU_PER_PT))
    section.page_height = Emu(int(page.rect.height * _EMU_PER_PT))
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, 0)
    section.header_distance = 0
    section.footer_distance = 0


def convert_pdf_to_layout_docx(pdf_bytes: bytes, progress_callback=None) -> bytes:
    """คืนไบต์ไฟล์ .docx แบบรักษาหน้าตา (ดูคำอธิบายหัวไฟล์)"""
    document = Document()
    body_style = document.styles["Normal"]
    body_style.paragraph_format.space_after = Pt(0)
    body_style.paragraph_format.space_before = Pt(0)

    with fitz.open("pdf", pdf_bytes) as pdf:
        if pdf.needs_pass:
            raise ValueError("ไฟล์มีรหัสผ่าน กรุณาปลดรหัสผ่านก่อนแปลง")
        total = pdf.page_count
        for index, page in enumerate(pdf):
            section = document.sections[0] if index == 0 else document.add_section(WD_SECTION.NEW_PAGE)
            _setup_section(section, page)
            width_emu = int(page.rect.width * _EMU_PER_PT)
            height_emu = int(page.rect.height * _EMU_PER_PT)

            # จัดรูปข้อความไทยทีละบรรทัด (ข้าม span ได้ — วรรณยุกต์/สระอำมักถูกแยกไปอีก span)
            raw = thai_text.normalize_page_dict(page.get_text("rawdict"), page)
            rows = _text_rows(raw)
            highlights, underlines, erase = _decorations(page, rows)

            anchor_par = document.paragraphs[-1] if index == 0 and document.paragraphs else document.add_paragraph()
            run = anchor_par.add_run()
            background = _background_jpeg(page, erase, [r for r, _, st in underlines if st])
            run.add_picture(io.BytesIO(background), width=Emu(width_emu), height=Emu(height_emu))
            inline = run._r.find(qn("w:drawing")).find(qn("wp:inline"))
            _anchor_behind_text(inline, width_emu, height_emu, shape_id=1000 + index)
            anchor_par.paragraph_format.space_after = Pt(0)

            for row in rows:
                x0, y0, x1, y1 = row["box"]
                par = document.add_paragraph()
                # เผื่อความกว้าง 15% กันคำล้นบรรทัดเมื่อเครื่องที่เปิดใช้ฟอนต์ต่างจากต้นฉบับเล็กน้อย
                _frame(par, x0, y0, (x1 - x0) * 1.15 + 4, y1 - y0)
                pieces: list[list] = []      # [text, span, hl, ul]
                for ch, span in row["chars"]:
                    hl, ul = _char_marks(ch, row["box"], highlights, underlines)
                    if pieces and pieces[-1][1] is span and pieces[-1][2] == hl and pieces[-1][3] == ul:
                        pieces[-1][0] += ch["c"]
                    else:
                        pieces.append([ch["c"], span, hl, ul])
                for text, span, hl, ul in pieces:
                    run = par.add_run(text)
                    _style_run(run, span)
                    _apply_marks(run, hl, ul)
            if progress_callback:
                progress_callback(10 + int((index + 1) / max(1, total) * 85))

    fix_symbol_chars(document)   # bullet ฟอนต์ Symbol/Wingdings/OpenSymbol (U+F0xx) → Unicode
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()
