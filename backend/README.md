# JA PDF Editor — Backend (FastAPI + PyMuPDF)

API ของ JA PDF Editor: เปิด/แก้ไข PDF ผ่าน session, คำอธิบายประกอบ, แก้ข้อความ/รูป, OCR, PDPA, แปลงไฟล์,
สร้างเอกสารอัตโนมัติ, ลายเซ็นและงานลงนาม, บัญชีผู้ใช้ (ภาพรวมทั้งระบบดู [`../README.md`](../README.md))

## ติดตั้งและรันนอก Docker

ต้องมี Python 3.11 และโปรแกรมระบบ: `tesseract-ocr` + `tesseract-ocr-tha`, LibreOffice (แปลง Office), Ghostscript

```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.template .env           # ตั้ง JWT_SECRET, FRONTEND_URL · DATABASE_URL ดีฟอลต์ postgres ที่ localhost:5432
                                # (ใช้ postgres ของ docker-compose.dev.yml ได้ที่พอร์ต 5433) · ไม่ตั้ง PDF_REDIS_URL = session ใน memory

uvicorn app.main:app --reload --port 8000
```

Swagger UI (รายการ API ทั้งหมดพร้อมทดลองเรียก): `http://localhost:8000/docs`

## ทดสอบ

```bash
pip install -r requirements-dev.txt
pytest -q                                    # SQLite + โฟลเดอร์ชั่วคราว ไม่ต้องมี Postgres/Redis
```

เทสต์ที่ต้องใช้ tesseract ภาษาไทย / LibreOffice / ไฟล์ทดสอบจริง (`THAI_CORPUS_DIR`) จะข้ามเองถ้าเครื่องไม่มี
ชุดวัดผลภาษาไทย (`scripts/thai_eval.py`, `ocr_eval.py`, `docx_eval.py`, `pii_eval.py`) ดูตารางใน README หลัก

ฐานข้อมูล: แอปรัน Alembic migration ให้เองตอน start (`app/db/migrations.py`) — แก้ model แล้วต้องสร้าง
migration ใหม่เสมอ: `alembic revision --autogenerate -m "อธิบายการเปลี่ยนแปลง"` (รันใน `backend/`)
test `test_schema_matches_models` จะ fail ถ้าลืม

## แนวคิดของสถาปัตยกรรม

- **Session-based**: อัปโหลด/เปิดไฟล์ 1 ครั้ง = 1 `session_id` ทุก endpoint ถัดไป (render/annotate/edit/download) อ้างอิงด้วย session_id นี้
- **ไม่แตะไฟล์ต้นฉบับ**: การแก้ไขทั้งหมดทำบน working copy · undo/redo เก็บ snapshot ทั้งเอกสาร (`session.push_history()` หลังทุกการแก้ไขที่สำเร็จ)
- **ตรวจสิทธิ์เจ้าของทุก endpoint**: route ที่รับ `{session_id}` ต้องใช้ `session: PDFSession = Depends(get_owned_session)` (ดู `app/api/deps.py`) — ผู้ที่ไม่ใช่เจ้าของได้ 404
- **Session store**: ไม่ตั้ง `PDF_REDIS_URL` = เก็บใน memory ของ process (single instance) / ตั้งค่า = `RedisSessionManager` รองรับหลาย replica: `with session.lock:` ถือ Redis lock ข้าม pod และโหลดสถานะล่าสุดเองถ้า pod อื่นเพิ่งแก้ไข (ต้องใช้ shared storage สำหรับ `/data` และ Redis `maxmemory-policy volatile-lru`)
- **แก้ข้อความ = redact แล้ววาดใหม่**: ลบข้อความเดิม (เติมสีพื้นหลังที่สุ่มจากหน้าจริง) แล้ววาดข้อความใหม่เป็นข้อความเวกเตอร์ด้วย fpdf2 + uharfbuzz (จัดรูปอักษรไทยถูกต้อง ยังค้นหา/คัดลอกได้) — ประวัติการตัดสินใจดู `app/services/edit_service/NOTES.md`
- **ข้อความไทยผ่านตัวกลางเดียว**: `app/services/thai_text.py` (จัดรูป/ตัดคำ) ใช้ทั้งการค้นหา เซ็นเซอร์ คัดลอก PDPA และแปลงเป็น Word · OCR อยู่ที่ `app/services/ocr_thai.py`

## กลุ่ม API หลัก

| Prefix | ไฟล์ | หน้าที่ |
|---|---|---|
| `/pdf` | `app/api/pdf/` | อัปโหลด (PDF/รูป/Office), เอกสารของฉัน, render, หน้า/บุ๊กมาร์ก, ลายน้ำ/รหัสผ่าน, เซ็นเซอร์, OCR, PDPA, บันทึก/ดาวน์โหลด |
| `/annotation` | `routes_annotation.py` | ไฮไลต์ กล่องข้อความ กรอบ โน้ต, คำในหน้า (สำหรับลากเลือก/คัดลอก) |
| `/edit` | `routes_edit.py` | แก้ข้อความ/รูปเดิม แทรกรูป ฟอนต์ |
| `/convert` | `routes_convert.py` | PDF → Word (งานเบื้องหลัง + ติดตามความคืบหน้า) |
| `/autogen` | `routes_autogen.py` | สร้างเอกสารอัตโนมัติ + ไฟล์ตัวอย่าง (`/autogen/samples/{name}`) |
| `/signature`, `/signing`, `/notifications` | `routes_signature.py`, `routes_signing.py` | ลายเซ็นอิเล็กทรอนิกส์/ดิจิทัล, งานลงนามหลายคน, หนังสือรับรองการลงนาม, การแจ้งเตือนในแอป |
| `/auth`, `/auth/passkeys`, `/auth/line`, `/line`, `/license` | `routes_auth.py`, `routes_passkey.py`, `routes_line_login.py`, `routes_line.py`, `routes_license.py` | บัญชีผู้ใช้, Passkey, เข้าสู่ระบบด้วย LINE, แจ้งเตือนทาง LINE, ใส่ license key อัปเกรดแพ็กเกจ |
| `/admin` | `routes_admin.py` | ผู้ใช้ แพ็กเกจ โควต้าบริการภายนอก |

## Troubleshooting: `MuPDF error: zlib error: incorrect header check` ตอนเปิดไฟล์ที่มีรหัสผ่าน

**อาการ**: unlock สำเร็จ (200), `/info` สำเร็จ (200), แต่พอ render หน้า (`/pdf/{id}/page/{n}`) log ขึ้น
`MuPDF error: library error: zlib error: incorrect header check` — แม้ endpoint จะตอบ 200 กลับมาก็ตาม

**สาเหตุ**: ไฟล์ PDF ที่เข้ารหัสและใช้โครงสร้าง compressed object streams (ObjStm — มาตรฐานของไฟล์ PDF
ที่สร้างจากโปรแกรมสมัยใหม่แทบทุกตัว) ทำให้ MuPDF ต้อง "แตะ" โครงสร้าง object บางส่วนตอน `fitz.open()`
เพื่อรู้จำนวนหน้า/โครงสร้างเอกสาร **ก่อน**ที่เราจะเรียก `authenticate()` ได้ด้วยซ้ำ ถ้า MuPDF พยายามอ่าน
object ที่อยู่ใน ObjStm ตอนนั้น (ยังไม่รู้รหัสผ่าน) แล้วแคชผลลัพธ์ที่ยังเป็น ciphertext ไว้ ต่อให้
`authenticate()` สำเร็จภายหลัง การ decompress object ที่แคชผิดไว้แล้วก็จะยังพังอยู่ดี — เป็นบั๊ก/ข้อจำกัด
ที่รู้กันในระดับ MuPDF ไม่ใช่ error จากโค้ดฝั่งเรา

**วิธีแก้ที่ใส่ไว้ในโค้ดแล้ว** (`app/services/pdf_service/core.py`, ฟังก์ชัน `unlock()`): หลัง `authenticate()`
สำเร็จ ระบบจะปิด document เดิมแล้วเปิดไฟล์เดียวกันขึ้นมาใหม่ทันที (fresh `fitz.Document` ที่ยังไม่เคย
ถูกแตะ object ใดๆ) แล้ว authenticate ซ้ำก่อนใช้งานต่อ วิธีนี้การันตีว่าไม่มี object/stream ใดถูกอ่านไป
ก่อนที่ระบบจะรู้รหัสผ่านที่ถูกต้อง ซึ่งแก้ปัญหานี้ได้ในเคสส่วนใหญ่

**เพิ่มเติมที่ทำไว้**: ปิดการพ่น error ดิบของ MuPDF ไปที่ stderr ตรงๆ (`fitz.TOOLS.mupdf_display_errors(False)`
ใน `app/main.py`) แล้วดึงข้อความเดียวกันมา log ผ่าน logging ของแอปแทน พร้อมระบุ session/หน้าที่เกิดปัญหา
(`_flush_mupdf_warnings()`) ทำให้ debug ง่ายขึ้นมากถ้าเจอไฟล์ที่ยังมีปัญหาอยู่ — เช็คใน log ว่าเป็น
`WARNING:pdf_service:...` แทนบรรทัด `MuPDF error:` ดิบๆ

**ถ้าลองแล้วยังเจอปัญหากับไฟล์เดิม**:
1. อัปเดต PyMuPDF เป็นเวอร์ชันล่าสุด (`pip install --upgrade pymupdf`) — บั๊กเกี่ยวกับการถอดรหัสสตรีมที่เข้ารหัส
   มักถูกแก้ไขต่อเนื่องในแต่ละเวอร์ชัน
2. ลองเปิดไฟล์เดิมด้วยโปรแกรมอื่น (เช่น Adobe Acrobat, Preview) แล้ว "Save As" ใหม่ — โปรแกรมเหล่านี้มัก
   ซ่อมโครงสร้างไฟล์ PDF ที่เสียหายบางส่วนโดยอัตโนมัติตอนเซฟ ถ้าไฟล์เปิดด้วยโปรแกรมอื่นได้ปกติแต่ยัง error
   ในระบบนี้ แปลว่าไฟล์อาจมีสตรีมที่เสียหายเฉพาะจุด (เช่น รูปภาพฝังในหน้านั้น) ซึ่งเป็นคนละปัญหากับ caching
   ด้านบน
3. ถ้ายังไม่หาย ส่งไฟล์ตัวอย่าง (เอาข้อมูลจริงออกก่อน) พร้อม log บรรทัด `WARNING:pdf_service:...` มาดู
   รายละเอียด error message ที่ชัดเจนขึ้นจะช่วยระบุว่า object ไหนของไฟล์ที่มีปัญหา

## ข้อจำกัดที่ควรรู้ (สำหรับพัฒนาต่อ)

- **ฟอนต์ตอนแก้ข้อความ**: วาดใหม่ด้วยฟอนต์ที่ใกล้เคียงที่สุดในระบบ (`fonts.match_pdf_font_name` — Sarabun (เอกสารที่ใช้ TH Sarabun New/PSK/IT๙ ก็ใช้ Sarabun แทน เพราะไม่ได้แนบไฟล์ TH Sarabun New มากับระบบ), Kanit, ฟอนต์จาก Google Fonts และฟอนต์ที่ผู้ใช้ติดตั้ง) ไม่ใช่ฟอนต์ที่ฝังในไฟล์เดิม
- **ตราลายเซ็นดิจิทัล**: ข้อความไทยบนตราเรนเดอร์เป็นรูปด้วย Pillow + RAQM (เอนจินข้อความของ pyHanko รองรับแค่ละติน) — `main.py` เตือนใน log ตอน start ถ้า Pillow ไม่มี RAQM
- **คำเตือน MuPDF ตอนเปิดไฟล์เข้ารหัสก่อน authenticate**: เป็น cosmetic warning ปกติ ไม่กระทบผลลัพธ์หลัง authenticate สำเร็จ
