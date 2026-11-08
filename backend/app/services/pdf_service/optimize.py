"""pdf_service.optimize — ลดขนาดไฟล์ (บีบรูปเอง / Ghostscript เมื่อข้อความไม่เสีย) และรวมเลเยอร์"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile

import fitz
import pikepdf

from app.core.heavy import heavy_slot
from app.core.session import PDFSession
from app.services.pdf_service.core import PDFError, require_unlocked

logger = logging.getLogger("pdf_service")


_MIN_SAVING = 0.03   # เล็กลงไม่ถึง 3% ถือว่าลดไม่ได้ — ไม่เขียนทับ (Ghostscript บางครั้งทำไฟล์ใหญ่ขึ้น)


def _strip_for_ghostscript(src_path: str, out_path: str) -> None:
    """สำเนาที่ส่งให้ Ghostscript: เหลือแค่ลิงก์ — annotation อื่นและช่องฟอร์มเอาออกก่อน
    (Ghostscript วาดช่องฟอร์มลงเนื้อหน้าจนกรอกต่อไม่ได้ และ annotation ที่ผ่าน Ghostscript ไม่ครบเหมือนเดิม)"""
    with pikepdf.open(src_path) as pdf:
        for page in pdf.pages:
            annots = page.obj.get("/Annots")
            if annots is None:
                continue
            links = [a for a in annots if a.get("/Subtype") == pikepdf.Name.Link]
            if links:
                page.obj.Annots = pikepdf.Array(links)
            else:
                del page.obj["/Annots"]
        if "/AcroForm" in pdf.Root:
            del pdf.Root["/AcroForm"]
        pdf.save(out_path)


def _indirect(pdf, obj):
    """copy_foreign รับเฉพาะ indirect object — object ที่เขียนฝังตรง (direct) ต้องแปลงก่อน"""
    return obj if obj.is_indirect else pdf.make_indirect(obj)


def _restore_annotations(src_path: str, gs_path: str, out_path: str, keep=None) -> None:
    """ใส่ annotation (ไฮไลต์ กล่องข้อความ กรอบ บันทึกย่อ ...) และช่องฟอร์มจากต้นฉบับคืนให้ไฟล์ที่ Ghostscript ทำ
    (ลิงก์ใช้ของ Ghostscript ซึ่งแปลงปลายทางให้ถูกหน้าแล้ว)"""
    with pikepdf.open(src_path) as src, pikepdf.open(gs_path) as dst:
        if len(src.pages) != len(dst.pages):
            raise PDFError("ลดขนาดไฟล์ไม่สำเร็จ: จำนวนหน้าหลังประมวลผลไม่ตรงกับต้นฉบับ")
        for sp, dp in zip(src.pages, dst.pages):
            annots = [a for a in (sp.obj.get("/Annots") or [])
                      if a.get("/Subtype") != pikepdf.Name.Link and (keep is None or keep(a))]
            if not annots:
                continue
            if [round(float(v)) for v in sp.mediabox] != [round(float(v)) for v in dp.mediabox]:
                raise PDFError("ลดขนาดไฟล์ไม่สำเร็จ: ขนาดหน้าเปลี่ยน ใส่ไฮไลต์/กล่องข้อความคืนตำแหน่งเดิมไม่ได้")
            for a in annots:
                if "/P" in a:          # อ้างถึงหน้าต้นฉบับ — ถ้าคัดลอกไปด้วยจะลากทั้งหน้าเดิมติดไป
                    del a["/P"]
            copied = [dst.copy_foreign(_indirect(src, a)) for a in annots]
            existing = list(dp.obj.get("/Annots") or [])
            dp.obj.Annots = pikepdf.Array(existing + copied)
        if "/AcroForm" in src.Root:
            dst.Root.AcroForm = dst.copy_foreign(_indirect(src, src.Root.AcroForm))
        dst.save(out_path)


# ---------------------------------------------------------------------------
# ตรวจว่าข้อความในไฟล์ยังเหมือนเดิม (ใช้หลัง Ghostscript)
# ---------------------------------------------------------------------------
# Ghostscript (pdfwrite) เขียนฟอนต์ทุกตัวใหม่ — PDF จาก Word/LibreOffice ที่ map อักษรไทยหลายตัวต่อ glyph (เช่น "นั" = glyph เดียว)
# หลังผ่าน Ghostscript ToUnicode ไม่ตรงกับ glyph อีก คัดลอก/ค้นหาได้ "หนั\x03งสื\x06อ" หรือ "หนี้" กลายเป็น "หนั"
# จึงตรวจข้อความทุกหน้าก่อน/หลังเสมอ ถ้าไม่ตรง ไม่ใช้ผลของ Ghostscript

def text_fingerprint(path) -> list[str]:
    """ข้อความทุกหน้าแบบจัดรูปไทยแล้ว ไม่มีช่องว่าง/ขึ้นบรรทัด (เทียบว่าตัวอักษรเหมือนเดิมไหม)"""
    from app.services import thai_text

    out = []
    with fitz.open(path) as doc:
        for page in doc:
            text = thai_text.normalize(page.get_text())
            out.append("".join(ch for ch in text if not ch.isspace()))
    return out


def pages_with_changed_text(src_path, out_path, allow_added: bool = False) -> list[int]:
    """หน้า (เริ่ม 1) ที่ตัวอักษรเปลี่ยนไป — เทียบ "ชุดตัวอักษร" ของแต่ละหน้า (ลำดับการดึงข้อความอาจต่างได้เมื่อเนื้อหาถูก
    เขียนใหม่ แต่ตัวอักษรต้องครบและไม่เพี้ยน) · allow_added=True: ยอมให้มีตัวอักษรเพิ่ม (เช่น กล่องข้อความ/ค่าในฟอร์มที่
    ถูกรวมลงหน้า) ขอแค่ของเดิมอยู่ครบ"""
    try:
        a, b = text_fingerprint(src_path), text_fingerprint(out_path)
    except Exception:
        logger.warning("pages_with_changed_text: ตรวจข้อความไม่สำเร็จ", exc_info=True)
        return []
    if len(a) != len(b):
        return list(range(1, len(a) + 1))
    return [i + 1 for i, (x, y) in enumerate(zip(a, b)) if not _same_chars(x, y, allow_added)]


def _same_chars(x: str, y: str, allow_added: bool = False) -> bool:
    """ตัวอักษรของหน้าเหมือนกัน — ไม่นับอักษร Private Use (สัญลักษณ์ bullet ของ Word ที่ Ghostscript แปลงเป็น •)
    และยอมให้ต่างกันเล็กน้อย (≤ 1% อย่างน้อย 3 ตัว เช่น ข้อความที่มองไม่เห็นนอกกรอบตัดถูกทิ้ง) — ข้อความไทยที่เพี้ยนจาก
    ฟอนต์ต่างกันเป็นสิบเป็นร้อยตัวต่อหน้า"""
    from collections import Counter

    def chars(t):
        return Counter(c for c in t if not ("\ue000" <= c <= "\uf8ff") and c not in "•·")

    cx, cy = chars(x), chars(y)
    limit = max(3, len(x) // 100)
    missing = sum((cx - cy).values())
    extra = 0 if allow_added else sum((cy - cx).values())
    return missing <= limit and extra <= limit


def text_preserved(src_path, out_path) -> bool:
    try:
        a, b = text_fingerprint(src_path), text_fingerprint(out_path)
    except Exception:
        logger.warning("text_preserved: ตรวจข้อความไม่สำเร็จ", exc_info=True)
        return False
    return len(a) == len(b) and all(_same_chars(x, y) for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# ลดขนาดรูปในไฟล์โดยไม่แตะฟอนต์/ข้อความ
# ---------------------------------------------------------------------------
# (dpi เป้าหมาย, คุณภาพ JPEG) — ใกล้เคียง -dPDFSETTINGS ของ Ghostscript
_IMAGE_PROFILES = {"screen": (96, 55), "ebook": (150, 70), "printer": (300, 85)}
_MIN_IMAGE_GAIN = 0.9    # รูปที่บีบใหม่ต้องเล็กลงอย่างน้อย 10% จึงแทนที่
_UNKNOWN_PLACEMENT_MAX_PX = 2500   # รูปที่หาตำแหน่งบนหน้าไม่เจอ: ย่อเฉพาะที่ด้านยาวเกินนี้


def _placed_dpi(doc: fitz.Document) -> dict[int, float]:
    """xref ของรูป → dpi สูงสุดที่รูปนั้นถูกวางบนหน้า (รูปเดียวใช้หลายที่ ใช้ค่าที่คมที่สุด)"""
    dpi: dict[int, float] = {}
    for page in doc:
        try:
            infos = page.get_image_info(xrefs=True)
        except Exception:
            continue
        for info in infos:
            xref = info.get("xref") or 0
            bbox = fitz.Rect(info["bbox"])
            if not xref or bbox.is_empty or bbox.width < 1 or bbox.height < 1:
                continue
            d = max(info["width"] / (bbox.width / 72.0), info["height"] / (bbox.height / 72.0))
            dpi[xref] = max(dpi.get(xref, 0.0), d)
    return dpi


def _recompress_images(src_path: str, out_path: str, profile: str) -> int:
    """ย่อ/บีบรูปที่ละเอียดเกินโปรไฟล์เป็น JPEG แล้วเขียนไฟล์ใหม่ด้วย qpdf (object stream + บีบ stream)
    ไม่แตะฟอนต์ ข้อความ annotation ช่องฟอร์ม ลิงก์ บุ๊กมาร์ก — คืนจำนวนรูปที่แทนที่

    ข้าม: รูปขาวดำ 1 บิต (สแกนเอกสาร บีบดีอยู่แล้ว), JBIG2/CCITT, image mask, รูปที่มี /Decode, รูปที่เป็น SMask
    รูปที่มีพื้นโปร่งใส (SMask) ย่อ SMask ตามขนาดใหม่ด้วย"""
    import io as _io

    from PIL import Image

    target_dpi, quality = _IMAGE_PROFILES.get(profile, _IMAGE_PROFILES["ebook"])
    with fitz.open(src_path) as fdoc:
        placed = _placed_dpi(fdoc)
    replaced = 0
    with pikepdf.open(src_path) as pdf:
        smask_xrefs = set()
        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == pikepdf.Name.Image and "/SMask" in obj:
                sm = obj.SMask
                if sm.is_indirect:
                    smask_xrefs.add(sm.objgen[0])
        for obj in list(pdf.objects):
            if not isinstance(obj, pikepdf.Stream) or obj.get("/Subtype") != pikepdf.Name.Image:
                continue
            xref = obj.objgen[0]
            if xref in smask_xrefs or obj.get("/ImageMask") or "/Decode" in obj or "/Mask" in obj:
                continue
            if int(obj.get("/BitsPerComponent", 8)) != 8:
                continue
            flt = obj.get("/Filter")
            flts = [str(f) for f in (flt if isinstance(flt, pikepdf.Array) else [flt] if flt is not None else [])]
            if any(f in ("/JBIG2Decode", "/CCITTFaxDecode", "/JPXDecode") for f in flts):
                continue
            w, h = int(obj.get("/Width", 0)), int(obj.get("/Height", 0))
            if w < 64 or h < 64:
                continue
            dpi = placed.get(xref)
            if dpi is not None:
                scale = min(1.0, target_dpi / dpi) if dpi > target_dpi * 1.15 else 1.0
            else:
                scale = min(1.0, _UNKNOWN_PLACEMENT_MAX_PX / max(w, h))
            try:
                img = pikepdf.PdfImage(obj).as_pil_image()
            except Exception:
                continue
            if img.mode not in ("RGB", "L"):
                try:
                    img = img.convert("RGB")
                except Exception:
                    continue
            nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
            if (nw, nh) != (w, h):
                img = img.resize((nw, nh), Image.Resampling.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            old_len = len(obj.read_raw_bytes())
            if len(data) >= old_len * _MIN_IMAGE_GAIN:
                continue
            smask = obj.get("/SMask")
            if smask is not None and (nw, nh) != (w, h):
                try:
                    mask = pikepdf.PdfImage(smask).as_pil_image().convert("L").resize((nw, nh), Image.Resampling.LANCZOS)
                except Exception:
                    continue   # ย่อ SMask ไม่ได้ = ไม่แตะรูปนี้ (ไม่ให้ขนาดรูปกับพื้นโปร่งใสไม่ตรงกัน)
                smask.write(mask.tobytes(), filter=pikepdf.Name.FlateDecode)
                smask.Width, smask.Height, smask.BitsPerComponent = nw, nh, 8
                smask.ColorSpace = pikepdf.Name.DeviceGray
                for key in ("/DecodeParms", "/Decode"):
                    if key in smask:
                        del smask[key]
            obj.write(data, filter=pikepdf.Name.DCTDecode)
            obj.Width, obj.Height, obj.BitsPerComponent = nw, nh, 8
            obj.ColorSpace = pikepdf.Name.DeviceGray if img.mode == "L" else pikepdf.Name.DeviceRGB
            if "/DecodeParms" in obj:
                del obj["/DecodeParms"]
            replaced += 1
        pdf.remove_unreferenced_resources()
        # ไม่ใช้ object stream: ดาวน์โหลด/บันทึกเขียนไฟล์ใหม่ด้วย PyMuPDF (ไม่มี object stream) อยู่แล้ว ขนาดที่วัดตรงนี้
        # จึงตรงกับไฟล์ที่ผู้ใช้ได้จริง (ไม่งั้นกดลดขนาดซ้ำได้ "เล็กลง" ทุกครั้งทั้งที่ไฟล์ที่ได้เท่าเดิม)
        pdf.save(out_path, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.disable)
    return replaced


def compress_pdf(session: PDFSession, profile: str = "screen", reference_size: int | None = None) -> dict | None:
    """ลดขนาดไฟล์ — คืน {"before", "after", "method"} (ไบต์) หรือ None ถ้าเล็กลงไม่ถึง 3% (ไม่แตะเอกสาร)

    ลองสองวิธีแล้วเลือกไฟล์ที่เล็กกว่า:
    1. บีบ/ย่อรูปเอง (ไม่แตะฟอนต์และข้อความเลย) — ใช้ได้ทุกไฟล์
    2. Ghostscript (ย่อรูป + ตัดฟอนต์เฉพาะตัวที่ใช้) — ใช้ "เฉพาะเมื่อข้อความทุกหน้ายังเหมือนเดิม" (ดู text_preserved)
       เดิมใช้ Ghostscript อย่างเดียว: PDF จาก Word/LibreOffice (รวมถึงสร้างเอกสารอัตโนมัติ/แปลง Office ของระบบ)
       หลังลดขนาด คัดลอก/ค้นหาภาษาไทยได้ตัวอักษรเพี้ยน
    annotation และช่องฟอร์มอยู่ครบทั้งสองวิธี (วิธีที่ 2 ใส่คืนจากต้นฉบับ)

    reference_size: ขนาดไฟล์ที่ผู้ใช้เห็นจริง (เช่น ไฟล์ที่บันทึกไว้ในเอกสารของฉัน) — ไม่ส่งมาใช้ขนาดเอกสารที่เก็บกวาดแล้ว
    """
    if session.signed_pdf_bytes is not None:
        raise PDFError(_SIGNED_MSG.format(action="ลดขนาดไฟล์"))
    doc = require_unlocked(session)

    paths = []
    for _ in range(5):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            paths.append(tmp.name)
    src_path, native_path, gs_in, gs_out, gs_final = paths
    try:
        # ฐานเปรียบเทียบ: ไฟล์ที่เก็บกวาด object ที่ไม่ใช้แล้ว (ไม่ใช่ working copy ที่มีประวัติแก้ไขสะสม)
        doc.save(src_path, garbage=3, deflate=True)
        def finalize(path: str) -> str:
            # วัดขนาดแบบเดียวกับไฟล์ที่ผู้ใช้จะได้จริง — ดาวน์โหลด/บันทึกเขียนไฟล์ใหม่ด้วย PyMuPDF (garbage=3) เสมอ
            # (ผลของ Ghostscript ที่ผ่าน qpdf ยังมี object ซ้ำ เขียนใหม่แล้วเล็กลงอีกมาก)
            final = path + ".final.pdf"
            paths.append(final)
            with fitz.open(path) as cand:
                cand.save(final, garbage=3, deflate=True)
            return final

        before = reference_size or os.path.getsize(src_path)
        sized: list[tuple[int, str, str]] = []
        gs_error = None
        try:
            _strip_for_ghostscript(src_path, gs_in)
            _run_ghostscript([
                "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS=/{profile}", "-dAutoRotatePages=/None", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                f"-sOutputFile={gs_out}", gs_in,
            ])
            if text_preserved(gs_in, gs_out):
                _restore_annotations(src_path, gs_out, gs_final)
                final = finalize(gs_final)
                sized.append((os.path.getsize(final), final, "ghostscript"))
            else:
                logger.info("compress: Ghostscript ทำให้ข้อความเปลี่ยน — ใช้วิธีบีบรูปอย่างเดียว")
        except PDFError as exc:
            gs_error = exc
            logger.info("compress: ข้าม Ghostscript (%s)", exc)

        # บีบรูปเอง: เมื่อใช้ Ghostscript ไม่ได้ หรือ Ghostscript ลดได้ไม่มาก (ไฟล์ใหญ่ทำทั้งสองวิธีใช้เวลานาน)
        if not sized or sized[0][0] > before * 0.8:
            try:
                _recompress_images(src_path, native_path, profile)
                final = finalize(native_path)
                sized.append((os.path.getsize(final), final, "images"))
            except Exception:
                logger.warning("compress: บีบรูปเองไม่สำเร็จ", exc_info=True)

        if not sized:
            raise gs_error or PDFError("ลดขนาดไฟล์ไม่สำเร็จ")
        after, best, method = min(sized)
        if after > before * (1 - _MIN_SAVING):
            return None

        import shutil
        session.doc.close()
        shutil.copy2(best, session.working_path)
        session.doc = fitz.open(session.working_path)
        session.mark_dirty()
        return {"before": before, "after": after, "method": method}
    except pikepdf.PdfError as exc:
        raise PDFError(f"ลดขนาดไฟล์ไม่สำเร็จ: {exc}") from exc
    finally:
        for path in paths:
            if os.path.exists(path):
                os.remove(path)


_SIGNED_MSG = (
    "เอกสารนี้มีลายเซ็นดิจิทัล (PAdES) ฝังอยู่แล้ว ไม่สามารถ{action}ได้ เพราะต้องเขียนไฟล์ใหม่ทั้งหมด "
    "ซึ่งทำให้ลายเซ็นดิจิทัลที่ฝังไว้ใช้งานไม่ได้อีกต่อไป กรุณา Undo ย้อนกลับไปก่อนจุดที่เซ็นถ้าต้องการ{action}"
)


def _run_ghostscript(cmd: list[str]) -> None:
    # -dPreserveMarkedContent: คง marked content (/Span ActualText) ไว้ — PDF จาก Word/LibreOffice บอกข้อความจริงของ
    # อักษรไทยที่รวมเป็น glyph เดียว ("นี้", "ซื้") ผ่าน ActualText ถ้าทิ้ง คัดลอก/ค้นหาได้ "หนั\x03งสื\x06อ" (ตรวจแล้ว:
    # ไฟล์จากสร้างเอกสารอัตโนมัติ ข้อความเหมือนเดิม 100% เมื่อใส่ตัวเลือกนี้) · Ghostscript รุ่นที่ไม่รู้จักตัวเลือกนี้จะข้ามไปเอง
    if "-sDEVICE=pdfwrite" in cmd and "-dPreserveMarkedContent=true" not in cmd:
        cmd = [cmd[0], "-dPreserveMarkedContent=true", *cmd[1:]]
    try:
        with heavy_slot("ghostscript"):
            subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError:
        raise PDFError("ไม่พบโปรแกรม Ghostscript บนเซิร์ฟเวอร์ — ติดต่อผู้ดูแลระบบ")
    except subprocess.CalledProcessError as e:
        # Ghostscript เขียนรายละเอียด error (เช่น "Error: /invalidfileaccess in --file--") ลง stdout ส่วน stderr มีแค่
        # "Unrecoverable error" — เก็บบรรทัด error จาก stdout ไว้ใน log และข้อความ error เพื่อให้รู้สาเหตุ
        err = e.stderr.decode("utf-8", errors="ignore").strip()
        out = e.stdout.decode("utf-8", errors="ignore")
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        hits = [ln for ln in lines if ln.startswith(("Error", "****")) or "denied" in ln.lower()]
        detail = " · ".join((hits or lines)[:4])[:500]
        logger.warning("Ghostscript failed (exit %s): %s | %s", e.returncode, err, detail)
        raise PDFError(f"Ghostscript error: {err}" + (f" — {detail}" if detail else ""))


def _saved_links(doc: fitz.Document, keep_targets: bool = False) -> list[list[dict]]:
    """ลิงก์ทุกหน้า (พิกัดตามที่เห็นบนหน้า) เพื่อใส่คืนหลังแปลง annotation — keep_targets=False: ปลายทางบนหน้าหมุน
    ไปหัวหน้าแทน (Ghostscript รวมการหมุนเข้าเนื้อหน้า พิกัดเดิมใช้ไม่ได้)"""
    out = []
    for page in doc:
        links = []
        for link in page.get_links():
            item = {k: v for k, v in link.items() if k not in ("xref", "id", "zoom")}
            # ปลายทางในเอกสารเดียวกันที่เป็นหน้าหมุน: พิกัด "to" เปลี่ยนเมื่อ Ghostscript รวมการหมุนเข้าเนื้อหน้า
            # — ไปที่หัวหน้านั้นแทน
            if not keep_targets and item.get("kind") == fitz.LINK_GOTO and 0 <= item.get("page", -1) < doc.page_count \
                    and doc[item["page"]].rotation:
                item.pop("to", None)
            links.append(item)
        out.append(links)
    return out


def _restore_links(doc: fitz.Document, links: list[list[dict]]) -> int:
    restored = 0
    for page, items in zip(doc, links):
        for item in items:
            try:
                page.insert_link(item)
                restored += 1
            except Exception:
                logger.warning("flatten: ใส่ลิงก์คืนไม่สำเร็จ %s", item.get("uri") or item.get("page"), exc_info=True)
    return restored


def _burn_freetext(doc: fitz.Document) -> None:
    """เตรียม annotation ก่อนรวมเลเยอร์/Ghostscript: กล่องข้อความ/กรอบของแอปที่ยังไม่มี appearance (สร้างก่อน v1.26.12)
    สร้าง AP ข้อความไทยให้ก่อน แล้วตั้ง print flag ทุกตัว — bake()/Ghostscript วาดตาม AP

    เดิมวาดข้อความเฉพาะ FreeText ลงหน้าแล้วลบทิ้ง: ข้อความในกรอบสี่เหลี่ยมหายตอนรวมเลเยอร์ และ FreeText จากโปรแกรมอื่น
    เสียรูปแบบตัวอักษรเดิม"""
    from app.services import annotation_service as _annot_svc

    _annot_svc.ensure_text_appearances(doc)
    for page in doc:
        for annot in page.annots() or []:
            # xref_set_key ไม่ใช่ set_flags: set_flags ทำให้ MuPDF สร้าง appearance ใหม่ทับของเรา (ข้อความในกรอบหาย)
            doc.xref_set_key(annot.xref, "F", str(annot.flags | fitz.PDF_ANNOT_IS_PRINT))


def flatten_pdf(session: PDFSession) -> bool:
    """รวมเลเยอร์: annotation (ไฮไลต์ กล่องข้อความ สี่เหลี่ยม บันทึกย่อ) และช่องฟอร์มที่กรอกไว้ กลายเป็นเนื้อหน้า
    ตัวอักษรยังเลือก/ค้นหาได้ ลิงก์และบุ๊กมาร์กยังใช้ได้

    ใช้ MuPDF bake() ซึ่งแปลงเฉพาะ annotation/ฟอร์มเป็นเนื้อหน้า เนื้อหาเดิมของหน้าไม่ถูกเขียนใหม่
    — เดิมส่งทั้งไฟล์ผ่าน Ghostscript ซึ่งเข้ารหัสฟอนต์ใหม่: PDF ที่สร้างจาก Word/LibreOffice (รวมถึงสร้างเอกสาร
    อัตโนมัติ/แปลง Office ของระบบเอง) หลังรวมเลเยอร์คัดลอก/ค้นหาภาษาไทยได้เป็นตัวอักษรเพี้ยน ("หนั\x03งสื\x06อ")
    ทำกับสำเนาของเอกสาร — ถ้าขั้นใดล้มเหลว เอกสารใน session ไม่ถูกแตะ
    """
    if session.signed_pdf_bytes is not None:
        raise PDFError(_SIGNED_MSG.format(action="รวมเลเยอร์"))
    doc = require_unlocked(session)
    work = fitz.open("pdf", doc.tobytes())
    try:
        page_count = work.page_count
        links = _saved_links(work, keep_targets=True)
        for page in work:        # ที่ซ่อนไว้ (มองไม่เห็นบนจอ) ไม่ควรติดลงเนื้อหน้า
            for annot in list(page.annots() or []):
                if annot.flags & (fitz.PDF_ANNOT_IS_HIDDEN | fitz.PDF_ANNOT_IS_NO_VIEW):
                    page.delete_annot(annot)
        _burn_freetext(work)     # กล่องข้อความ/กรอบของแอปรุ่นเก่ายังไม่มี appearance — สร้างให้ก่อน bake
        work.bake(annots=True, widgets=True)
        for page in work:        # ที่ bake ไม่แปลง (ถ้ามี) — เอาออก ลิงก์ใส่คืนด้านล่าง
            for annot in list(page.annots() or []):
                page.delete_annot(annot)
            for link in page.get_links():
                page.delete_link(link)
        if work.page_count != page_count:
            raise PDFError("รวมเลเยอร์ไม่สำเร็จ: จำนวนหน้าหลังประมวลผลไม่ตรงกับต้นฉบับ")
        _restore_links(work, links)
        data = work.tobytes(garbage=3, deflate=True)
    except PDFError:
        raise
    except Exception as exc:
        logger.exception("flatten ล้มเหลว")
        raise PDFError(f"รวมเลเยอร์ไม่สำเร็จ: {exc}") from exc
    finally:
        work.close()

    tmp = session.working_path.with_suffix(".flatten.tmp")
    tmp.write_bytes(data)
    session.doc.close()
    os.replace(tmp, session.working_path)
    session.doc = fitz.open(session.working_path)
    session.mark_dirty()
    return True
