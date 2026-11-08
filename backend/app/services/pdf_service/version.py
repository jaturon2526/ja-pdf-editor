"""pdf_service.version — บันทึกเป็น PDF เวอร์ชันที่เลือก (1.4 / 1.5 / 1.6 / 1.7 / 2.0) ให้เนื้อไฟล์ตรงมาตรฐานเวอร์ชันนั้นจริง

ไม่ใช่แค่เปลี่ยนเลขหัวไฟล์ (%PDF-x.y): ตรวจทุกคุณสมบัติในไฟล์ที่ต้องใช้เวอร์ชันสูงกว่าเป้าหมาย แล้วแปลงลง
- โครงสร้างไฟล์ (object stream / xref stream ต้อง 1.5+) และการเข้ารหัส → เขียนไฟล์ใหม่ด้วย qpdf (pikepdf) ไม่เสียอะไร
  การเข้ารหัสตามเวอร์ชัน: 1.4–1.5 RC4 128 บิต (R3), 1.6–1.7 AES-128 (R4), 2.0 AES-256 (R6)
- เนื้อหาหน้า (รูป JPEG 2000 / รูป 16 บิต / เลเยอร์ OCG ต้อง 1.5+, ฟอนต์ OpenType ต้อง 1.6+) → Ghostscript แปลงลง
  (รูปไม่ลดความละเอียดและไม่บีบแบบเสียคุณภาพ, เลเยอร์ถูกรวมตามที่มองเห็น) annotation/ช่องฟอร์มไม่ผ่าน Ghostscript
  แต่ใส่คืนจากต้นฉบับ (เหมือนลดขนาดไฟล์)
- annotation ชนิดที่ยังไม่มีในเวอร์ชันเป้าหมาย, XFA, NeedsRendering, Collection → เอาออก (แจ้งรายการใน removed)
- PDF 2.0: เลิกใช้ Document Info (เหลือ CreationDate/ModDate) ข้อมูลเอกสารย้ายไปอยู่ใน XMP metadata
ปิดท้ายด้วยการตรวจไฟล์ผลลัพธ์ซ้ำ ถ้ายังมีคุณสมบัติเกินเวอร์ชันหรือโครงสร้างเสีย → ไม่บันทึก (PDFError)
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import fitz
import pikepdf

from app.core.config import settings
from app.core.session import PDFSession
from app.services.pdf_service.core import PDFError, has_digital_signatures, require_unlocked, save_working_copy
from app.services.pdf_service.optimize import (_restore_annotations, _run_ghostscript, _strip_for_ghostscript,
                                               pages_with_changed_text)

PDF_VERSIONS = ("1.4", "1.5", "1.6", "1.7", "2.0")

# annotation ที่เพิ่มเข้ามาหลัง 1.4 (ชนิดอื่นที่แอปสร้าง — Highlight, FreeText, Square, Text, Link, Widget — มีตั้งแต่ ≤1.3)
_ANNOT_MIN = {
    "/Caret": "1.5", "/Polygon": "1.5", "/PolyLine": "1.5", "/Screen": "1.5",
    "/Watermark": "1.6", "/3D": "1.6", "/Redact": "1.7", "/Projection": "2.0", "/RichMedia": "2.0",
}
_ANNOT_LABEL = {"/Caret": "เครื่องหมายแทรก (Caret)", "/Polygon": "รูปหลายเหลี่ยม", "/PolyLine": "เส้นหลายจุด",
                "/Screen": "สื่อมัลติมีเดีย", "/Watermark": "ลายน้ำแบบ annotation", "/3D": "โมเดล 3 มิติ",
                "/Redact": "เครื่องหมายเซ็นเซอร์ที่ยังไม่ใช้", "/Projection": "Projection", "/RichMedia": "Rich Media"}


def _v(s: str) -> tuple[int, int]:
    major, minor = s.split(".")[:2]
    return int(major), int(minor)


def scan_features(path) -> dict[str, str]:
    """คุณสมบัติในไฟล์ที่ต้องใช้ PDF สูงกว่า 1.4 → {ชื่อ: เวอร์ชันต่ำสุด} (ใช้ทั้งตัดสินใจแปลงและตรวจผลลัพธ์)"""
    found: dict[str, str] = {}

    def need(name: str, version: str):
        if name not in found or _v(version) > _v(found[name]):
            found[name] = version

    with pikepdf.open(path) as pdf:
        raw = Path(path).read_bytes()
        compact = raw.replace(b" ", b"")
        if b"/Type/ObjStm" in compact:
            need("object_stream", "1.5")
        if b"/Type/XRef" in compact:
            need("xref_stream", "1.5")
        if "/OCProperties" in pdf.Root:
            need("ocg", "1.5")
        acro = pdf.Root.get("/AcroForm")
        if acro is not None and "/XFA" in acro:
            need("xfa", "1.5")
        if "/Collection" in pdf.Root:
            need("collection", "1.7")
        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Stream):
                flt = obj.get("/Filter")
                flts = list(flt) if isinstance(flt, pikepdf.Array) else ([flt] if flt is not None else [])
                if pikepdf.Name.JPXDecode in flts:
                    need("jpx_image", "1.5")
                if obj.get("/BitsPerComponent") == 16:
                    need("image_16bit", "1.5")
                if obj.get("/Subtype") == pikepdf.Name("/OpenType"):
                    need("opentype_font", "1.6")
        for page in pdf.pages:
            for a in page.obj.get("/Annots") or []:
                sub = str(a.get("/Subtype"))
                if sub in _ANNOT_MIN:
                    need(f"annot:{sub}", _ANNOT_MIN[sub])
    return found


_CONTENT_FEATURES = {"jpx_image", "image_16bit", "ocg", "opentype_font"}   # ต้องให้ Ghostscript แปลงเนื้อหา
_FEATURE_LABEL = {"jpx_image": "รูป JPEG 2000 (แปลงเป็นรูปแบบที่รองรับ ไม่เสียความคมชัด)",
                  "image_16bit": "รูป 16 บิตต่อสี (ลดเป็น 8 บิต)", "ocg": "เลเยอร์ (รวมเป็นชั้นเดียวตามที่มองเห็น)",
                  "opentype_font": "ฟอนต์ OpenType (แปลงเป็นฟอนต์ที่เวอร์ชันนี้รองรับ)",
                  "xfa": "ฟอร์ม XFA", "collection": "PDF Portfolio"}


def _ghostscript_downgrade(src: str, target: str, out: str) -> None:
    """แปลงเนื้อหาหน้าด้วย Ghostscript โดยคงคุณภาพ — รูปไม่ downsample, รูปที่ไม่ใช่ JPEG บีบแบบ Flate (ไม่เสียข้อมูล),
    JPEG เดิมส่งผ่านตรง, สีไม่แปลง — annotation/ช่องฟอร์มใส่คืนจากต้นฉบับ (ชนิดที่เวอร์ชันเป้าหมายรองรับเท่านั้น)"""
    fd, gs_in = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    fd, gs_out = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        _strip_for_ghostscript(src, gs_in)
        cmd = ["gs", "-sDEVICE=pdfwrite", f"-dCompatibilityLevel={target}", "-dAutoRotatePages=/None",
               "-dNOPAUSE", "-dQUIET", "-dBATCH", "-dDetectDuplicateImages=true",
               "-dColorConversionStrategy=/LeaveColorUnchanged", "-dEmbedAllFonts=true",
               "-dPassThroughJPEGImages=true"]
        for kind in ("Color", "Gray", "Mono"):
            cmd.append(f"-dDownsample{kind}Images=false")
        for kind in ("Color", "Gray"):
            cmd += [f"-dAutoFilter{kind}Images=false", f"-d{kind}ImageFilter=/FlateEncode"]
        if _v(target) >= (1, 5):
            cmd.append("-dPassThroughJPXImages=true")
        cmd += [f"-sOutputFile={gs_out}", gs_in]
        _run_ghostscript(cmd)

        def keep(annot):
            need = _ANNOT_MIN.get(str(annot.get("/Subtype")))
            return need is None or _v(need) <= _v(target)
        _restore_annotations(src, gs_out, out, keep=keep)
    finally:
        for p in (gs_in, gs_out):
            if os.path.exists(p):
                os.remove(p)


def _encryption_for(target: str, password: str, mode: str = "aes256") -> pikepdf.Encryption:
    """1.4–1.5 RC4-128 (R3) · 1.6 AES-128 (R4) · 1.7 AES-256 (R6 + Adobe Extension Level 8) ถ้าผู้ใช้เลือก AES-256
    ไม่งั้น AES-128 · 2.0 AES-256 (R6)"""
    if _v(target) == (1, 7) and mode == "aes256":
        return pikepdf.Encryption(owner=password, user=password, R=6, aes=True)
    if _v(target) <= (1, 5):
        return pikepdf.Encryption(owner=password, user=password, R=3, aes=False, metadata=False)
    if _v(target) <= (1, 7):
        return pikepdf.Encryption(owner=password, user=password, R=4, aes=True)
    return pikepdf.Encryption(owner=password, user=password, R=6, aes=True)


def _finalize(src: str, target: str, out: str, docinfo: dict, removed: list[str], password: str | None,
              mode: str = "aes256") -> None:
    """เอาสิ่งที่เวอร์ชันเป้าหมายไม่มีออก ตั้งข้อมูลเอกสาร/XMP แล้วเขียนไฟล์ด้วยหัวไฟล์และโครงสร้างของเวอร์ชันนั้น"""
    tv = _v(target)
    with pikepdf.open(src) as pdf:
        for page in pdf.pages:
            annots = page.obj.get("/Annots")
            if annots is None:
                continue
            kept = []
            for a in annots:
                sub = str(a.get("/Subtype"))
                if sub in _ANNOT_MIN and _v(_ANNOT_MIN[sub]) > tv:
                    label = _ANNOT_LABEL.get(sub, sub)
                    if label not in removed:
                        removed.append(label)
                    continue
                kept.append(a)
            page.obj.Annots = pikepdf.Array(kept)
        acro = pdf.Root.get("/AcroForm")
        if acro is not None and "/XFA" in acro and (tv < (1, 5) or tv >= (2, 0)):
            del acro["/XFA"]
            removed.append(_FEATURE_LABEL["xfa"])
        if tv >= (2, 0) and "/NeedsRendering" in pdf.Root:
            del pdf.Root["/NeedsRendering"]
        if "/Collection" in pdf.Root and tv < (1, 7):
            del pdf.Root["/Collection"]
            removed.append(_FEATURE_LABEL["collection"])
        if "/Version" in pdf.Root:           # ค่าในแคตตาล็อกมีผลเหนือหัวไฟล์ — ให้หัวไฟล์เป็นตัวกำหนดอย่างเดียว
            del pdf.Root["/Version"]

        # ข้อมูลเอกสาร: ใช้ของต้นฉบับ (Ghostscript เขียน Producer ของตัวเองทับ) + XMP ที่ตรงกัน
        if "/Metadata" in pdf.Root:          # XMP ของ Ghostscript/ต้นฉบับ — สร้างใหม่จากข้อมูลเอกสารด้านล่าง
            del pdf.Root["/Metadata"]
        info = pikepdf.Dictionary({k: pikepdf.String(v) for k, v in docinfo.items() if v})
        info["/ModDate"] = pikepdf.String(datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ"))
        pdf.docinfo = pdf.make_indirect(info)
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            meta.load_from_docinfo(pdf.docinfo, delete_missing=True)
        if tv >= (2, 0):   # PDF 2.0 เลิกใช้ Document Info — คงไว้เฉพาะวันที่ (ข้อมูลอื่นอยู่ใน XMP แล้ว)
            for key in list(pdf.docinfo.keys()):
                if key not in ("/CreationDate", "/ModDate"):
                    del pdf.docinfo[key]

        r6_in_17 = bool(password) and tv == (1, 7) and mode == "aes256"
        pdf.save(
            out,
            # AES-256 ใน PDF 1.7 ต้องประกาศ Adobe Extension Level 8 — ถ้าบังคับแค่ "1.7" qpdf จะทิ้งการเข้ารหัสเงียบๆ
            force_version=(target, 8) if r6_in_17 else target,
            object_stream_mode=pikepdf.ObjectStreamMode.disable if tv < (1, 5) else pikepdf.ObjectStreamMode.generate,
            compress_streams=True,
            encryption=_encryption_for(target, password, mode) if password else False,
        )


def verify(path, target: str, password: str | None = None) -> None:
    """ตรวจไฟล์ที่ได้: หัวไฟล์ตรง, ไม่มีคุณสมบัติเกินเวอร์ชัน, การเข้ารหัสตรงเวอร์ชัน, โครงสร้างผ่าน qpdf check"""
    with pikepdf.open(path, password=password or "") as pdf:
        if pdf.pdf_version != target:
            raise PDFError(f"บันทึกเป็น PDF {target} ไม่สำเร็จ: หัวไฟล์เป็น {pdf.pdf_version}")
        checker = getattr(pdf, "check_pdf_syntax", None) or getattr(pdf, "check", None)   # ชื่อต่างกันตามรุ่น pikepdf
        problems = [str(p) for p in (checker() if checker else []) if "warning" not in str(p).lower()]
        if problems:
            raise PDFError(f"บันทึกเป็น PDF {target} ไม่สำเร็จ: โครงสร้างไฟล์ผิด ({problems[0]})")
        if password and not pdf.is_encrypted:
            raise PDFError(f"บันทึกเป็น PDF {target} ไม่สำเร็จ: ไฟล์ที่ได้ไม่ได้เข้ารหัส")
        if pdf.is_encrypted:
            r = pdf.encryption.R
            ok = {(1, 4): {2, 3}, (1, 5): {2, 3}, (1, 6): {2, 3, 4}, (1, 7): {2, 3, 4, 6}, (2, 0): {6}}[_v(target)]
            if r not in ok:
                raise PDFError(f"บันทึกเป็น PDF {target} ไม่สำเร็จ: การเข้ารหัส R{r} ไม่ตรงเวอร์ชัน")
    if password:
        # สแกนคุณสมบัติจากเนื้อไฟล์ที่ถอดรหัสแล้ว
        fd, plain = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            with pikepdf.open(path, password=password) as pdf:
                pdf.save(plain, encryption=False, object_stream_mode=pikepdf.ObjectStreamMode.preserve)
            features = scan_features(plain)
        finally:
            os.remove(plain)
    else:
        features = scan_features(path)
    over = sorted(f for f, need in features.items() if _v(need) > _v(target))
    if over:
        raise PDFError(f"บันทึกเป็น PDF {target} ไม่สำเร็จ: ยังมีคุณสมบัติที่ต้องใช้เวอร์ชันสูงกว่า ({', '.join(over)})")


def export_pdf_version(session: PDFSession, target: str) -> tuple[Path, dict]:
    """ไฟล์ temp ของเอกสารปัจจุบันในเวอร์ชัน target (ผู้เรียกลบเอง) + รายงาน
    {"pdf_version", "method": "rewrite" | "ghostscript", "converted": [...], "removed": [...]}"""
    if target not in PDF_VERSIONS:
        raise PDFError(f"ไม่รองรับ PDF เวอร์ชัน {target}")
    doc = require_unlocked(session)
    if session.signed_pdf_bytes is not None or has_digital_signatures(doc):
        raise PDFError("เอกสารที่มีลายเซ็นดิจิทัลเปลี่ยนเวอร์ชัน PDF ไม่ได้ เพราะต้องเขียนไฟล์ใหม่ทั้งไฟล์ ทำให้ลายเซ็นใช้ไม่ได้")
    mode = session.output_encryption or "aes256"
    if session.output_password and (_v(target) < (1, 7) or (_v(target) == (1, 7) and mode == "aes128")):
        # RC4/AES-128 (มาตรฐานเดิม) รับเฉพาะรหัสผ่านอักษรละติน ≤ 32 ตัว — เดิมรหัสภาษาไทยทำให้ error ภาษาอังกฤษ (500)
        try:
            from app.services.pdf_service.core import check_password_for_mode

            check_password_for_mode(session.output_password, "aes128")
        except PDFError:
            raise PDFError(f"PDF {target} เข้ารหัสได้เฉพาะรหัสผ่านตัวอังกฤษ/ตัวเลข/สัญลักษณ์ (ไม่เกิน 32 ตัว) — "
                           "เปลี่ยนรหัสผ่าน หรือบันทึกเป็น PDF 1.7 / 2.0 ซึ่งใช้ AES-256 รองรับรหัสผ่านภาษาไทย") from None
    save_working_copy(session)

    settings.ensure_dirs()
    fd, src = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    fd, mid = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    out = settings.WORKING_DIR / f"version_{session.session_id}_{os.urandom(6).hex()}.pdf"
    try:
        plain = fitz.open(session.working_path)
        try:
            plain.save(src, garbage=3, deflate=True)
        finally:
            plain.close()
        with pikepdf.open(src) as pdf:
            docinfo = {str(k): str(v) for k, v in pdf.docinfo.items()
                       if str(k) in ("/Title", "/Author", "/Subject", "/Keywords", "/Creator", "/Producer", "/CreationDate")
                       and str(v).strip() not in ("", "None")}

        features = scan_features(src)
        needs_gs = sorted(f for f in features if f in _CONTENT_FEATURES and _v(features[f]) > _v(target))
        if needs_gs:
            _ghostscript_downgrade(src, target, mid)
            source_for_final = mid
        else:
            source_for_final = src
        removed: list[str] = []
        notes: list[str] = []
        if needs_gs:   # Ghostscript เขียนเนื้อหาใหม่ — ตรวจว่าข้อความเดิมยังคัดลอก/ค้นหาได้เหมือนเดิม
            changed = pages_with_changed_text(src, mid, allow_added=True)
            if changed:
                notes.append(f"ข้อความบางส่วนในหน้า {', '.join(map(str, changed[:10]))} อาจคัดลอก/ค้นหาได้ไม่ตรงกับที่เห็น")
        _finalize(source_for_final, target, str(out), docinfo, removed, session.output_password, mode)
        verify(out, target, session.output_password)
        return out, {
            "pdf_version": target,
            "method": "ghostscript" if needs_gs else "rewrite",
            "converted": [_FEATURE_LABEL[f] for f in needs_gs] + notes,
            "removed": removed,
        }
    except pikepdf.PdfError as exc:
        out.unlink(missing_ok=True)
        raise PDFError(f"บันทึกเป็น PDF {target} ไม่สำเร็จ: {exc}") from exc
    except Exception:
        out.unlink(missing_ok=True)
        raise
    finally:
        for p in (src, mid):
            if os.path.exists(p):
                os.remove(p)
