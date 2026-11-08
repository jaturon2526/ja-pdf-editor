"""เขียนโครงเอกสาร (layout.PageLayout) เป็นไฟล์ Word — ฟอนต์ Sarabun ฝังในไฟล์"""
from __future__ import annotations

import io
import uuid
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Emu, Pt
from PIL import Image

from app.services.scan_docx.layout import PageLayout, Paragraph, Picture, Table

FONT = "Sarabun"
FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
FONT_FILES = {
    "regular": "Sarabun-Regular.ttf",
    "bold": "Sarabun-Bold.ttf",
    "italic": "Sarabun-Italic.ttf",
    "boldItalic": "Sarabun-BoldItalic.ttf",
}

_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.THAI_JUSTIFY,
}


def _set_run_font(rpr_parent, size: float | None = None, bold: bool | None = None, color: str | None = None) -> None:
    """ฟอนต์ทุกชุดอักษร (ascii/hAnsi/cs) + ขนาดทั้งปกติและ complex script — Word ใช้ cs กับอักษรไทย"""
    rpr = rpr_parent.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), FONT)
    if bold is not None:
        for tag in ("w:b", "w:bCs"):
            el = rpr.find(qn(tag))
            if bold and el is None:
                rpr.append(OxmlElement(tag))
            elif not bold and el is not None:
                rpr.remove(el)
    if size is not None:
        half = str(int(round(size * 2)))
        for tag in ("w:sz", "w:szCs"):
            el = rpr.find(qn(tag))
            if el is None:
                el = OxmlElement(tag)
                rpr.append(el)
            el.set(qn("w:val"), half)
    if color:
        el = rpr.find(qn("w:color"))
        if el is None:
            el = OxmlElement("w:color")
            # ลำดับใน rPr: rFonts, b, bCs, ..., color, ..., sz, szCs, ..., lang
            sz = rpr.find(qn("w:sz"))
            if sz is not None:
                sz.addprevious(el)
            else:
                rpr.append(el)
        el.set(qn("w:val"), color)
    lang = rpr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rpr.append(lang)
    lang.set(qn("w:val"), "en-US")
    lang.set(qn("w:bidi"), "th-TH")


def _setup_styles(doc) -> None:
    normal = doc.styles["Normal"]
    _set_run_font(normal.element, size=11)
    pf = normal.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    for name in ("Table Grid",):
        try:
            doc.styles[name]
        except KeyError:  # pragma: no cover
            pass


def _paragraph(container, p: Paragraph):
    para = container.add_paragraph()
    _fill_paragraph(para, p)
    return para


def _fill_paragraph(para, p: Paragraph) -> None:
    pf = para.paragraph_format
    pf.alignment = _ALIGN.get(p.align, WD_ALIGN_PARAGRAPH.LEFT)
    pf.left_indent = Pt(p.left) if p.left else None
    if p.first:
        pf.first_line_indent = Pt(p.first)
    pf.space_before = Pt(p.space_before)
    pf.space_after = Pt(0)
    if p.line:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(p.line)
    for t in p.tabs:
        align = {"left": WD_TAB_ALIGNMENT.LEFT, "right": WD_TAB_ALIGNMENT.RIGHT,
                 "center": WD_TAB_ALIGNMENT.CENTER}[t.align]
        leader = WD_TAB_LEADER.DOTS if t.leader == "dot" else WD_TAB_LEADER.SPACES
        pf.tab_stops.add_tab_stop(Pt(max(1.0, t.pos)), align, leader)
    for r in p.runs:
        run = para.add_run(r.text)
        _set_run_font(run._r, size=r.size, bold=r.bold, color=r.color)


def _picture_stream(img: Image.Image) -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf


def crop_picture(color: Image.Image, box, kind: str) -> Image.Image:
    x0, y0, x1, y1 = box
    pad = 3
    crop = color.crop((max(0, x0 - pad), max(0, y0 - pad), min(color.width, x1 + pad), min(color.height, y1 + pad)))
    rgb = crop.convert("RGB")
    # สีจริง (ตราประทับ/โลโก้สี) คงสีไว้ · ภาพขาวดำ/เทา → เทาหรือ 1 บิต ไฟล์เล็กและคม
    import numpy as np

    a = np.asarray(rgb).astype(np.int16)
    chroma = (a.max(axis=2) - a.min(axis=2))
    if (chroma > 40).mean() > 0.01:
        return rgb
    g = rgb.convert("L")
    ga = np.asarray(g)
    if ((ga < 40) | (ga > 215)).mean() > 0.97 or kind == "barcode":
        return g.point(lambda v: 255 if v > 140 else 0).convert("1")
    return g


def _add_picture_run(para, img: Image.Image, w_pt: float, h_pt: float):
    run = para.add_run()
    run.add_picture(_picture_stream(img), width=Pt(w_pt), height=Pt(h_pt))
    return run


def _make_floating(run, x_pt: float, y_pt: float, relative: str = "page") -> None:
    """แปลงรูปในบรรทัด (wp:inline) เป็นรูปลอยตำแหน่งตายตัวเทียบกับหน้ากระดาษ ไม่ดันข้อความ (wrapNone)"""
    inline = run._r.find(".//" + qn("wp:inline"))
    if inline is None:
        return
    extent = inline.find(qn("wp:extent"))
    cx, cy = extent.get("cx"), extent.get("cy")
    docpr = inline.find(qn("wp:docPr"))
    graphic = inline.find(qn("a:graphic"))
    anchor = parse_xml(
        f'<wp:anchor {nsdecls("wp", "a", "pic", "r")} distT="0" distB="0" distL="0" distR="0" simplePos="0" '
        f'relativeHeight="251659264" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
        f'<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="page"><wp:posOffset>{int(Emu(Pt(x_pt)))}</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="{relative}"><wp:posOffset>{int(Emu(Pt(y_pt)))}</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
        f'</wp:anchor>'
    )
    anchor.append(docpr)
    anchor.append(OxmlElement("wp:cNvGraphicFramePr"))
    anchor.append(graphic)
    inline.getparent().replace(inline, anchor)


def _table(doc_or_cell, t: Table, color: Image.Image):
    nrows, ncols = len(t.row_heights), len(t.col_widths)
    table = doc_or_cell.add_table(rows=nrows, cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    tblPr = table._tbl.tblPr
    # เยื้องตารางตามตำแหน่งเดิม + ขนาดคอลัมน์ตายตัว
    ind = OxmlElement("w:tblInd")
    ind.set(qn("w:w"), str(int(t.left * 20)))
    ind.set(qn("w:type"), "dxa")
    tblPr.append(ind)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    grid = table._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), t.col_widths):
        gc.set(qn("w:w"), str(int(w * 20)))
    for r, h in zip(table.rows, t.row_heights):
        trPr = r._tr.get_or_add_trPr()
        el = OxmlElement("w:trHeight")
        el.set(qn("w:val"), str(int(h * 20)))
        el.set(qn("w:hRule"), "atLeast")
        trPr.append(el)
        for c, w in zip(r.cells, t.col_widths):
            c.width = Pt(w)
    covered: set[tuple[int, int]] = set()
    for tc in sorted(t.cells, key=lambda c: (c.row, c.col)):
        if (tc.row, tc.col) in covered:
            continue      # ช่องนี้ถูกรวมไปกับช่องอื่นแล้ว (โครงตารางจากภาพซ้อนกัน)
        cell = table.cell(tc.row, tc.col)
        r2 = min(tc.row + tc.row_span, nrows)
        c2 = min(tc.col + tc.col_span, ncols)
        span = {(r, c) for r in range(tc.row, r2) for c in range(tc.col, c2)}
        if len(span) > 1 and not (span & covered):
            try:
                cell = cell.merge(table.cell(r2 - 1, c2 - 1))
                covered |= span
            except ValueError:  # รวมช่องไม่ได้ (โครงไม่เป็นสี่เหลี่ยม) → เขียนช่องเดี่ยว
                cell = table.cell(tc.row, tc.col)
                covered.add((tc.row, tc.col))
        else:
            covered.add((tc.row, tc.col))
        if tc.shade:
            tcPr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), tc.shade)
            tcPr.append(shd)
        first = cell.paragraphs[0]
        for k, p in enumerate(tc.paragraphs):
            para = first if k == 0 else cell.add_paragraph()
            _fill_paragraph(para, p)
        if not tc.paragraphs:
            _set_run_font(first.add_run("")._r, size=_cell_size(t))
    return table


def _cell_size(t: Table) -> float:
    for c in t.cells:
        for p in c.paragraphs:
            if p.runs:
                return p.runs[0].size
    return 11.0


def build_docx(pages: list[tuple[PageLayout, Image.Image]]) -> bytes:
    doc = Document()
    _setup_styles(doc)
    body = doc.element.body
    # ลบย่อหน้าว่างเริ่มต้น
    for p in list(body.findall(qn("w:p"))):
        body.remove(p)
    for i, (pl, color) in enumerate(pages):
        section = doc.sections[0] if i == 0 else doc.add_section(WD_SECTION.NEW_PAGE)
        section.page_width = Pt(pl.width)
        section.page_height = Pt(pl.height)
        l, t, r, b = pl.margins
        section.left_margin, section.top_margin = Pt(l), Pt(t)
        section.right_margin, section.bottom_margin = Pt(r), Pt(b)
        section.header_distance = Pt(min(18, t))
        section.footer_distance = Pt(min(18, b))
        _write_blocks(doc, pl, color)
        if i == 0 and len(pages) > 1:
            pass
    # add_section() แทรก sectPr ในย่อหน้าสุดท้ายของหน้าก่อน — หน้าที่ว่างเปล่า (ไม่มีบล็อก) ต้องมีย่อหน้าอย่างน้อยหนึ่งย่อหน้า
    buf = io.BytesIO()
    doc.save(buf)
    return embed_fonts(buf.getvalue(), used_styles(doc))


def _write_blocks(doc, pl: PageLayout, color: Image.Image) -> None:
    written: dict[int, object] = {}
    floats: list[Picture] = []
    last_para = None
    for b in pl.blocks:
        if isinstance(b, Picture) and b.floating:
            floats.append(b)
            continue
        if isinstance(b, Paragraph):
            last_para = _paragraph(doc, b)
            written[id(b)] = last_para
        elif isinstance(b, Table):
            if b.space_before:
                spacer = doc.add_paragraph()
                spacer.paragraph_format.space_before = Pt(max(0.0, b.space_before - 1))
                spacer.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
                spacer.paragraph_format.line_spacing = Pt(1)
                _set_run_font(spacer.add_run("")._r, size=1)
            _table(doc, b, color)
            last_para = None
        else:
            para = doc.add_paragraph()
            pf = para.paragraph_format
            pf.space_before = Pt(b.space_before)
            pf.alignment = _ALIGN.get(b.align, WD_ALIGN_PARAGRAPH.LEFT)
            if b.left:
                pf.left_indent = Pt(b.left)
            _add_picture_run(para, crop_picture(color, b.box, b.kind), b.w, b.h)
            last_para = para
    body = doc.element.body
    if last_para is None or len(body) == 0 or body[-1].tag != qn("w:p"):
        # หน้าต้องจบด้วยย่อหน้า (sectPr ของหน้าอยู่ในย่อหน้าสุดท้าย) — ย่อหน้าเล็กมากไม่กินที่
        last_para = doc.add_paragraph()
        _set_run_font(last_para.add_run("")._r, size=1)
        last_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        last_para.paragraph_format.line_spacing = Pt(1)
    for fp in floats:
        host = written.get(id(fp.host)) if fp.host is not None else None
        target = host if host is not None else last_para
        run = _add_picture_run(target, crop_picture(color, fp.box, fp.kind), fp.w, fp.h)
        if host is not None:
            _make_floating(run, fp.x, fp.rel_y, relative="paragraph")
        else:
            _make_floating(run, fp.x, fp.y)


def used_styles(doc) -> set[str]:
    styles = {"regular"}
    for b in doc.element.body.iter(qn("w:b")):
        styles.add("bold")
        break
    return styles


# ---------------------------------------------------------------- ฝังฟอนต์

def _obfuscate(data: bytes, key_guid: uuid.UUID) -> bytes:
    """ECMA-376 Part 1 §17.8.1 (Font Embedding): XOR 32 ไบต์แรกของฟอนต์ด้วยคีย์ที่ได้จาก GUID
    (ไบต์ของ GUID ในรูปข้อความ hex เรียงกลับหลัง)"""
    hexs = key_guid.hex  # 32 ตัวอักษร ตามลำดับที่เขียนใน fontKey
    key = bytes(int(hexs[i:i + 2], 16) for i in range(30, -2, -2))
    head = bytearray(data[:32])
    for i in range(32):
        head[i] ^= key[i % 16]
    return bytes(head) + data[32:]


def embed_fonts(docx: bytes, styles: set[str]) -> bytes:
    """ฝังฟอนต์ Sarabun (OFL อนุญาตให้ฝัง) — Word บนเครื่องที่ไม่มี Sarabun ยังแสดงฟอนต์เดิม"""
    src = zipfile.ZipFile(io.BytesIO(docx))
    files = {n: src.read(n) for n in src.namelist()}
    font_table = files["word/fontTable.xml"].decode("utf8")
    rels_name = "word/_rels/fontTable.xml.rels"
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    embeds = []
    for k, style in enumerate(sorted(styles)):
        tag = {"regular": "embedRegular", "bold": "embedBold", "italic": "embedItalic", "boldItalic": "embedBoldItalic"}[style]
        g = uuid.uuid4()
        data = (FONTS_DIR / FONT_FILES[style]).read_bytes()
        name = f"word/fonts/font{k + 1}.odttf"
        files[name] = _obfuscate(data, g)
        rid = f"rIdFont{k + 1}"
        rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/font" Target="fonts/font{k + 1}.odttf"/>')
        embeds.append(f'<w:{tag} r:id="{rid}" w:fontKey="{{{str(g).upper()}}}"/>')
    rels.append("</Relationships>")
    files[rels_name] = "".join(rels).encode("utf8")
    entry = (f'<w:font w:name="{FONT}"><w:charset w:val="DE"/><w:family w:val="swiss"/><w:pitch w:val="variable"/>'
             + "".join(embeds) + "</w:font>")
    if 'xmlns:r=' not in font_table.split(">", 2)[1]:
        font_table = font_table.replace("<w:fonts ", '<w:fonts xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    font_table = font_table.replace("</w:fonts>", entry + "</w:fonts>")
    files["word/fontTable.xml"] = font_table.encode("utf8")
    settings = files["word/settings.xml"].decode("utf8")
    if "embedTrueTypeFonts" not in settings:
        # ต้องอยู่ต้น ๆ ของ settings ตามลำดับ schema (หลัง w:view/w:zoom/w:removePersonalInformation...)
        import re

        m = re.search(r"<w:zoom[^>]*/>", settings)
        ins = "<w:embedTrueTypeFonts/><w:saveSubsetFonts/>"
        if m:
            settings = settings[:m.end()] + ins + settings[m.end():]
        else:
            settings = re.sub(r"(<w:settings[^>]*>)", r"\1" + ins, settings, count=1)
        files["word/settings.xml"] = settings.encode("utf8")
    ct = files["[Content_Types].xml"].decode("utf8")
    if 'Extension="odttf"' not in ct:
        ct = ct.replace("<Types ", "<Types ", 1).replace(
            "</Types>", '<Default Extension="odttf" ContentType="application/vnd.openxmlformats-officedocument.obfuscatedFont"/></Types>')
        files["[Content_Types].xml"] = ct.encode("utf8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in src.namelist():
            z.writestr(n, files[n])
        for n in files:
            if n not in src.namelist():
                z.writestr(n, files[n])
    return out.getvalue()
