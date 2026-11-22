"""pdf_service.forms — อ่านและกรอกแบบฟอร์ม PDF (AcroForm: Text / Checkbox / Radio / Dropdown / Listbox)"""
from __future__ import annotations

from typing import Any

import fitz

from app.core.session import PDFSession
from app.services.pdf_service.core import (
    PDFError,
    _flush_mupdf_warnings,
    has_digital_signatures,
    require_unlocked,
)

FORM_MAX_VALUE_LEN = 5000

_SUPPORTED_TYPES: dict[int, str] = {
    fitz.PDF_WIDGET_TYPE_TEXT: "text",
    fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio",
    fitz.PDF_WIDGET_TYPE_COMBOBOX: "dropdown",
    fitz.PDF_WIDGET_TYPE_LISTBOX: "listbox",
}


def _normalize_choice_options(raw_choices: Any) -> list[dict[str, str]]:
    """แปลง widget.choice_values เป็น [{"value": ..., "label": ...}]"""
    if not raw_choices:
        return []
    out: list[dict[str, str]] = []
    for item in raw_choices:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append({"value": str(item[0]), "label": str(item[1])})
        elif isinstance(item, (list, tuple)) and len(item) == 1:
            val = str(item[0])
            out.append({"value": val, "label": val})
        else:
            val = str(item)
            out.append({"value": val, "label": val})
    return out


def _widget_is_checked(widget: fitz.Widget) -> bool:
    val = widget.field_value
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    s = str(val).strip()
    return bool(s) and s.lower() not in {"off", "false", "0", "no"}


def _widget_value(widget: fitz.Widget, kind: str) -> str | bool:
    if kind in {"checkbox", "radio"}:
        return _widget_is_checked(widget)
    val = widget.field_value
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return "" if val is None else str(val)


def _visible_rect(page: fitz.Page, rect: fitz.Rect) -> dict[str, float]:
    """แปลง rect ของ widget เป็นพิกัดที่มองเห็นบนหน้า (รองรับหน้าหมุน/CropBox)"""
    cb = page.cropbox
    shifted = fitz.Rect(rect.x0 - cb.x0, rect.y0 - cb.y0, rect.x1 - cb.x0, rect.y1 - cb.y0)
    vis = shifted * page.rotation_matrix
    return {
        "x0": round(float(vis.x0), 2),
        "y0": round(float(vis.y0), 2),
        "x1": round(float(vis.x1), 2),
        "y1": round(float(vis.y1), 2),
    }


def list_form_fields(session: PDFSession) -> list[dict]:
    """คืนรายการช่องกรอกฟอร์ม AcroForm ทั้งหมดในเอกสาร (เรียงตามหน้าและตำแหน่งบน-ซ้าย)"""
    doc = require_unlocked(session)
    fields: list[dict] = []
    for page_idx in range(doc.page_count):
        page = doc[page_idx]
        widgets = list(page.widgets() or [])
        for w in widgets:
            kind = _SUPPORTED_TYPES.get(w.field_type)
            if not kind:
                continue
            flags = int(w.field_flags or 0)
            read_only = bool(flags & fitz.PDF_FIELD_IS_READ_ONLY)
            multiline = bool(kind == "text" and (flags & fitz.PDF_TX_FIELD_IS_MULTILINE))
            label = (w.field_label or "").strip() or (w.field_name or "").strip() or f"ช่องที่ {len(fields) + 1}"
            on_state = None
            if kind in {"checkbox", "radio"}:
                try:
                    raw_on = w.on_state()
                    on_state = str(raw_on) if raw_on else "Yes"
                except Exception:
                    on_state = "Yes"
            fields.append(
                {
                    "xref": int(w.xref),
                    "page": page_idx,
                    "name": str(w.field_name or f"field_{w.xref}"),
                    "label": label,
                    "type": kind,
                    "rect": _visible_rect(page, w.rect),
                    "value": _widget_value(w, kind),
                    "multiline": multiline,
                    "read_only": read_only,
                    "max_len": int(w.text_maxlen) if getattr(w, "text_maxlen", 0) else None,
                    "options": _normalize_choice_options(w.choice_values) if kind in {"dropdown", "listbox"} else [],
                    "on_state": on_state,
                }
            )
    fields.sort(key=lambda f: (f["page"], round(f["rect"]["y0"], 1), round(f["rect"]["x0"], 1)))
    return fields


def _apply_widget_value(widget: fitz.Widget, kind: str, value: str | bool) -> bool:
    """กำหนดค่าให้ widget แล้วเรียก update() — คืน True ถ้าค่าเปลี่ยนแปลงจริง"""
    old_val = _widget_value(widget, kind)
    if kind == "checkbox":
        target_bool = bool(value)
        if old_val == target_bool:
            return False
        on_val = widget.on_state() or True
        widget.field_value = on_val if target_bool else False
        widget.update()
        return True

    if kind == "radio":
        target_bool = bool(value)
        if old_val == target_bool:
            return False
        if target_bool:
            widget.field_value = widget.on_state() or "Yes"
            widget.update()
            return True
        widget.field_value = False
        widget.update()
        return True

    text_val = "" if value is None else str(value)
    if len(text_val) > FORM_MAX_VALUE_LEN:
        raise PDFError(f"ข้อความในช่องฟอร์มยาวเกิน {FORM_MAX_VALUE_LEN} ตัวอักษร")
    if old_val == text_val:
        return False
    widget.field_value = text_val
    widget.update()
    return True


def fill_form_fields(session: PDFSession, updates: list[dict]) -> int:
    """บันทึกค่าลงช่องกรอกฟอร์ม AcroForm ตามรายการ updates ([{xref, page, value}])

    คืนจำนวนฟิลด์ที่เปลี่ยนแปลงจริง (0 = no-op ไม่ต้อง push_history)
    """
    if session.signed_pdf_bytes is not None:
        raise PDFError(
            "เอกสารนี้มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว ไม่สามารถแก้ไขแบบฟอร์มได้ "
            "เพราะจะทำให้ลายเซ็นดิจิทัลใช้งานไม่ได้"
        )
    doc = require_unlocked(session)
    if has_digital_signatures(doc):
        raise PDFError(
            "เอกสารนี้มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว ไม่สามารถแก้ไขแบบฟอร์มได้ "
            "เพราะจะทำให้ลายเซ็นดิจิทัลใช้งานไม่ได้"
        )

    if not updates:
        return 0

    # จัดกลุ่มตามหน้าเพื่อลดการวน widgets ซ้ำ
    by_page: dict[int, list[dict]] = {}
    for item in updates:
        page_idx = int(item["page"])
        if not (0 <= page_idx < doc.page_count):
            raise PDFError(f"เลขหน้า {page_idx + 1} อยู่นอกช่วง (มีทั้งหมด {doc.page_count} หน้า)")
        by_page.setdefault(page_idx, []).append(item)

    changed_count = 0
    for page_idx, page_updates in by_page.items():
        page = doc[page_idx]
        widgets_by_xref = {int(w.xref): w for w in (page.widgets() or [])}
        for item in page_updates:
            xref = int(item["xref"])
            widget = widgets_by_xref.get(xref)
            if widget is None:
                continue
            kind = _SUPPORTED_TYPES.get(widget.field_type)
            if not kind:
                continue
            if int(widget.field_flags or 0) & fitz.PDF_FIELD_IS_READ_ONLY:
                continue
            if _apply_widget_value(widget, kind, item.get("value")):
                changed_count += 1

    if changed_count > 0:
        session.mark_dirty()
        _flush_mupdf_warnings(f"fill_form_fields session={session.session_id}")
    return changed_count


def _guard_form_edit(session: PDFSession) -> fitz.Document:
    if session.signed_pdf_bytes is not None:
        raise PDFError(
            "เอกสารนี้มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว ไม่สามารถแก้ไขแบบฟอร์มได้ "
            "เพราะจะทำให้ลายเซ็นดิจิทัลใช้งานไม่ได้"
        )
    doc = require_unlocked(session)
    if has_digital_signatures(doc):
        raise PDFError(
            "เอกสารนี้มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว ไม่สามารถแก้ไขแบบฟอร์มได้ "
            "เพราะจะทำให้ลายเซ็นดิจิทัลใช้งานไม่ได้"
        )
    return doc


def _unrotated_rect(page: fitz.Page, rect: dict) -> fitz.Rect:
    vis = fitz.Rect(rect["x0"], rect["y0"], rect["x1"], rect["y1"]).normalize()
    if vis.width < 10 or vis.height < 10:
        raise PDFError("ขนาดช่องแบบฟอร์มเล็กเกินไป (ต้องกว้างและสูงอย่างน้อย 10 pt)")
    derot = vis * page.derotation_matrix
    cb = page.cropbox
    return fitz.Rect(
        derot.x0 + cb.x0,
        derot.y0 + cb.y0,
        derot.x1 + cb.x0,
        derot.y1 + cb.y0,
    ) & page.mediabox


def add_form_field(
    session: PDFSession,
    page_number: int,
    field_type: str,
    rect: dict,
    name: str = "",
    label: str = "",
    multiline: bool = False,
    options: list[str] | None = None,
) -> dict:
    """สร้างช่องกรอกแบบฟอร์ม AcroForm ใหม่ลงหน้าเอกสาร (v1.47.0) — คืนข้อมูลฟิลด์ที่สร้าง"""
    doc = _guard_form_edit(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"เลขหน้า {page_number + 1} อยู่นอกช่วง (มีทั้งหมด {doc.page_count} หน้า)")

    page = doc[page_number]
    target_rect = _unrotated_rect(page, rect)
    clean_label = (label or "").strip() or (name or "").strip() or "ช่องกรอกข้อมูล"
    clean_name = (name or "").strip()
    if not clean_name:
        import uuid
        clean_name = f"field_{uuid.uuid4().hex[:8]}"

    widget = fitz.Widget()
    widget.rect = target_rect
    widget.field_name = clean_name
    widget.field_label = clean_label
    widget.border_color = (0.39, 0.45, 0.55)
    widget.border_width = 1.0
    widget.fill_color = (0.97, 0.99, 1.0)
    widget.text_color = (0.06, 0.09, 0.16)
    widget.text_fontsize = 11

    if field_type == "text":
        widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_value = ""
        if multiline:
            widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
    elif field_type == "checkbox":
        widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        widget.field_value = False
    elif field_type == "radio":
        widget.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
        widget.field_value = False
    elif field_type == "dropdown":
        clean_opts = [o.strip() for o in (options or []) if o and o.strip()]
        if not clean_opts:
            raise PDFError("กรุณาระบุตัวเลือกอย่างน้อย 1 รายการสำหรับดรอปดาวน์")
        widget.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
        widget.choice_values = clean_opts
        widget.field_value = clean_opts[0]
    else:
        raise PDFError(f"ไม่รองรับชนิดช่องแบบฟอร์ม: {field_type}")

    page.add_widget(widget)
    session.mark_dirty()
    _flush_mupdf_warnings(f"add_form_field session={session.session_id}")

    all_fields = list_form_fields(session)
    for f in all_fields:
        if f["page"] == page_number and f["xref"] == int(widget.xref):
            return f
    return all_fields[-1]


def delete_form_field(session: PDFSession, page_number: int, xref: int) -> bool:
    """ลบช่องกรอกแบบฟอร์ม AcroForm ตาม xref บนหน้าที่ระบุ (v1.47.0)"""
    doc = _guard_form_edit(session)
    if not (0 <= page_number < doc.page_count):
        raise PDFError(f"เลขหน้า {page_number + 1} อยู่นอกช่วง (มีทั้งหมด {doc.page_count} หน้า)")
    page = doc[page_number]
    target = next((w for w in (page.widgets() or []) if int(w.xref) == int(xref)), None)
    if target is None:
        raise PDFError("ไม่พบช่องแบบฟอร์มที่ต้องการลบ")
    page.delete_widget(target)
    session.mark_dirty()
    _flush_mupdf_warnings(f"delete_form_field session={session.session_id}")
    return True
