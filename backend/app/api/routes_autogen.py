"""สร้างเอกสารอัตโนมัติ (Auto-Gen): Template Word (.docx, Jinja2 ผ่าน docxtpl) + ข้อมูล JSON/CSV/TXT/XLSX → Word/PDF

POST /autogen/preview  ข้อมูล 3 แถวแรก + ตรวจกับตัวแปรใน Template (ถ้าส่ง template มาด้วย)
POST /autogen/         สร้างเอกสาร — แยกไฟล์ (.zip) หรือรวมเป็นไฟล์เดียว

ความปลอดภัย: Template / ชื่อไฟล์ / รหัสผ่าน render ใน Jinja2 SandboxedEnvironment เสมอ
(Environment ธรรมดาเปิดทางให้รันโค้ด Python บนเซิร์ฟเวอร์ผ่าน {{ ''.__class__.__mro__... }} ใน Template ได้)
"""
import csv
import datetime as dt
import io
import json
import logging
import re
import urllib.parse
import zipfile
from pathlib import Path

import docx
import openpyxl
from docxcompose.composer import Composer
from docxtpl import DocxTemplate
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import get_current_active_user
from app.core.heavy import heavy_slot
from app.models.domain import User
from app.services import autogen_barcodes
from app.services.convert_service import convert_docx_batch_to_pdf, convert_office_to_pdf_bytes

logger = logging.getLogger("routes_autogen")

router = APIRouter(prefix="/autogen", tags=["Auto-Gen"])

# ไฟล์ตัวอย่างสำหรับดาวน์โหลดจากหน้าคู่มือ (หัวข้อเอกสารอัตโนมัติ) — ไม่ต้องล็อกอิน เปิดได้เฉพาะชื่อในรายการนี้
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "sample_autogen"
SAMPLE_FILES = {
    "template.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "data.json": "application/json",
    "template_flat.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "data_flat.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "data_flat.csv": "text/csv",
    # QR Code / บาร์โค้ด (scripts/create_qr_sample.py)
    "template_qr.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "data_qr.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "data_qr.csv": "text/csv",
}

DATA_EXTS = (".json", ".csv", ".txt", ".xlsx")
MAX_TEMPLATE_SIZE = 20 * 1024 * 1024
MAX_DATA_SIZE = 20 * 1024 * 1024
# จำนวนแถวสูงสุดต่อครั้ง — คำขอต้องเสร็จก่อน nginx ตัดที่ 120 วินาที (PDF แปลงด้วย LibreOffice ~0.3 วินาที/เอกสาร)
MAX_ROWS_PDF = 300
MAX_ROWS_DOCX = 2000
MAX_NAME_LEN = 150


@router.get("/samples/{name}")
def download_sample(name: str):
    if name not in SAMPLE_FILES or not (SAMPLES_DIR / name).is_file():
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ตัวอย่าง")
    return FileResponse(SAMPLES_DIR / name, media_type=SAMPLE_FILES[name], filename=f"autogen_sample_{name}")


_SANDBOX = None


def _sandbox():
    global _SANDBOX
    if _SANDBOX is None:
        from jinja2.sandbox import SandboxedEnvironment

        _SANDBOX = SandboxedEnvironment()
    return _SANDBOX


_DOCX_ENV = None


def _docx_env():
    """Jinja2 sandbox สำหรับ Template Word — autoescape: ค่าที่มี & < > ไม่ทำให้ไฟล์ .docx เสีย (XML)"""
    global _DOCX_ENV
    if _DOCX_ENV is None:
        from jinja2.sandbox import SandboxedEnvironment

        _DOCX_ENV = SandboxedEnvironment(autoescape=True)
    return _DOCX_ENV


def _cell_text(value) -> str:
    """ค่าจาก Excel/CSV เป็นข้อความ: 1234.0 → "1234" (Excel เก็บตัวเลขเป็น float), None → """""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _render_field_value(spec: str, context: dict) -> str:
    """ค่ารหัสผ่านต่อแถว: ชื่อคอลัมน์ตรงๆ (มีเว้นวรรคได้) หรือรูปแบบ {{ ... }} เช่น {{ emp_id }}{{ birth_year }}"""
    if "{{" in spec:
        return _sandbox().from_string(spec).render(**context).strip()
    return _cell_text(context.get(spec.strip()))


def _encrypt_pdf(pdf_bytes: bytes, password: str) -> bytes:
    """AES-256 แบบเดียวกับเมนูเข้ารหัส PDF (PDF 1.7 + Adobe Extension Level 8 — รองรับรหัสผ่านภาษาไทย)"""
    import os
    import tempfile

    import fitz

    from app.services import pdf_service

    doc = fitz.open("pdf", pdf_bytes)
    try:
        plain = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()
    fd, src = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    out = src + ".enc.pdf"
    try:
        with open(src, "wb") as fh:
            fh.write(plain)
        pdf_service.encrypt_pdf_file(src, out, password, "aes256")
        with open(out, "rb") as fh:
            return fh.read()
    finally:
        for p in (src, out):
            if os.path.exists(p):
                os.remove(p)


_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_name(name: str, default: str) -> str:
    """ชื่อไฟล์จากข้อมูล/ผู้ใช้ → ปลอดภัยสำหรับใส่ใน .zip และ header (ไม่มี / \\ : * ? " < > | ตัวควบคุม, ไม่ขึ้นต้นด้วยจุด)"""
    name = _BAD_NAME_CHARS.sub("_", str(name or "")).strip().strip(".").strip()
    name = re.sub(r"\s+", " ", name)[:MAX_NAME_LEN].strip()
    return name or default


def get_content_disposition(filename: str) -> str:
    encoded_name = urllib.parse.quote(filename)
    ascii_name = filename.encode("ascii", "ignore").decode("ascii").replace('"', "").replace("\\", "") or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=utf-8''{encoded_name}"


# ---------------------------------------------------------------- อ่านไฟล์ข้อมูล

def _clean_value(v):
    """ค่าจาก Excel: 1234.0 → 1234 · วันที่ที่ไม่มีเวลา → date (แสดงเป็น 2026-01-05 แทน 2026-01-05 00:00:00)"""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, dt.datetime) and v.time() == dt.time(0, 0):
        return v.date()
    if isinstance(v, str):
        return v.strip()
    return v


def _unique_headers(raw) -> list[str]:
    """ชื่อคอลัมน์: ตัดช่องว่างหัวท้าย (" name " → "name") · ว่าง → col_N · ซ้ำ → name_2"""
    out, seen = [], {}
    for i, h in enumerate(raw):
        h = str(h).strip() if h is not None else ""
        h = h or f"col_{i + 1}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 1
        out.append(h)
    return out


def _decode_text(content: bytes, encoding: str) -> tuple[str, str]:
    """ถอดรหัสไฟล์ข้อความ — "auto" ลอง UTF-8 ก่อนแล้วจึงภาษาไทยแบบเก่า (Windows-874/TIS-620 จาก Excel รุ่นเก่า)"""
    tries = ["utf-8-sig", "cp874"] if encoding in ("", "auto") else [encoding]
    for enc in tries:
        try:
            return content.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise HTTPException(status_code=400, detail="อ่านไฟล์ข้อความไม่ได้ — ลองเลือกการเข้ารหัสภาษา (Encoding) อื่น")


def _detect_delimiter(text: str, delimiter: str) -> str:
    if delimiter and delimiter != "auto":
        return delimiter
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def parse_data(filename: str, content: bytes, delimiter: str = "auto", encoding: str = "auto") -> tuple[list, dict]:
    """ไฟล์ข้อมูล → (รายการ dict ต่อแถว, ข้อมูลประกอบ {"encoding", "delimiter"})"""
    name = filename.lower()
    info: dict = {}
    if not name.endswith(DATA_EXTS):
        raise HTTPException(status_code=400, detail="Data ต้องเป็นไฟล์ JSON, CSV, TXT หรือ XLSX เท่านั้น")
    if len(content) > MAX_DATA_SIZE:
        raise HTTPException(status_code=413, detail="ไฟล์ข้อมูลใหญ่เกิน 20 MB")
    try:
        if name.endswith(".json"):
            data = json.loads(content.decode("utf-8-sig"))
            if not isinstance(data, list):
                raise HTTPException(status_code=400, detail="ข้อมูล JSON ขอบนอกสุดจะต้องเป็น Array [ ] เท่านั้น")
            return data, info
        if name.endswith((".csv", ".txt")):
            text, info["encoding"] = _decode_text(content, encoding)
            info["delimiter"] = _detect_delimiter(text, delimiter)
            rows = list(csv.reader(io.StringIO(text), delimiter=info["delimiter"]))
        else:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
            rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
            wb.close()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("อ่านไฟล์ข้อมูลไม่ได้: %s", e)
        raise HTTPException(status_code=400, detail=f"ไม่สามารถอ่านไฟล์ข้อมูลได้: {e}")
    rows = [r for r in rows if any(c not in (None, "") and str(c).strip() for c in r)]   # ข้ามแถวว่าง
    if len(rows) < 2:
        return [], info
    headers = _unique_headers(rows[0])
    data = [{h: _clean_value(row[i]) if i < len(row) else "" for i, h in enumerate(headers)} for row in rows[1:]]
    return data, info


def _numeric_headers(headers) -> bool:
    for h in headers:
        try:
            float(str(h).replace(",", ""))
            return True
        except ValueError:
            pass
    return False


def template_variables(template_bytes: bytes) -> set[str]:
    """ตัวแปรใน Template · รูปแบบ {{ }} / {% %} ผิด → HTTPException 400 พร้อมรายละเอียด"""
    from jinja2 import TemplateSyntaxError

    try:
        frame_vars: set[str] = set()
        if autogen_barcodes.uses_barcodes(template_bytes):
            # QR/บาร์โค้ด: ชื่อฟังก์ชันไม่ใช่คอลัมน์ · นิพจน์ใน Alt Text ของรูปตัวแทนนับตัวแปรด้วย
            template_bytes, exprs = autogen_barcodes.prepare(template_bytes)
            frame_vars = autogen_barcodes.frame_variables(exprs, _docx_env())
        found = set(DocxTemplate(io.BytesIO(template_bytes)).get_undeclared_template_variables(_docx_env()))
        return (found - set(autogen_barcodes.FUNCTIONS)) | frame_vars
    except TemplateSyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Template มีรูปแบบ {{{{ }}}} หรือ {{% %}} ไม่ถูกต้อง: {e.message}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"เปิดไฟล์ Template ไม่ได้ (ต้องเป็นไฟล์ Word .docx): {e}")


@router.post("/preview")
async def preview_data(
    data: UploadFile = File(...),
    template: UploadFile | None = File(None),
    csv_delimiter: str = Form("auto"),
    csv_encoding: str = Form("auto"),
    current_user: User = Depends(get_current_active_user),
):
    rows, info = parse_data(data.filename, await data.read(), csv_delimiter, csv_encoding)
    headers = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
    out = {
        "headers": headers,
        "rows": [{k: (str(v) if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in r.items()}
                 if isinstance(r, dict) else r for r in rows[:3]],
        "total_records": len(rows),
        "has_numeric_header_warning": _numeric_headers(headers),
        "encoding": info.get("encoding"),
        "delimiter": info.get("delimiter"),
        "max_rows_pdf": MAX_ROWS_PDF,
        "max_rows_docx": MAX_ROWS_DOCX,
    }
    if template is not None and template.filename:
        variables = template_variables(await template.read())
        out["template_variables"] = sorted(variables)
        out["missing_variables"] = sorted(variables - set(headers)) if headers else []
    return out


def _row_name(context: dict, filename_field: str | None, index: int) -> str:
    """ชื่อไฟล์ย่อยของแถว: รูปแบบ {{ }} / ชื่อคอลัมน์คั่นด้วยช่องว่าง / ค่าคอลัมน์แรก / document_N"""
    default = f"document_{index + 1}"
    if filename_field:
        if "{{" in filename_field:
            try:
                rendered = _sandbox().from_string(filename_field).render(**context).strip()
                if rendered:
                    return safe_name(rendered, default)
            except Exception as e:  # noqa: BLE001
                logger.warning("ตั้งชื่อไฟล์จากรูปแบบไม่ได้: %s", e)
        else:
            vals = [_cell_text(context.get(p)) for p in filename_field.split() if _cell_text(context.get(p))]
            if vals:
                return safe_name(" ".join(vals), default)
    if context:
        return safe_name(_cell_text(next(iter(context.values()))), default)
    return default


@router.post("/")
async def auto_generate_documents(
    template: UploadFile = File(...),
    data: UploadFile = File(...),
    output_format: str = Form("docx"),
    split_files: bool = Form(True),
    filename_field: str = Form(None),
    output_filename: str = Form(None),
    password_field: str = Form(None),
    csv_delimiter: str = Form("auto"),
    csv_encoding: str = Form("auto"),
    current_user: User = Depends(get_current_active_user),
):
    if output_format not in ("docx", "pdf"):
        raise HTTPException(status_code=400, detail="รูปแบบผลลัพธ์ต้องเป็น docx หรือ pdf")
    password_field = (password_field or "").strip() or None
    if password_field and not (split_files and output_format == "pdf"):
        raise HTTPException(status_code=400, detail="เข้ารหัสด้วยรหัสผ่านจากคอลัมน์ได้เฉพาะแบบ \"แยกไฟล์\" และผลลัพธ์เป็น PDF")
    if not (template.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Template ต้องเป็นไฟล์ .docx เท่านั้น")

    rows, _info = parse_data(data.filename, await data.read(), csv_delimiter, csv_encoding)
    if not rows:
        raise HTTPException(status_code=400, detail="ไม่มีข้อมูลในไฟล์ Data (ไฟล์ว่างเปล่า หรือไม่มีข้อมูลแถวที่ 2)")
    limit = MAX_ROWS_PDF if output_format == "pdf" else MAX_ROWS_DOCX
    if len(rows) > limit:
        raise HTTPException(status_code=400, detail=f"ข้อมูลมี {len(rows):,} แถว — สร้างแบบ {output_format.upper()} ได้ครั้งละไม่เกิน "
                                                    f"{limit:,} แถว แบ่งไฟล์ข้อมูลเป็นหลายชุดแล้วสร้างทีละชุด")

    template_bytes = await template.read()
    if len(template_bytes) > MAX_TEMPLATE_SIZE:
        raise HTTPException(status_code=413, detail="ไฟล์ Template ใหญ่เกิน 20 MB")
    variables = template_variables(template_bytes)
    frame_exprs: list[str] = []
    with_barcodes = autogen_barcodes.uses_barcodes(template_bytes)
    if with_barcodes:
        template_bytes, frame_exprs = autogen_barcodes.prepare(template_bytes)

    if isinstance(rows[0], dict):
        headers = set(rows[0].keys())
        if password_field and "{{" not in password_field and password_field not in headers:
            raise HTTPException(status_code=400, detail=f"ไม่พบคอลัมน์ \"{password_field}\" สำหรับรหัสผ่านในไฟล์ข้อมูล")
        if _numeric_headers(headers) and not data.filename.lower().endswith(".json"):
            raise HTTPException(status_code=400, detail="ตรวจพบข้อมูลตัวเลขในบรรทัดหัวตาราง (Header) กรุณาตรวจสอบว่าไฟล์ข้อมูลมีบรรทัดหัวตารางหรือไม่ (บรรทัดแรกต้องเป็นชื่อคอลัมน์เสมอ)")
        if variables and not variables & headers:
            raise HTTPException(status_code=400, detail="ไม่พบชื่อคอลัมน์ (Header) ที่ตรงกับตัวแปรใน Template เลย กรุณาตรวจสอบว่ามีบรรทัดหัวตาราง หรือพิมพ์ชื่อคอลัมน์ตรงกับใน Word หรือไม่")

    rendered: list[bytes] = []
    names: list[str] = []
    passwords: list[str] = []
    errors: list[tuple[int, str]] = []
    row_codes: list[autogen_barcodes.RowBarcodes] = []
    indexes: list[int] = []
    used: set[str] = set()
    for index, item in enumerate(rows):
        context = item if isinstance(item, dict) else {"item": item}
        try:
            doc = DocxTemplate(io.BytesIO(template_bytes))
            codes = autogen_barcodes.RowBarcodes()
            # qr()/barcode() ทับคอลัมน์ชื่อเดียวกัน (คู่มือบอกให้ตั้งชื่อคอลัมน์อื่น)
            doc.render({**context, **codes.functions()} if with_barcodes else context, jinja_env=_docx_env(), autoescape=True)
            if frame_exprs:
                codes.evaluate_frames(frame_exprs, _docx_env(), context)
            buf = io.BytesIO()
            doc.save(buf)
            pw = None
            if password_field:
                pw = _render_field_value(password_field, context)
                if not pw:
                    # ไม่มีรหัสผ่าน → ไม่ใส่ไฟล์ (ห้ามหลุดเป็นไฟล์ไม่เข้ารหัส) แจ้งเป็นไฟล์ error แทน
                    raise ValueError(f"ไม่มีค่ารหัสผ่านในคอลัมน์/รูปแบบ \"{password_field}\" — ไม่ได้สร้างไฟล์นี้")
            base = _row_name(context, filename_field, index)
            name, n = base, 2
            while name.lower() in used:                       # ชื่อซ้ำ → -2, -3 (ไม่ทับไฟล์ใน .zip)
                name, n = f"{base}-{n}", n + 1
            used.add(name.lower())
            names.append(name)
            passwords.append(pw)
            rendered.append(buf.getvalue())
            row_codes.append(codes)
            indexes.append(index)
        except Exception as e:  # noqa: BLE001
            logger.info("Auto-Gen แถวที่ %d สร้างไม่ได้: %s", index + 1, e)
            errors.append((index, str(e)))

    if with_barcodes and rendered:
        # สร้างรูป QR/บาร์โค้ดของทุกแถวในครั้งเดียว (ค่าซ้ำสร้างครั้งเดียว) แล้วใส่ลงไฟล์ของแต่ละแถว
        from fastapi.concurrency import run_in_threadpool

        def _build():
            with heavy_slot("autogen-barcode"):
                return autogen_barcodes.render_all(row_codes)

        images = await run_in_threadpool(_build)
        keep = []
        for k, codes in enumerate(row_codes):
            err = autogen_barcodes.first_error(codes, images)
            if err:
                errors.append((indexes[k], err))
                continue
            try:
                rendered[k] = autogen_barcodes.apply(rendered[k], codes, images)
                keep.append(k)
            except Exception as e:  # noqa: BLE001
                logger.warning("ใส่บาร์โค้ดแถว %d ไม่สำเร็จ: %s", indexes[k] + 1, e)
                errors.append((indexes[k], f"ใส่ QR/บาร์โค้ดไม่สำเร็จ: {e}"))
        rendered = [rendered[k] for k in keep]
        names = [names[k] for k in keep]
        passwords = [passwords[k] for k in keep]
        errors.sort()

    if not rendered:
        first = errors[0][1] if errors else ""
        raise HTTPException(status_code=400, detail=f"สร้างเอกสารไม่ได้เลยสักรายการ — {first}")
    stats = {"X-Autogen-Created": str(len(rendered)), "X-Autogen-Errors": str(len(errors)),
             "Access-Control-Expose-Headers": "X-Autogen-Created, X-Autogen-Errors, Content-Disposition"}

    if split_files:
        pdfs = await _to_pdf_many(rendered, current_user.id) if output_format == "pdf" else None
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, doc_bytes in enumerate(rendered):
                if pdfs is not None:
                    pdf_bytes = _encrypt_pdf(pdfs[i], passwords[i]) if password_field else pdfs[i]
                    zf.writestr(f"{names[i]}.pdf", pdf_bytes)
                else:
                    zf.writestr(f"{names[i]}.docx", doc_bytes)
            for index, err_msg in errors:
                zf.writestr(f"error_item_{index + 1}.txt", f"แถวข้อมูลที่ {index + 1}: เกิดข้อผิดพลาด — {err_msg}".encode("utf-8"))
        zip_buffer.seek(0)
        final = safe_name(re.sub(r"\.zip$", "", output_filename or "", flags=re.I), "autogen_result") + ".zip"
        return StreamingResponse(zip_buffer, media_type="application/zip",
                                 headers={"Content-Disposition": get_content_disposition(final), **stats})

    composer = Composer(docx.Document(io.BytesIO(rendered[0])))
    for doc_bytes in rendered[1:]:
        composer.doc.add_page_break()            # ขึ้นหน้าใหม่ก่อนต่อเอกสารถัดไป
        composer.append(docx.Document(io.BytesIO(doc_bytes)))
    merged_buffer = io.BytesIO()
    composer.save(merged_buffer)
    merged_bytes = merged_buffer.getvalue()
    final = safe_name(re.sub(r"\.(pdf|docx)$", "", output_filename or "", flags=re.I), "autogen_merged")
    if output_format == "pdf":
        final_pdf = await convert_office_to_pdf_bytes(merged_bytes, "merged.docx", user_id=current_user.id)
        return StreamingResponse(io.BytesIO(final_pdf), media_type="application/pdf",
                                 headers={"Content-Disposition": get_content_disposition(f"{final}.pdf"), **stats})
    return StreamingResponse(io.BytesIO(merged_bytes),
                             media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             headers={"Content-Disposition": get_content_disposition(f"{final}.docx"), **stats})


async def _to_pdf_many(docs: list[bytes], user_id: int) -> list[bytes]:
    """แปลงทีละชุด (LibreOffice เริ่มครั้งเดียวต่อชุด) — ชุดละ 50 ไฟล์ กันคำสั่งยาวเกินและหน่วยความจำ"""
    if len(docs) == 1:
        return [await convert_office_to_pdf_bytes(docs[0], "doc.docx", user_id=user_id)]
    out: list[bytes] = []
    for k in range(0, len(docs), 50):
        out += await convert_docx_batch_to_pdf(docs[k:k + 50], user_id=user_id)
    return out
