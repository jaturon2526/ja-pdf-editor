import subprocess
import os
import tempfile
import asyncio
from fastapi import HTTPException
import logging
import difflib
import json
import re
from pdf2docx import Converter
from docx import Document
from app.core.heavy import heavy_slot
from app.services import thai_text
from app.services import ai_client, ai_usage, gemini_client
from app.services.pdf2docx_fixes import (
    collect_light_text_backgrounds,
    fix_symbol_chars,
    fix_table_grids,
    split_heading_paragraphs,
    normalize_docx_fonts,
    patched_pdf2docx,
    upright_rotated_pages,
    paragraph_text_groups,
    replace_group_text,
    restore_light_text_backgrounds,
)
from app.core.config import settings
from app.models.domain import User

logger = logging.getLogger("convert_service")


def _libreoffice_to_pdf(inputs: list[tuple[str, bytes]], user_id: int | None) -> list[bytes]:
    """แปลงไฟล์ Office หลายไฟล์เป็น PDF ใน LibreOffice ครั้งเดียว (เริ่มโปรแกรมครั้งเดียว — ไฟล์ละ ~0.3 วินาที
    แทน ~3 วินาทีต่อการเรียกแยก) · inputs = [(นามสกุลไฟล์ เช่น ".docx", ไบต์)] → PDF ตามลำดับ
    สร้าง fontconfig ชั่วคราวที่รวม app fonts + ฟอนต์ส่วนตัวของ user เข้าด้วยกัน"""
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = []
        for i, (ext, data) in enumerate(inputs):
            path = os.path.join(tmpdir, f"input_{i:05d}{ext}")
            with open(path, "wb") as f:
                f.write(data)
            paths.append(path)

        # สร้าง fontconfig ชั่วคราว เพื่อให้ LibreOffice เห็นฟอนต์ของแอปและฟอนต์ส่วนตัวของ user
        app_fonts_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "assets", "fonts"))
        font_dirs_xml = f'  <dir>{app_fonts_dir}</dir>\n'
        if user_id is not None:
            user_fonts_dir = str(settings.UPLOAD_DIR / "users" / str(user_id) / "fonts")  # ตรงกับ fonts._get_user_fonts_dir
            if os.path.isdir(user_fonts_dir):
                font_dirs_xml += f'  <dir>{user_fonts_dir}</dir>\n'
        fonts_conf_content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>/usr/share/fonts</dir>
  <dir>/usr/local/share/fonts</dir>
{font_dirs_xml}
  <cachedir>/tmp/lo_fontcache_{os.getpid()}</cachedir>
</fontconfig>"""
        fonts_conf_path = os.path.join(tmpdir, "fonts.conf")
        with open(fonts_conf_path, "w") as f:
            f.write(fonts_conf_content)

        # profile แยกต่างหากต่อ job ป้องกัน LibreOffice lock conflict เมื่อรันพร้อมกันหลาย request
        lo_profile_dir = os.path.join(tmpdir, "lo_profile")
        outdir = os.path.join(tmpdir, "out")
        cmd = [
            "libreoffice", "--headless", "--invisible", "--nologo", "--nodefault", "--norestore",
            f"-env:UserInstallation=file://{lo_profile_dir}",
            "--convert-to", "pdf", *paths, "--outdir", outdir,
        ]
        try:
            if not os.path.exists("/usr/bin/libreoffice") and os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice"):
                cmd[0] = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
            env = os.environ.copy()
            env["FONTCONFIG_FILE"] = fonts_conf_path
            with heavy_slot("libreoffice"):
                subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
            out = []
            for path in paths:
                pdf_path = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
                if not os.path.exists(pdf_path):
                    raise FileNotFoundError("ไม่พบไฟล์ผลลัพธ์จากการแปลง")
                with open(pdf_path, "rb") as f:
                    out.append(f.read())
            return out
        except Exception as e:
            logger.error(f"LibreOffice error: {e}")
            raise RuntimeError("การแปลงไฟล์ล้มเหลว โครงสร้างไฟล์อาจไม่สมบูรณ์")


async def convert_office_to_pdf_bytes(file_bytes: bytes, original_filename: str, user_id: int | None = None) -> bytes:
    """ใช้ LibreOffice แปลงไฟล์ Office เป็น PDF โดยรับไบต์เข้ามาและคืนไบต์ของ PDF ออกไป
    รองรับ user_id เพื่อใช้ฟอนต์ส่วนตัวของ user ด้วย"""
    ext = os.path.splitext(original_filename)[1]
    try:
        [pdf_bytes] = await asyncio.to_thread(_libreoffice_to_pdf, [(ext, file_bytes)], user_id)
        return pdf_bytes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def convert_docx_batch_to_pdf(docs: list[bytes], user_id: int | None = None) -> list[bytes]:
    """แปลง .docx หลายไฟล์เป็น PDF ใน LibreOffice ครั้งเดียว (สร้างเอกสารอัตโนมัติแบบแยกไฟล์)"""
    if not docs:
        return []
    try:
        return await asyncio.to_thread(_libreoffice_to_pdf, [(".docx", d) for d in docs], user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _normalize_thai_text(text: str) -> str:
    """จัดรูปข้อความไทยที่ดึงจาก PDF — ใช้ตัวกลาง services/thai_text.py (PUA, สระอำ, ลำดับสระ/วรรณยุกต์ ฯลฯ)"""
    return thai_text.normalize(text)

def get_latest_flash_model(api_key: str | None = None) -> str:
    """รุ่น Gemini Flash ล่าสุด (ดู gemini_client.latest_flash_model)"""
    return gemini_client.latest_flash_model(api_key or gemini_client.system_api_key())


def _add_zwsp(text: str) -> str:
    """แทรก zero-width space ระหว่างคำไทยที่ติดกัน ให้ Word ขึ้นบรรทัดตรงขอบคำ — เฉพาะไทย-ไทย
    (เดิมแทรกระหว่างทุก token รวมอังกฤษ/ตัวเลข/ช่องว่าง ข้อความที่คัดลอกจาก Word จึงมี ZWSP เต็มไปหมด)"""
    return thai_text.with_break_opportunities(text)


_LATIN_DIGIT = re.compile(r"[A-Za-z0-9]+")
_ZW_CHARS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
AI_MIN_SIMILARITY = 0.85        # ผล AI ต้องคล้ายข้อความที่จัดรูปในเครื่องอย่างน้อยเท่านี้ (difflib ratio)
AI_MAX_LENGTH_CHANGE = 0.15     # ความยาวเปลี่ยนได้ไม่เกิน 15% (ข้อความสั้นเปลี่ยนได้ 2 ตัวอักษร)


def accept_ai_text(local: str, ai) -> str | None:
    """ตรวจผลแก้คำของ Gemini เทียบกับข้อความที่จัดรูปในเครื่องแล้ว — คืนข้อความที่ใช้ได้ หรือ None (ใช้ของในเครื่องแทน)

    ปฏิเสธเมื่อ: ไม่ใช่ข้อความ · ตัวเลข/คำภาษาอังกฤษเปลี่ยน (สั่งไว้ว่าห้ามแตะ) · ความยาวเปลี่ยนมาก หรือเนื้อหาต่าง
    จากเดิมมาก (แปลภาษา สรุปความ ตัด/เติมประโยค ตอบปนคำอธิบาย) · ตัดคำภาษาไทยได้แย่ลง (คำในพจนานุกรมน้อยลง)"""
    if not isinstance(ai, str):
        return None
    ai = thai_text.normalize(ai.translate(_ZW_CHARS))
    if ai == local:
        return ai
    if _LATIN_DIGIT.findall(ai) != _LATIN_DIGIT.findall(local):
        return None
    n = len(local.strip())
    if abs(len(ai.strip()) - n) > max(2, AI_MAX_LENGTH_CHANGE * n):
        return None
    if difflib.SequenceMatcher(None, local, ai, autojunk=False).ratio() < AI_MIN_SIMILARITY:
        return None
    if thai_text.dictionary_coverage(ai) + 0.005 < thai_text.dictionary_coverage(local):
        return None
    return ai


def _thai_paragraphs(doc) -> list[list]:
    """กลุ่มข้อความ (paragraph_text_groups) ของทุกย่อหน้าที่มีภาษาไทย — รวมในตาราง/กล่องข้อความ ตามลำดับเอกสาร"""
    from docx.oxml.ns import qn

    out = []
    for p in doc.element.body.iter(qn("w:p")):
        groups = paragraph_text_groups(p)
        if any(thai_text.has_thai("".join(n.text or "" for n in g)) for g in groups):
            out.append(groups)
    return out


def _fix_thai_in_docx(docx_path: str, user: User = None, progress_callback=None, source: str = "pdf") -> str:
    """เปิดไฟล์ DOCX แล้วแก้ข้อความไทย (ตัวจัดรูปในเครื่อง + Gemini ถ้ามีโควต้า/คีย์) โดยคงรูปแบบของแต่ละ run
    คืนค่า 'ai' หากเรียก AI สำเร็จทุกชุด, 'fallback' หากต้องใช้ตัวจัดรูปในเครื่องเพราะ AI ใช้ไม่ได้/โควต้าหมด
    หรือ 'basic' หากไม่ได้ตั้ง AI ไว้เลย (ปิดฟีเจอร์ AI)

    ทุกย่อหน้าผ่าน thai_text.normalize ก่อนเสมอ แล้วจึงส่งให้ AI แก้ต่อ ผลของ AI ใช้เฉพาะช่วงที่ผ่าน accept_ai_text
    สุดท้ายแทรก ZWSP ระหว่างคำไทย (ให้ Word ตัดบรรทัดตรงคำ) แล้วใส่กลับเข้า run เดิม (replace_group_text)"""
    status = "ai"
    reserved_system_quota = False
    try:
        doc = Document(docx_path)
        paras = _thai_paragraphs(doc)
        if not paras:
            if progress_callback: progress_callback(100)
            return "ai"
        # ข้อความที่จัดรูปในเครื่องแล้วของทุกกลุ่ม — ใช้เป็นผลสำรองและเป็นตัวเทียบตรวจผล AI
        local = [[_normalize_thai_text("".join(n.text or "" for n in g)) for g in groups] for groups in paras]
        chosen = [list(x) for x in local]

        def apply_all():
            for groups, texts in zip(paras, chosen):
                for g, t in zip(groups, texts):
                    replace_group_text(g, _add_zwsp(t))
            doc.save(docx_path)

        # AI ของผู้ใช้เอง (ค่ายไหนก็ได้ — ดู ai_client) / AI ของระบบ (key องค์กร)
        user_ai = ai_client.personal_config(user)
        system_ai = ai_client.system_config()
        if not user_ai and not system_ai:
            # ไม่ได้ตั้ง AI เลย (ระบบไม่มี key และผู้ใช้ไม่มี key ส่วนตัว) — ใช้ตัวจัดรูปในเครื่อง ไม่ใช่ "AI ขัดข้อง"
            apply_all()
            if progress_callback: progress_callback(100)
            return "basic"

        # โควต้าฟรีรายวัน (ใช้ AI ของระบบ) — จองก่อนเริ่ม คืนให้ถ้าสุดท้าย AI ใช้ไม่ได้ (ดู ai_usage.py)
        # ผู้ที่ไม่ได้ login ใช้ key ของระบบไม่ได้
        system_key_allowed = bool(
            system_ai and user is not None
            and ai_usage.try_reserve(user.id, ai_usage.SYSTEM_CONVERSION, settings.AI_SYSTEM_DAILY_LIMIT)
        )
        reserved_system_quota = system_key_allowed

        if not user_ai and not system_key_allowed:
            apply_all()
            if progress_callback: progress_callback(100)
            return "fallback"

        # ใช้ AI ของระบบถ้ายังมีโควต้ารายวัน ไม่งั้นใช้ key ส่วนตัวของผู้ใช้ (BYOK)
        ai_cfg = system_ai if system_key_allowed else user_ai
        try:
            model_name = ai_client.resolve_model(ai_cfg)
        except Exception as e:
            logger.error("ตั้งค่า AI (%s) ไม่ครบ: %s", ai_cfg.provider, e)
            if reserved_system_quota:
                ai_usage.release(user.id, ai_usage.SYSTEM_CONVERSION)
            apply_all()
            if progress_callback: progress_callback(100)
            return "fallback"
        batch_size = 30
        ai_batches = personal_batches = accepted = rejected = 0
        total_batches = (len(paras) + batch_size - 1) // batch_size

        for start in range(0, len(paras), batch_size):
            if progress_callback:
                progress_callback(50 + int((start // batch_size + 1) / total_batches * 45))
            idx = list(range(start, min(start + batch_size, len(paras))))
            # หนึ่งย่อหน้า = หนึ่งสตริง ช่วงที่คั่นด้วย tab/ขึ้นบรรทัด ส่งเป็นบรรทัด ("\n") — ต้องได้จำนวนบรรทัดเท่าเดิม
            texts = ["\n".join(local[i]) for i in idx]
            origin = ("recognized by OCR from a scanned page; some words may be misread "
                      "(look-alike Thai letters swapped, missing or wrong vowels/tone marks)") if source == "ocr" else (
                      "extracted from a PDF and already normalized; some words may still be misspelled "
                      "(wrong or missing vowels/tone marks, broken Sara Am, characters swapped by bad font encoding)")
            prompt = f"""You are a Thai text fixing tool.
The Thai text below was {origin}.
Fix only the Thai spelling of each paragraph. DO NOT translate, summarize, reorder, add or remove words.
DO NOT change numbers, English text, punctuation or line breaks ("\\n") — keep the same number of lines.
Return EXACTLY a JSON array of strings of length {len(texts)}, in the same order.

Input JSON:
{json.dumps(texts, ensure_ascii=False)}"""
            for attempt in range(3):
                try:
                    resp_text = ai_client.generate(ai_cfg, prompt, model=model_name).strip()
                    if resp_text.startswith("```"):
                        resp_text = resp_text.split("\n", 1)[1] if "\n" in resp_text else resp_text[3:]
                        resp_text = resp_text.rsplit("```", 1)[0]
                    fixed = json.loads(resp_text.strip())
                    if not isinstance(fixed, list) or len(fixed) != len(idx):
                        raise ValueError("JSON length mismatch")
                    for i, out in zip(idx, fixed):
                        lines = out.split("\n") if isinstance(out, str) else None
                        if lines is None or len(lines) != len(local[i]):
                            rejected += len(local[i])
                            continue
                        for k, line in enumerate(lines):
                            ok = accept_ai_text(local[i][k], line)
                            if ok is None:
                                rejected += 1
                            else:
                                chosen[i][k] = ok
                                accepted += 1
                    ai_batches += 1
                    if not system_key_allowed:
                        personal_batches += 1
                    break
                except Exception as e:
                    if ai_client.is_rate_limited(e) and attempt < 2:
                        import time
                        time.sleep(2)  # รอ 2 วินาทีแล้วลองใหม่
                        continue
                    logger.error(f"AI ({ai_cfg.provider}) fix failed for batch (attempt {attempt+1}): {e}")
                    status = "fallback"  # ชุดนี้ใช้ข้อความที่จัดรูปในเครื่อง
                    break

        if rejected:
            logger.info("AI แก้คำไทย: ใช้ %d ช่วง ปฏิเสธ %d ช่วง (เนื้อหาเปลี่ยนเกินที่อนุญาต)", accepted, rejected)
        apply_all()

        user_id = getattr(user, "id", None)
        ai_usage.add(user_id, ai_usage.AI_REQUEST, ai_batches)
        ai_usage.add(user_id, ai_usage.PERSONAL_REQUEST, personal_batches)
        if reserved_system_quota and status == "fallback":
            ai_usage.release(user.id, ai_usage.SYSTEM_CONVERSION)  # นับเฉพาะครั้งที่ AI แปลงสำเร็จจริง
        reserved_system_quota = False

        if progress_callback: progress_callback(100)
        return status
    except Exception as e:
        logger.error(f"Failed to post-process DOCX: {e}")
        if reserved_system_quota and user is not None:
            ai_usage.release(user.id, ai_usage.SYSTEM_CONVERSION)
        return "fallback"


def convert_pdf_to_docx(pdf_bytes: bytes, user: User = None, progress_callback=None):
    """แปลง PDF เป็น Word และแก้คำไทย คืนค่า (docx_bytes, status)"""
    pdf_bytes = upright_rotated_pages(pdf_bytes)  # หน้าที่หมุนไว้ → ข้อความแนวนอน (ดู pdf2docx_fixes.py)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf_path = tmp_pdf.name
        
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
        tmp_docx_path = tmp_docx.name
        
    try:
        if progress_callback: progress_callback(10)
        with patched_pdf2docx():  # กันรูปทรงโปร่งใส/gradient กลายเป็นกล่องสีดำ (ดู pdf2docx_fixes.py)
            cv = Converter(tmp_pdf_path)
            cv.convert(tmp_docx_path, start=0, end=None)
            cv.close()
        
        if progress_callback: progress_callback(50)
        status = _fix_thai_in_docx(tmp_docx_path, user, progress_callback)
        try:
            fixed_doc = Document(tmp_docx_path)
            fix_symbol_chars(fixed_doc)      # bullet ฟอนต์ Symbol/Wingdings (U+F0xx) → Unicode
            fix_table_grids(fixed_doc)       # ความกว้างคอลัมน์ตาราง (tblGrid) ตามช่องจริง
            split_heading_paragraphs(fixed_doc)  # หัวข้อ "2.1.6 ..." ที่ติดอยู่ในย่อหน้าก่อนหน้า → ย่อหน้าใหม่
            normalize_docx_fonts(fixed_doc)  # ฟอนต์/ขนาดอักษรไทยใน Word (complex script)
            # หัวข้อสีขาวที่ pdf2docx จับแถบสีพื้นหลังไม่ได้
            restore_light_text_backgrounds(fixed_doc, collect_light_text_backgrounds(tmp_pdf_path))
            fixed_doc.save(tmp_docx_path)
        except Exception:
            logger.warning("ปรับฟอนต์ใน DOCX ไม่สำเร็จ", exc_info=True)
        
        with open(tmp_docx_path, "rb") as f:
            docx_bytes = f.read()
            
        return docx_bytes, status
    finally:
        if os.path.exists(tmp_pdf_path):
            os.remove(tmp_pdf_path)
        if os.path.exists(tmp_docx_path):
            os.remove(tmp_docx_path)

def convert_scan_pdf_to_docx(pdf_bytes: bytes, user: User = None, use_ai: bool = False, progress_callback=None):
    """ไฟล์สแกน → Word ข้อความแก้ไขได้ (OCR บนเซิร์ฟเวอร์ ดู scan_docx) · use_ai: แก้คำไทยที่ OCR อ่านผิดด้วย AI
    (ใช้โควต้า AI — ผู้ใช้ต้องเลือกเอง) คืนค่า (docx_bytes, status) status = "scan" | "scan-ai" | "fallback" """
    from app.services import scan_docx

    def scaled(p):  # ถ้าตามด้วย AI: OCR ใช้ครึ่งแรกของแถบความคืบหน้า
        if progress_callback:
            progress_callback(int(p * 0.5) if use_ai else p)

    use_ai = use_ai and ai_client.available_for(user)  # ไม่ได้ตั้ง AI = ไม่มีตัวเลือกนี้ (กันคำขอที่ส่งมาตรงๆ)
    docx_bytes = scan_docx.convert_scan_to_docx(pdf_bytes, progress_callback=scaled)
    if not use_ai:
        return docx_bytes, "scan"
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(docx_bytes)
        path = tmp.name
    try:
        status = _fix_thai_in_docx(path, user, progress_callback, source="ocr")
        with open(path, "rb") as f:
            return f.read(), ("scan-ai" if status == "ai" else "fallback")
    finally:
        os.remove(path)


def process_conversion_task(task_id: str, mode: str = "editable", use_ai: bool = False):
    """mode: "editable" = แปลงเป็นย่อหน้า/ตารางแก้ไขได้ (pdf2docx + AI แก้คำไทย),
    "layout" = รักษาหน้าตาต้นฉบับ (ภาพพื้นหลัง + กล่องข้อความ — ดู layout_docx.py ไม่ใช้โควต้า AI),
    "scan" = ไฟล์สแกน (OCR — ดู scan_docx) · ไฟล์สแกนที่ส่งมาด้วยโหมดอื่นจะเปลี่ยนเป็น "scan" อัตโนมัติ
    (pdf2docx ไม่รองรับไฟล์สแกน: ได้รูปเต็มหน้าไม่มีข้อความ) — use_ai ใช้กับโหมด scan เท่านั้น"""
    from app.db.database import SessionLocal
    from app.models.domain import ConversionTask, FileRecord, User
    import traceback
    
    db = SessionLocal()
    try:
        task = db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
        if not task:
            return
            
        task.status = "processing"
        task.progress = 5
        db.commit()
        
        file_record = db.query(FileRecord).filter(FileRecord.id == task.file_record_id).first()
        if not file_record:
            raise Exception("ไม่พบข้อมูลไฟล์ในฐานข้อมูล")
            
        from app.services.file_storage import resolve_stored_pdf

        pdf_path = resolve_stored_pdf(file_record)
        if pdf_path is None:
            raise Exception("ไม่พบไฟล์ต้นฉบับบนเซิร์ฟเวอร์ (ไฟล์อาจถูกลบไปแล้ว)")

        user = db.query(User).filter(User.id == task.user_id).first()
            
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        def _update_progress(p):
            try:
                # Use a fresh session to update progress to avoid long transaction locks
                with SessionLocal() as prog_db:
                    prog_task = prog_db.query(ConversionTask).filter(ConversionTask.id == task_id).first()
                    if prog_task and prog_task.progress != p:
                        prog_task.progress = p
                        prog_db.commit()
            except Exception as e:
                logger.error(f"Failed to update task progress: {e}")
                
        if mode != "scan":
            from app.services import scan_docx

            if scan_docx.is_scanned_pdf(pdf_bytes):
                mode = "scan"
        if mode == "scan":
            docx_bytes, conv_status = convert_scan_pdf_to_docx(pdf_bytes, user, use_ai, progress_callback=_update_progress)
        elif mode == "layout":
            from app.services.layout_docx import convert_pdf_to_layout_docx

            docx_bytes, conv_status = convert_pdf_to_layout_docx(pdf_bytes, progress_callback=_update_progress), "layout"
        else:
            docx_bytes, conv_status = convert_pdf_to_docx(pdf_bytes, user, progress_callback=_update_progress)
        
        # Save output
        # เก็บใน UPLOAD_DIR (volume ที่เขียนได้เสมอ) — เดิมใช้ /data/conversions ซึ่งเป็นของ root ใน image
        # ทำให้แปลงไม่สำเร็จบน volume ใหม่ (CI/เครื่องใหม่) และบน k8s ที่ root filesystem อ่านอย่างเดียว
        out_dir = settings.UPLOAD_DIR / "_conversions"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{task_id}.docx"
        
        with open(out_path, "wb") as f:
            f.write(docx_bytes)
            
        task.status = "completed"
        task.progress = 100
        task.result_file_path = str(out_path)
        
        # We can store the conversion fallback status in error_message as a note if we want, or just leave it
        if conv_status in ("fallback", "basic", "scan", "scan-ai"):
            task.error_message = conv_status   # หมายเหตุให้หน้าจอเลือกข้อความแจ้งผล (ไม่ใช่ข้อผิดพลาด)
            
        db.commit()
        
    except Exception as e:
        logger.error(f"Conversion task failed: {e}\n{traceback.format_exc()}")
        try:
            task.status = "failed"
            task.error_message = str(e)
            db.commit()
        except:
            pass
    finally:
        db.close()
