"""ตรวจฟอนต์ในเอกสาร (Font Inspector — v1.38.0, ผู้ใช้ขอ 2026-11-20)

- ``font_table(page)``: ข้อมูลฟอนต์ของหน้า (ชนิด / ฝัง / subset) จาก ``page.get_fonts()`` จับคู่ด้วยชื่อที่ตัด subset prefix
  (ชื่อใน span ของ PyMuPDF ไม่มี prefix ``ABCDEF+`` อยู่แล้ว)
- ``summarize_spans(...)``: สรุปชุดฟอนต์/ขนาด/สีในย่อหน้า (ใช้ใน ``TextBlock.source_fonts`` ของโหมดแก้ไข)
- ``page_spans(page)``: ข้อความระดับ span พร้อมกรอบ ให้เครื่องมือ "ตรวจฟอนต์" ชี้/แตะดูได้
- ``document_fonts(doc)``: รายการฟอนต์ทั้งเอกสาร (แบบ Acrobat › คุณสมบัติ › ฟอนต์) พร้อมหน้าที่ใช้

ขนาดที่แสดงคือขนาดของ span ตามที่ PDF ระบุ (รวมสเกลของ text matrix แล้ว) — ไม่ใช่ขนาดที่ประมาณจากความสูงกรอบ
ซึ่ง get_text_blocks ใช้เป็นค่าเริ่มต้นของการแก้ไข (ฟอนต์แต่ละตัวมีสัดส่วน em ต่างกัน)
"""
from __future__ import annotations

import re
from collections import OrderedDict

import fitz

_SUBSET = re.compile(r"^[A-Z]{6}\+")
_FONT_TYPES = {
    "Type0": "Type 0 (CID)",
    "TrueType": "TrueType",
    "Type1": "Type 1",
    "MMType1": "Type 1 (Multiple Master)",
    "Type3": "Type 3",
    "CIDFontType0": "Type 0 (CID)",
    "CIDFontType2": "Type 0 (CID)",
}
# ฟอนต์มาตรฐาน 14 ตัวของ PDF — โปรแกรมอ่านทุกตัวมีให้ จึงไม่ต้องฝัง
_BASE14 = {
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", "Symbol", "ZapfDingbats",
}


def strip_subset(name: str) -> str:
    return _SUBSET.sub("", name or "")


def _key(name: str) -> str:
    """ชื่อสำหรับจับคู่ — ชื่อใน span ของ MuPDF กับ BaseFont อาจต่างกันแค่ช่องว่าง/ขีด ("Sarabun Regular" ↔ "Sarabun-Regular")"""
    return re.sub(r"[\s\-_,]+", "", strip_subset(name)).lower()


def _hex(color: int) -> str:
    return f"#{int(color or 0) & 0xFFFFFF:06x}"


def _round_size(size: float) -> float:
    return round(float(size or 0) * 2) / 2  # ปัดครึ่ง pt — ค่าทศนิยมยาวจากการสเกลหน้าไม่มีความหมายกับผู้ใช้


def same_family(pdf_font_name: str, system_font_key: str) -> bool:
    """ฟอนต์ในไฟล์เป็นตระกูลเดียวกับฟอนต์ระบบ (key เช่น "sarabun-bold") หรือไม่ — "Sarabun-Regular" ใช่, "THSarabunNew" ไม่ใช่"""
    family = re.split(r"-(?:bold|italic|bolditalic|regular)$", (system_font_key or "").lower())[0]
    return bool(family) and _key(pdf_font_name).startswith(_key(family))


def font_table(page: fitz.Page) -> dict[str, dict]:
    """ชื่อฟอนต์ (คีย์จาก ``_key``) → {name, type, embedded, subset, base14}"""
    out: dict[str, dict] = {}
    for _xref, ext, ftype, basefont, _ref, encoding, *_ in page.get_fonts(full=True):
        name = strip_subset(basefont)
        info = out.setdefault(_key(name), {
            "name": name,
            "type": _FONT_TYPES.get(ftype, ftype or "ไม่ทราบ"),
            "embedded": False,
            "subset": False,
            "base14": name in _BASE14,
            "encoding": encoding or "",
        })
        info["embedded"] = info["embedded"] or (ext not in ("n/a", "", None))
        info["subset"] = info["subset"] or bool(_SUBSET.match(basefont or ""))
    return out


def _span_entry(span: dict, table: dict[str, dict]) -> dict:
    name = strip_subset(span.get("font", ""))
    flags = int(span.get("flags", 0))
    info = table.get(_key(name), {})
    return {
        "name": name or "(ไม่มีชื่อ)",
        "size": _round_size(span.get("size", 0)),
        "color": _hex(span.get("color", 0)),
        "bold": bool(flags & (1 << 4)) or "bold" in name.lower(),
        "italic": bool(flags & (1 << 1)) or any(k in name.lower() for k in ("italic", "oblique")),
        "type": info.get("type", ""),
        "embedded": info.get("embedded", False),
        "subset": info.get("subset", False),
        "base14": info.get("base14", False),
    }


def summarize_spans(span_chars: list[tuple[dict, int]], table: dict[str, dict]) -> list[dict]:
    """[(span, จำนวนตัวอักษร)] → ชุดฟอนต์ที่ไม่ซ้ำ (ชื่อ+ขนาด+สี+หนา/เอียง) เรียงจากใช้มากไปน้อย พร้อม ``chars``"""
    merged: OrderedDict[tuple, dict] = OrderedDict()
    for span, count in span_chars:
        entry = _span_entry(span, table)
        key = (entry["name"], entry["size"], entry["color"], entry["bold"], entry["italic"])
        if key in merged:
            merged[key]["chars"] += count
        else:
            merged[key] = {**entry, "chars": count}
    return sorted(merged.values(), key=lambda e: -e["chars"])


def page_spans(page: fitz.Page) -> list[dict]:
    """span ของเนื้อหน้า (ไม่รวม annotation) → [{bbox, text, font…}] สำหรับเครื่องมือตรวจฟอนต์"""
    from app.services import thai_text
    from app.services.pdf_service.text_index import content_page

    text_page = content_page(page)
    table = font_table(text_page)
    raw = thai_text.normalize_page_dict(text_page.get_text("dict"), text_page)
    out = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text.strip():
                    continue
                x0, y0, x1, y1 = span["bbox"]
                out.append({"bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}, "text": text.strip(),
                            **_span_entry(span, table)})
    return out


def document_fonts(doc: fitz.Document) -> list[dict]:
    """ฟอนต์ทั้งเอกสาร รวมตามชื่อ+ชนิด → [{name, type, embedded, subset, base14, encoding, pages:[1-based]}]"""
    fonts: OrderedDict[tuple, dict] = OrderedDict()
    for pno in range(doc.page_count):
        for key_name, info in font_table(doc[pno]).items():
            key = (key_name, info["type"])
            entry = fonts.setdefault(key, {**info, "name": info["name"] or "(ไม่มีชื่อ)", "pages": []})
            entry["embedded"] = entry["embedded"] or info["embedded"]
            entry["subset"] = entry["subset"] or info["subset"]
            if not entry["pages"] or entry["pages"][-1] != pno + 1:
                entry["pages"].append(pno + 1)
    return sorted(fonts.values(), key=lambda e: e["name"].lower())
