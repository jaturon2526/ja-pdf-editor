"""pdf_service.pdfa — บันทึกเป็น PDF/A (ISO 19005) สำหรับเก็บเอกสารระยะยาว: PDF/A-1b, PDF/A-2b, PDF/A-3b

ขั้นตอน (ทำกับสำเนา เอกสารใน session ไม่ถูกแตะ):
1. ไฮไลต์ → วาดเป็นแถบสีทึบ "ใต้" เนื้อหา (ไม่ใช้ blend mode — PDF/A-1 ห้ามความโปร่งใส ถ้าเหลืออยู่ Ghostscript
   จะแปลงทั้งหน้าเป็นรูปจนค้นหาข้อความไม่ได้) · กล่องข้อความ → วาดตัวหนังสือเป็นเวกเตอร์
2. Ghostscript รวม annotation/ช่องฟอร์มที่เหลือลงเนื้อหน้า (PDF/A ต้องมี appearance ครบและห้ามฟอร์มที่ต้องสร้าง
   หน้าตาใหม่ตอนเปิด) แล้วใส่ลิงก์คืนพร้อม print flag (PDF/A บังคับ — ไม่มี Ghostscript จะทิ้งลิงก์)
3. Ghostscript -dPDFA=n: ฝังฟอนต์ทุกตัว, OutputIntent sRGB (ICC ที่มากับ pikepdf), XMP pdfaid, Document ID,
   รูปไม่ลดความละเอียด/ไม่บีบแบบเสียคุณภาพ
4. ตรวจผลลัพธ์ตามข้อกำหนดหลักของ ISO 19005 (verify_pdfa) — ไม่ผ่าน = ไม่บันทึก
   (ใน CI ตรวจซ้ำด้วย veraPDF ตัวตรวจมาตรฐานของ PDF Association — ดู tests/test_pdfa.py)

PDF/A ห้ามเข้ารหัส: เอกสารที่ตั้งรหัสผ่านไว้ต้องลบรหัสผ่านก่อน · เอกสารที่มีลายเซ็นดิจิทัล: ไม่รองรับ (ลายเซ็นจะใช้ไม่ได้)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import fitz
import pikepdf

from app.core.config import settings
from app.core.session import PDFSession
from app.services.pdf_service.core import PDFError, has_digital_signatures, require_unlocked, save_working_copy
from app.services.pdf_service.optimize import (_burn_freetext, _restore_links, _run_ghostscript, _saved_links,
                                               pages_with_changed_text)

import logging

logger = logging.getLogger("pdf_service")

PDFA_PARTS = {"pdfa-1b": 1, "pdfa-2b": 2, "pdfa-3b": 3}
_ICC = Path(pikepdf.__file__).parent / "pdfa" / "data" / "sRGB.icc"
_PRINT, _HIDDEN, _INVISIBLE, _NOVIEW = 4, 2, 1, 32


def _pdfa_def_ps(path: str, icc_path: str) -> None:
    """PDFA_def.ps ของ Ghostscript (OutputIntent + โปรไฟล์ ICC) — ไม่ใส่ /Title ทับชื่อเรื่องเดิมของเอกสาร"""
    icc = str(icc_path).replace("\\", "/").replace("(", "\\(").replace(")", "\\)")
    Path(path).write_text(f"""%!
/ICCProfile ({icc}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} <<
  /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {{icc_PDFA}}
  /OutputConditionIdentifier (sRGB IEC61966-2.1) /Info (sRGB IEC61966-2.1)
>> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFA}} ] >> /PUT pdfmark
""", encoding="ascii")


def _highlights_under_content(doc: fitz.Document) -> None:
    """ไฮไลต์ (โปร่งใส/Multiply) → แถบสีทึบวาดใต้เนื้อหาเดิม: ตัวอักษรอยู่บนแถบสีเหมือนเดิม โดยไม่มีความโปร่งใส"""
    for page in doc:
        items = []
        for annot in page.annots():
            if annot.type[0] != fitz.PDF_ANNOT_HIGHLIGHT:
                continue
            color = (annot.colors or {}).get("stroke") or (1, 0.92, 0.3)
            verts = annot.vertices or []
            quads = [fitz.Quad(verts[i:i + 4]) for i in range(0, len(verts) - 3, 4)] or [fitz.Rect(annot.rect).quad]
            items.append((annot, color, quads))
        for annot, color, quads in items:
            for q in quads:
                page.draw_quad(q, color=None, fill=color, overlay=False)
            page.delete_annot(annot)


def _flatten_image_alpha(doc: fitz.Document) -> int:
    """PDF/A-1 ห้ามรูปโปร่งใส (SMask) — เติมพื้นขาวใต้รูป (เหมือนที่เห็นบนกระดาษขาว) แทนที่จะปล่อยให้ Ghostscript
    แปลงทั้งหน้าเป็นรูปจนค้นหาข้อความไม่ได้ · คืนจำนวนรูปที่แก้"""
    import io
    from PIL import Image

    done = set()
    for page in doc:
        for info in page.get_images(full=True):
            xref, smask = info[0], info[1]
            if not smask or xref in done:
                continue
            done.add(xref)
            base = fitz.Pixmap(doc, xref)
            if base.alpha:
                base = fitz.Pixmap(base, 0)
            if base.colorspace and base.colorspace.n not in (1, 3):
                base = fitz.Pixmap(fitz.csRGB, base)
            mask = fitz.Pixmap(doc, smask)
            mode = "L" if base.n == 1 else "RGB"
            img = Image.frombytes(mode, (base.width, base.height), base.samples)
            alpha = Image.frombytes("L", (mask.width, mask.height), mask.samples)
            if alpha.size != img.size:
                alpha = alpha.resize(img.size)
            white = Image.new(mode, img.size, 255 if mode == "L" else (255, 255, 255))
            white.paste(img, (0, 0), alpha)
            buf = io.BytesIO()
            white.save(buf, "PNG")
            page.replace_image(xref, stream=buf.getvalue())
    return len(done)


def _links_printable(path_in: str, path_out: str) -> None:
    """ลิงก์: ตั้ง print flag (PDF/A บังคับ) และเอาการกระทำที่ PDF/A ห้าม (JavaScript, Launch) ออก"""
    with pikepdf.open(path_in) as pdf:
        for page in pdf.pages:
            annots = page.obj.get("/Annots")
            if annots is None:
                continue
            kept = []
            for a in annots:
                if a.get("/Subtype") != pikepdf.Name.Link:
                    continue
                action = a.get("/A")
                if action is not None and action.get("/S") in (pikepdf.Name.JavaScript, pikepdf.Name.Launch):
                    continue
                a.F = (int(a.get("/F", 0)) | _PRINT) & ~(_HIDDEN | _INVISIBLE | _NOVIEW)
                kept.append(a)
            if kept:
                page.obj.Annots = pikepdf.Array(kept)
            else:
                del page.obj["/Annots"]
        for key in ("/AcroForm", "/OpenAction", "/AA"):
            if key in pdf.Root and (key != "/OpenAction" or _is_script(pdf.Root.OpenAction)):
                del pdf.Root[key]
        names = pdf.Root.get("/Names")
        if names is not None:
            for key in ("/JavaScript", "/EmbeddedFiles"):
                if key in names:
                    del names[key]
        pdf.save(path_out)


def _is_script(action) -> bool:
    return isinstance(action, pikepdf.Dictionary) and action.get("/S") in (pikepdf.Name.JavaScript, pikepdf.Name.Launch)


def _text_chars(path: str) -> list[int]:
    doc = fitz.open(path)
    try:
        return [len(p.get_text().strip()) for p in doc]
    finally:
        doc.close()


# ---------------------------------------------------------------------------------------------------------------
# ตรวจผลลัพธ์ตาม ISO 19005 (ข้อกำหนดหลักที่ตรวจได้ด้วยโครงสร้างไฟล์)
# ---------------------------------------------------------------------------------------------------------------
_ALLOWED_ANNOTS = {
    1: {"/Text", "/Link", "/FreeText", "/Line", "/Square", "/Circle", "/Highlight", "/Underline", "/Squiggly",
        "/StrikeOut", "/Stamp", "/Ink", "/Popup", "/Widget", "/PrinterMark", "/TrapNet"},
}
_ALLOWED_ANNOTS[2] = _ALLOWED_ANNOTS[1] | {"/Polygon", "/PolyLine", "/Caret", "/FileAttachment", "/Redact",
                                           "/Watermark"}
_ALLOWED_ANNOTS[3] = _ALLOWED_ANNOTS[2]


def verify_pdfa(path, part: int) -> list[str]:
    """รายการข้อที่ไม่ผ่าน (ว่าง = ผ่าน)"""
    errors: list[str] = []
    with pikepdf.open(path) as pdf:
        if pdf.is_encrypted:
            errors.append("ไฟล์ถูกเข้ารหัส (6.1.3)")
        if part == 1 and pdf.pdf_version != "1.4":
            errors.append(f"PDF/A-1 ต้องเป็น PDF 1.4 (ได้ {pdf.pdf_version})")
        if part >= 2 and pdf.pdf_version not in ("1.4", "1.5", "1.6", "1.7"):
            errors.append(f"PDF/A-{part} ต้องเป็น PDF ไม่เกิน 1.7 (ได้ {pdf.pdf_version})")
        if "/ID" not in pdf.trailer:
            errors.append("ไม่มี Document ID ใน trailer (6.1.3)")

        meta = pdf.open_metadata()
        if str(meta.get("pdfaid:part", "")) != str(part) or str(meta.get("pdfaid:conformance", "")).upper() != "B":
            errors.append("XMP ไม่ระบุ pdfaid:part/conformance ตรงกับที่เลือก (6.7.11)")
        title_info = str(pdf.docinfo["/Title"]) if "/Title" in pdf.docinfo else None
        title_xmp = meta.get("dc:title")
        if title_info and title_xmp is not None and str(title_xmp) != title_info:
            errors.append("ชื่อเรื่องใน Document Info กับ XMP ไม่ตรงกัน (6.7.3)")

        intents = pdf.Root.get("/OutputIntents") or []
        if not any(i.get("/S") == pikepdf.Name("/GTS_PDFA1") and isinstance(i.get("/DestOutputProfile"), pikepdf.Stream)
                   for i in intents):
            errors.append("ไม่มี OutputIntent GTS_PDFA1 พร้อมโปรไฟล์ ICC (6.2.2)")

        acro = pdf.Root.get("/AcroForm")
        if acro is not None and (bool(acro.get("/NeedAppearances", False)) or "/XFA" in acro):
            errors.append("ฟอร์มต้องสร้างหน้าตาใหม่ตอนเปิด (NeedAppearances/XFA) (6.9)")
        names = pdf.Root.get("/Names")
        if names is not None and "/JavaScript" in names:
            errors.append("มี JavaScript (6.6.1)")
        if names is not None and "/EmbeddedFiles" in names and part < 3:
            errors.append(f"PDF/A-{part} ห้ามแนบไฟล์ (6.1.7)")
        if part == 1 and "/OCProperties" in pdf.Root:
            errors.append("PDF/A-1 ห้ามเลเยอร์ (6.1.13)")
        if "/AA" in pdf.Root:
            errors.append("มี Additional Actions ในแคตตาล็อก (6.6.2)")

        for no, page in enumerate(pdf.pages, 1):
            if part == 1 and page.obj.get("/Group") is not None and page.obj.Group.get("/S") == pikepdf.Name.Transparency:
                errors.append(f"หน้า {no}: มี transparency group (6.4)")
            for a in page.obj.get("/Annots") or []:
                sub = str(a.get("/Subtype"))
                if sub not in _ALLOWED_ANNOTS[part]:
                    errors.append(f"หน้า {no}: annotation {sub} ไม่อนุญาต (6.5.2)")
                    continue
                if sub == "/Popup":
                    continue
                flags = int(a.get("/F", 0))
                if not flags & _PRINT or flags & (_HIDDEN | _INVISIBLE | _NOVIEW):
                    errors.append(f"หน้า {no}: annotation {sub} ไม่ได้ตั้งให้พิมพ์ได้ (6.5.3)")
                if part == 1 and ("/CA" in a and float(a.CA) != 1.0):
                    errors.append(f"หน้า {no}: annotation โปร่งใส (6.5.3)")
                if sub != "/Link" and "/AP" not in a:
                    errors.append(f"หน้า {no}: annotation {sub} ไม่มี appearance (6.5.3)")
                action = a.get("/A")
                if action is not None and _is_script(action):
                    errors.append(f"หน้า {no}: ลิงก์ที่รันสคริปต์/โปรแกรม (6.6.1)")

        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Stream):
                flt = obj.get("/Filter")
                flts = list(flt) if isinstance(flt, pikepdf.Array) else ([flt] if flt is not None else [])
                if pikepdf.Name.LZWDecode in flts:
                    errors.append("มีการบีบอัด LZW (6.1.10)")
                if part == 1 and pikepdf.Name.JPXDecode in flts:
                    errors.append("PDF/A-1 ห้ามรูป JPEG 2000 (6.1.10)")
                if part == 1 and obj.get("/Subtype") == pikepdf.Name.Image and "/SMask" in obj:
                    errors.append("PDF/A-1 ห้ามรูปที่มีความโปร่งใส (SMask) (6.4)")
            if not isinstance(obj, pikepdf.Dictionary):
                continue
            typ = obj.get("/Type")
            if typ == pikepdf.Name.ExtGState and part == 1:
                smask = obj.get("/SMask")
                if smask is not None and smask != pikepdf.Name("/None"):
                    errors.append("PDF/A-1 ห้าม soft mask (6.4)")
                for key in ("/CA", "/ca"):
                    if key in obj and float(obj[key]) != 1.0:
                        errors.append("PDF/A-1 ห้ามความโปร่งใส (CA/ca) (6.4)")
                bm = obj.get("/BM")
                if bm is not None and bm not in (pikepdf.Name.Normal, pikepdf.Name.Compatible):
                    errors.append("PDF/A-1 ห้าม blend mode อื่นนอกจาก Normal (6.4)")
            if typ == pikepdf.Name.Font and obj.get("/Subtype") not in (pikepdf.Name.Type3, pikepdf.Name.Type0):
                desc = obj.get("/FontDescriptor")
                if desc is None or not any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                    errors.append(f"ฟอนต์ {obj.get('/BaseFont')} ไม่ได้ฝังในไฟล์ (6.3.4)")
    # ข้อความซ้ำกันหลายจุดจะรายงานครั้งเดียว
    return list(dict.fromkeys(errors))


def export_pdfa(session: PDFSession, flavour: str) -> tuple[Path, dict]:
    """ไฟล์ temp ของเอกสารปัจจุบันเป็น PDF/A (ผู้เรียกลบเอง) + รายงาน {"pdf_version": "PDF/A-2b", "converted": [...]}"""
    part = PDFA_PARTS.get(flavour)
    if part is None:
        raise PDFError(f"ไม่รองรับ {flavour}")
    label = f"PDF/A-{part}b"
    doc = require_unlocked(session)
    if session.signed_pdf_bytes is not None or has_digital_signatures(doc):
        raise PDFError(f"เอกสารที่มีลายเซ็นดิจิทัลบันทึกเป็น {label} ไม่ได้ เพราะต้องเขียนไฟล์ใหม่ทั้งไฟล์ ทำให้ลายเซ็นใช้ไม่ได้")
    if session.output_password:
        raise PDFError(f"{label} ห้ามเข้ารหัสไฟล์ — ลบรหัสผ่านของเอกสารก่อน (เมนู ความปลอดภัย) แล้วบันทึกอีกครั้ง")
    if not _ICC.exists():
        raise PDFError("ไม่พบโปรไฟล์สี sRGB สำหรับ PDF/A")
    save_working_copy(session)

    settings.ensure_dirs()
    temps = []
    for suffix in (".pdf", ".pdf", ".pdf", ".ps", ".icc"):
        fd, p = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        temps.append(p)
    prepared, flat, linked, def_ps, icc = temps
    out = settings.WORKING_DIR / f"pdfa_{session.session_id}_{os.urandom(6).hex()}.pdf"
    try:
        work = fitz.open(session.working_path)
        try:
            before_text = [len(p.get_text().strip()) for p in work]
            links = _saved_links(work)
            had_annots = any(True for p in work for a in p.annots()) or any(True for p in work for w in p.widgets())
            _highlights_under_content(work)
            _burn_freetext(work)
            alpha_images = _flatten_image_alpha(work) if part == 1 else 0
            work.save(prepared, garbage=3, deflate=True)
        finally:
            work.close()

        # รวม annotation/ช่องฟอร์มที่เหลือลงเนื้อหน้า (ลิงก์ใส่คืนทีหลัง)
        _run_ghostscript(["gs", "-sDEVICE=pdfwrite", "-dPrinted", "-dPreserveAnnots=false", "-dAutoRotatePages=/None",
                          "-dBATCH", "-dNOPAUSE", "-dQUIET", f"-sOutputFile={flat}", prepared])
        flat_doc = fitz.open(flat)
        try:
            if flat_doc.page_count != len(links):
                raise PDFError(f"บันทึกเป็น {label} ไม่สำเร็จ: จำนวนหน้าเปลี่ยน")
            _restore_links(flat_doc, links)
            flat_doc.save(linked, garbage=3, deflate=True)
        finally:
            flat_doc.close()
        _links_printable(linked, flat)

        # สำเนาโปรไฟล์ ICC ไว้ข้างไฟล์ชั่วคราว: Ghostscript 10.06 (Ubuntu 26.04) ปฏิเสธการอ่านไฟล์ใน site-packages
        # (/invalidfileaccess · Permission denied จากระบบ เช่น AppArmor) — ไฟล์ใน temp เดียวกับไฟล์ PDF ที่ส่งให้ gs อ่านได้เสมอ
        Path(icc).write_bytes(_ICC.read_bytes())
        _pdfa_def_ps(def_ps, icc)
        cmd = ["gs", f"-dPDFA={part}", "-dPDFACompatibilityPolicy=1", "-sDEVICE=pdfwrite",
               "-sColorConversionStrategy=RGB", "-dAutoRotatePages=/None", "-dBATCH", "-dNOPAUSE", "-dQUIET",
               "-dEmbedAllFonts=true", "-dSubsetFonts=true", "-dPassThroughJPEGImages=true", "-dDetectDuplicateImages=true",
               f"--permit-file-read={icc}", f"--permit-file-read={os.path.realpath(icc)}"]
        for kind in ("Color", "Gray", "Mono"):
            cmd.append(f"-dDownsample{kind}Images=false")
        for kind in ("Color", "Gray"):
            cmd += [f"-dAutoFilter{kind}Images=false", f"-d{kind}ImageFilter=/FlateEncode"]
        if part >= 2:
            cmd.append("-dPassThroughJPXImages=true")
        cmd += [f"-sOutputFile={out}", def_ps, flat]
        _run_ghostscript(cmd)

        errors = verify_pdfa(out, part)
        if errors:
            raise PDFError(f"บันทึกเป็น {label} ไม่สำเร็จ: " + "; ".join(errors[:3]))

        converted = []
        if had_annots:
            converted.append("ไฮไลต์ กล่องข้อความ และช่องฟอร์มถูกรวมลงเนื้อหน้า (PDF/A ต้องแสดงผลเหมือนกันทุกโปรแกรม)")
        if alpha_images:
            converted.append(f"รูปที่มีพื้นโปร่งใส {alpha_images} รูปถูกเติมพื้นขาว (PDF/A-1 ไม่รองรับความโปร่งใส)")
        after_text = _text_chars(str(out))
        rasterized = [i + 1 for i, (b, a) in enumerate(zip(before_text, after_text)) if b > 20 and a < b * 0.5]
        if rasterized:
            converted.append(f"หน้า {', '.join(map(str, rasterized))} ถูกแปลงเป็นภาพเพราะมีความโปร่งใสที่ PDF/A-1 ไม่รองรับ"
                             " (ค้นหาข้อความในหน้านั้นไม่ได้ — แนะนำ PDF/A-2b)")
        # ข้อความเดิมต้องคัดลอก/ค้นหาได้เหมือนเดิม (Ghostscript เขียนฟอนต์ใหม่ — ดู optimize._run_ghostscript)
        changed = [p for p in pages_with_changed_text(prepared, str(out), allow_added=True) if p not in rasterized]
        if changed:
            logger.warning("PDF/A: ข้อความเปลี่ยนหลัง Ghostscript หน้า %s session=%s", changed, session.session_id)
            converted.append(f"หน้า {', '.join(map(str, changed[:10]))}{' ...' if len(changed) > 10 else ''}: "
                             "ข้อความบางส่วนอาจคัดลอก/ค้นหาได้ไม่ตรงกับที่เห็น (ฟอนต์ในไฟล์ต้นฉบับแปลงให้ตรงมาตรฐานได้ไม่สมบูรณ์)")
        return out, {"pdf_version": label, "method": "pdfa", "converted": converted, "removed": []}
    except pikepdf.PdfError as exc:
        out.unlink(missing_ok=True)
        raise PDFError(f"บันทึกเป็น {label} ไม่สำเร็จ: {exc}") from exc
    except Exception:
        out.unlink(missing_ok=True)
        raise
    finally:
        for p in temps:
            if os.path.exists(p):
                os.remove(p)
