# JA PDF Editor — ระบบจัดการเอกสาร PDF ครบวงจร

[![CI](https://github.com/jaturon2526/pdf_editor_fullstack/actions/workflows/ci.yml/badge.svg)](https://github.com/jaturon2526/pdf_editor_fullstack/actions/workflows/ci.yml)

ระบบจัดการเอกสาร PDF ครบวงจร ทำงานบนเว็บเบราว์เซอร์ — แก้ไขข้อความ/รูปภาพ, คำอธิบายประกอบ, รวม/แยกไฟล์, ลายน้ำ, เข้ารหัส,
ลายเซ็นอิเล็กทรอนิกส์และดิจิทัล, ส่งเอกสารให้ลงนามตามลำดับ, ปกปิดข้อมูลส่วนบุคคล (PDPA), OCR, แปลง Office ↔ PDF ↔ Word
และสร้างเอกสารอัตโนมัติ — ออกแบบมาเพื่อเอกสารภาษาไทยโดยเฉพาะ พัฒนาร่วมกับ AI (Antigravity — Google DeepMind)

**ซอฟต์แวร์เสรีภายใต้ [GNU AGPL-3.0](LICENSE)** — ใช้ ศึกษา แก้ไข และติดตั้งเองได้ฟรี · ดู [License](#license)

คู่มือผู้ใช้ฉบับเต็มอยู่ในแอป: ปุ่ม **คู่มือ** ที่หน้าเอกสารของฉัน หรือเมนู **วิธีใช้ → คู่มือการใช้งาน** ใน Editor (`frontend/public/manual.html`)

---

## สถาปัตยกรรม (Architecture)

```
┌──────────────────────────────────────────────────┐
│                    Client (Browser)               │
└───────────────────────┬──────────────────────────┘
                        │ HTTP :8080 (dev) / :80 (prod)
┌───────────────────────▼──────────────────────────┐
│              Nginx (Frontend Container)           │
│  ├─ เสิร์ฟไฟล์ React SPA (static) + คู่มือ          │
│  └─ Reverse Proxy /api/ → backend:8000            │
└───────────────────────┬──────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────┐
│            FastAPI (Backend Container)             │
│  ├─ PDF: PyMuPDF, fpdf2 + uharfbuzz, pikepdf,     │
│  │       Ghostscript, pyHanko (PAdES)             │
│  ├─ แปลงไฟล์: LibreOffice (Office→PDF),           │
│  │            pdf2docx + python-docx (PDF→Word)   │
│  ├─ ภาษาไทย: PyThaiNLP, Tesseract (tha+eng)       │
│  ├─ Auth: JWT, bcrypt, Google, LINE, Passkey      │
│  └─ AI: Gemini / Claude / OpenAI — ไม่บังคับ       │
├───────────────┬──────────────────────────────────┤
│  PostgreSQL   │           Redis                   │
│ (ผู้ใช้/ไฟล์/  │  (PDF session, ล็อก, auth session) │
│  งานลงนาม)    │                                   │
└───────────────┴──────────────────────────────────┘
  บริการภายนอก (ไม่บังคับ): SMTP/Brevo (อีเมล), LINE Messaging/Login, Google OAuth, AI (Gemini / Claude / OpenAI-compatible), TSA (timestamp)
```

ข้อความในเอกสารประมวลผลบนเซิร์ฟเวอร์ทั้งหมด — ส่งออกไปผู้ให้บริการ AI ที่ตั้งไว้เฉพาะเมื่อผู้ใช้เลือกใช้ฟีเจอร์ AI
(แก้คำไทยตอนแปลงเป็น Word / ดึงข้อความด้วย AI) ส่วนการตรวจหาข้อมูลส่วนบุคคล (PDPA) ไม่ส่งออกภายนอกเลย

---

## ฟีเจอร์ทั้งหมด (Features)

### 📄 เอกสารของฉัน (Dashboard)
| ฟีเจอร์ | คำอธิบาย |
|---------|----------|
| อัปโหลดไฟล์ (หลายไฟล์/ลากวาง) | **PDF**, **รูปภาพ** (PNG/JPG → PDF พร้อมชั้นข้อความ OCR ภาษาไทย หมุนภาพถ่ายตาม EXIF) และ **ไฟล์ Office** (Word/Excel/PowerPoint → แปลงเป็น PDF ด้วย LibreOffice) — เก็บเป็น PDF เสมอ |
| จัดการไฟล์ | มุมมองการ์ด/ตาราง, ค้นหาชื่อ, เปลี่ยนชื่อ, ดาวน์โหลด, คุณสมบัติเอกสาร, ลบทีละไฟล์หรือเลือกหลายไฟล์ |
| แปลง PDF เป็น Word | 2 แบบ: **แก้ไขได้อิสระ** (ย่อหน้า/ตาราง คงรูปแบบตัวอักษรของแต่ละคำ เส้นใต้/ไฮไลต์ตรงกับข้อความ bullet ฟอนต์ Symbol เป็น Unicode จัดรูปสระ/วรรณยุกต์ไทย + AI แก้คำผิดโดยตรวจผลก่อนใช้) และ **รักษาหน้าตาต้นฉบับ** (พื้นหลัง + กล่องข้อความ ไฮไลต์/เส้นใต้เป็นรูปแบบตัวอักษร) · **ไฟล์สแกน** ตรวจอัตโนมัติ → OCR บนเซิร์ฟเวอร์เป็น Word ข้อความแก้ไขได้ (ย่อหน้า/ตารางมีเส้น/หัวตารางพื้นเข้ม/จุดไข่ปลาเป็นแท็บ/ช่องติ๊ก ☐) ลายเซ็น/โลโก้/บาร์โค้ดเป็นรูป ฟอนต์ Sarabun ฝังในไฟล์ · AI แก้คำเป็นตัวเลือก (`app/services/scan_docx/`) |
| เปรียบเทียบเอกสาร | 2 ไฟล์ (ไฟล์ในบัญชี / เอกสารที่เปิดอยู่รวมการแก้ที่ยังไม่บันทึก / อัปโหลด / **เวอร์ชันก่อนหน้า** = สำเนาก่อนบันทึกทับครั้งล่าสุด `{storage}_prev.pdf`) · ข้อความ: ตัดคำไทย (pythainlp) + difflib ทั้งเอกสาร (ข้อความที่ไหลข้ามหน้าไม่นับ) จับคู่หน้าตามเนื้อหา (หน้าแทรก/ลบ) · ภาพ: ต่างพิกเซลนอกบริเวณข้อความ (OpenCV) · หน้าสแกน OCR · หน้าเว็บเคียงข้าง/ซ้อนทับ + รายการจุดต่าง · รายงาน PDF (`services/compare_service/`, `api/routes_compare.py`, งานเบื้องหลังเข้าคิวงานหนัก ผลเก็บ 24 ชม.) |
| เข้ารหัส PDF / ปกปิดข้อมูลส่วนบุคคล | สร้างไฟล์ใหม่ "(เข้ารหัส)" / "(PDPA)" โดยไม่แตะไฟล์เดิม · เข้ารหัสด้วย pikepdf: AES-256 (R6, PDF 1.7 + Adobe Extension Level 8, ค่าเริ่มต้น) หรือ AES-128 (R4, รหัสผ่าน Latin-1 ≤ 32 ตัว) · ไฟล์ที่ประกาศ PDF/A จะเตือนและเอา pdfaid ออกเมื่อเข้ารหัส |
| สแกนเอกสาร (มือถือ/แท็บเล็ต) | กล้องหลัง + จับขอบกระดาษอัตโนมัติ (OpenCV.js ใน Web Worker) → ลาก 4 มุมเอง → ดัดภาพ ลบเงา เป็นขาวดำ/สีเทา/สี → ถ่ายต่อเนื่องหลายหน้า (เตือนภาพเบลอ/แสงสะท้อน) → PDF ตามสัดส่วนกระดาษจริง + ชั้นข้อความ OCR (ค้นหา/เซ็นเซอร์ได้ · โหมดขาวดำส่งภาพเทา `ocr_pages` มาให้อ่านคู่กัน เลือกผลที่ดีกว่าทีละหน้า) ชื่อไฟล์ `Scan_YYYYMMDD_HHmmss` · หน้าที่ถ่ายเก็บใน IndexedDB กู้ได้ถ้าแท็บถูกปิด |
| เครื่องมือด่วน | สแกนเอกสาร (เฉพาะจอสัมผัส), แปลงเป็น Word (PDF ทั่วไป/ไฟล์สแกน ตรวจอัตโนมัติ), สร้างเอกสารอัตโนมัติ, รวมไฟล์ PDF (ไฟล์จากเครื่อง + เอกสารของฉัน ≤ 30 ไฟล์ บันทึกเป็นไฟล์ใหม่ บุ๊กมาร์กตามไฟล์เดิม), ใส่ลายน้ำ (ตัวอย่างสด · กึ่งกลางตามที่มองเห็นบนหน้าที่หมุน · ย่อให้พอดีหน้า), เซ็นเซอร์ด้วยคำค้นหา (ลบคำจากช่องฟอร์ม โน้ต บุ๊กมาร์ก และ metadata ด้วย · ไม่รับ regex ซ้ำซ้อนแบบ `(a+)+` กัน ReDoS), ปกปิดข้อมูลส่วนบุคคล, ติดตั้งฟอนต์ (ท้ายสุดเสมอ), การลงนาม (รอฉันลงนาม / ส่งให้ลงนาม / ที่ฉันส่ง) |
| ติดตั้งฟอนต์ | **จากลิงก์ Google Fonts** (หน้าฟอนต์ / ลิงก์ CSS / ชื่อฟอนต์ → ตรวจลิงก์ ดูตัวอย่างทุกสไตล์ → ติดตั้ง 4 สไตล์เป็นตระกูลเดียว · รับเฉพาะ https ของโดเมนที่เชื่อถือได้ตาม `FONT_URL_ALLOWED_HOSTS` ไฟล์จาก fonts.gstatic.com เท่านั้น) หรือ **จากไฟล์** .ttf/.otf/.woff/.woff2 (แปลง WOFF เป็น sfnt, ไม่รับ .ttc, ≤ 20 MB, ≤ 100 ไฟล์ต่อบัญชี, ไม่ติดตั้งไฟล์ซ้ำ, เตือนเมื่อไม่มีอักษรไทย/ห้ามฝัง) — ฟอนต์ผูกกับบัญชี · แก้ข้อความด้วยฟอนต์ที่ไม่มีอักษรที่พิมพ์ → 400 (เดิมอักษรหายเงียบ) |
| สร้างเอกสารอัตโนมัติ (Auto-Gen) | Template Word (Jinja2: เงื่อนไข/คำนวณ/วนลูปตาราง) + ข้อมูล Excel/CSV/JSON → PDF/Word แยกไฟล์หรือรวมไฟล์ เข้ารหัสแต่ละไฟล์ด้วยรหัสจากคอลัมน์ได้ · **QR/บาร์โค้ด** `{{ qr(ลิงก์) }}` `{{ barcode("code128", รหัส, 50) }}` ในข้อความ หรือรูปตัวแทนที่ใส่นิพจน์ใน Alt Text (คงกรอบที่ออกแบบ) — สร้างทุกแถวใน Ghostscript รอบเดียว (`services/autogen_barcodes.py`, `barcode_service.render_png_batch`) — มีไฟล์ตัวอย่างให้ดาวน์โหลดในคู่มือ · Template render ใน Jinja2 sandbox · ตรวจตัวแปรกับคอลัมน์ก่อนสร้าง · CSV เดา encoding/ตัวคั่น · PDF แปลงด้วย LibreOffice ครั้งเดียวต่อ 50 ไฟล์ · ≤ 300 แถว (PDF) / 2,000 แถว (Word) |

### ✏️ แก้ไขเอกสาร (Editor)
| เมนู | ฟีเจอร์ |
|------|---------|
| ไฟล์ | เปิด PDF (เปิดซ้ำไม่ทิ้งสำเนาเก่า · ไฟล์ที่ไม่มีใครอ้างใน UPLOAD_DIR ถูกเก็บกวาดหลัง 24 ชม.), สร้างจาก Office (บันทึกเป็น PDF ในเอกสารของฉัน), บันทึก/บันทึกเป็นไฟล์ใหม่ (ชื่อไฟล์ปลอดภัย ไม่ซ้ำ · เตือนก่อนทิ้งการแก้ไขที่ยังไม่บันทึก), ดาวน์โหลด (ไม่บันทึกทับไฟล์ในบัญชี), พิมพ์ (ไฟล์พิมพ์ไม่เข้ารหัส รวม annotation), แยกหน้า (PDF เดียวหรือ ZIP · เรียงตามที่พิมพ์ เช่น `5, 1-3` · คงฟอร์ม/ลิงก์/บุ๊กมาร์ก · ใส่รหัสผ่านตามเอกสาร · ชื่อไฟล์ไทยได้), เพิ่ม/ลบรหัสผ่าน, คุณสมบัติเอกสาร + สถานะลายเซ็นดิจิทัล |
| แก้ไข / มุมมอง | เลิกทำ/ทำซ้ำทุกการกระทำ, ซูม, คีย์ลัด |
| แทรก | ข้อความ (ฟอนต์ไทย/สี/ขนาด, ตัดบรรทัดตามคำไทย · ไม่ลบข้อความเดิมใต้กล่อง), รูปภาพ · **เลขหน้า** (1/N, เลขไทย, เริ่มหน้าที่เลือก, หน้าคู่สลับข้างสำหรับพิมพ์สองหน้า — `edit_service/page_numbers.py`, ใช้จาก Dashboard ได้) · **บาร์โค้ด/QR** 11 ประเภท (QR/Data Matrix/PDF417/Aztec ภาษาไทย UTF-8+ECI, ตรวจเลขตรวจสอบ EAN/UPC, เวกเตอร์ — BWIPP ผ่าน treepoem + Ghostscript, `services/barcode_service.py`) |
| คำอธิบายประกอบ | ไฮไลต์ (snap ตามบรรทัด · หลายบรรทัด = annotation เดียวหลาย quad), กล่องข้อความ/กรอบสี่เหลี่ยม (appearance stream วาดเองด้วย fpdf2+HarfBuzz ฝังฟอนต์ไทย — ทุกโปรแกรมอ่าน PDF เห็นเหมือนกัน), โน้ต |
| เครื่องมือ | แก้ไขข้อความเดิม (redact + วาดใหม่เป็นข้อความเวกเตอร์), แก้ไข/ย้าย/ปรับขนาดรูป (ซ่อนรูปเดิมเฉพาะตำแหน่ง ไม่ redact ทั้งกรอบ), เซ็นเซอร์แบบลาก, **เซ็นเซอร์ด้วยคำค้นหา** (เข้าใจข้อความไทยที่ฟอนต์เก็บผิดรูป), **อ่านข้อความในรูปภาพ (OCR)** → ค้นหา/คัดลอก/เซ็นเซอร์ได้, **ตรวจหาข้อมูลส่วนบุคคล (PDPA)** (รวมค่าในช่องฟอร์ม/กล่องข้อความ/บันทึกย่อ · อ่านข้อความเนื้อหน้าโดยไม่รวม annotation ด้วย `text_index.content_page`), ลายน้ำ, ลดขนาดไฟล์ (Ghostscript เฉพาะเมื่อข้อความทุกหน้ายังเหมือนเดิม ไม่งั้นบีบเฉพาะรูปด้วย pikepdf/Pillow · gs ทุกจุดใช้ `-dPreserveMarkedContent=true` คง ActualText ของไทยจาก LibreOffice), รวมเลเยอร์ (MuPDF `bake()` — ไม่ผ่าน Ghostscript เนื้อหน้า/ฟอนต์เดิมไม่ถูกเขียนใหม่) |
| ลายเซ็นดิจิทัล | ลายเซ็นอิเล็กทรอนิกส์ (วาด/อัปโหลด/แผ่นเซ็นบนมือถือ), เซ็นรับรองด้วยใบรับรอง .p12/.pfx (PAdES · ตรวจใบรับรองก่อนวางตำแหน่ง `/signature/check-certificate` · พิกัดผ่าน `~page.transformation_matrix` รองรับหน้าหมุน/CropBox) |
| คัดลอกข้อความ | ลากเลือกแล้วคัดลอก (เรียงสระ/วรรณยุกต์ไทยถูกต้อง) หรือ "ดึงข้อความด้วย AI (OCR)" — AI ของ API key ส่วนตัว (Gemini / Claude / OpenAI) ถ้ามี ไม่งั้น Tesseract ที่ปรับมาสำหรับภาษาไทย |
| แถบข้าง | Thumbnail (เลื่อนตามหน้าที่ดู · selection ตามหน้าที่ย้าย), บุ๊กมาร์ก (บันทึกลงสารบัญของ PDF · คงโครงสร้างหลายชั้น/จุดหมายเดิม/ลิงก์เว็บ · แทรกตามลำดับหน้า), ลากจัดเรียง/หมุน/ลบหน้า (เหลืออย่างน้อย 1 หน้า · ลบบุ๊กมาร์กของหน้าที่ลบ · กันเอกสารที่เซ็นดิจิทัลแล้ว) |

### ✍️ ส่งเอกสารให้ลงนาม (Signing)
ส่งให้หลายคนลงนาม **ตามลำดับ** หรือ **พร้อมกัน**, เชิญคนที่ยังไม่มีบัญชี, ลงนามด้วยลายมือหรือ Passkey, เตือนอัตโนมัติก่อนครบกำหนด,
แจ้งเตือนทางอีเมลหรือ LINE, **หนังสือรับรองการลงนาม (Certificate of Completion)** พร้อมหลักฐาน, ไฟล์ที่ลงนามครบกลับเข้าเอกสารของผู้ส่ง
· ตรวจรูปลายมือชื่อ (ไม่ใช่รูป/ว่าง/ใหญ่ผิดปกติ → 400, หมุนตาม EXIF) · เวลาบนตราตาม `APP_TIMEZONE` · IP ในหลักฐานจาก `X-Real-IP` (nginx) ไม่ใช่ค่าแรกของ `X-Forwarded-For` · ดาวน์โหลด chain ใบรับรอง (AIA) เฉพาะโฮสต์สาธารณะ ไม่ตาม redirect (กัน SSRF)

### 🔒 ปกปิดข้อมูลส่วนบุคคล (PDPA)
ตรวจเลขประจำตัวประชาชน/ผู้เสียภาษี (ตรวจ check digit), บัตรเครดิต (Luhn), เบอร์โทร, อีเมล, เลขบัญชี, ชื่อ-นามสกุล
(คำนำหน้า ยศ ตำแหน่งวิชาการ ราชสกุล ชื่อที่ถูกตัดข้ามบรรทัด หัวข้อแบบฟอร์ม) และที่อยู่ — รองรับเลขไทย,
ตรวจทานก่อนปิดทับถาวร, ล้างข้อมูลเมตา, รายงานการปกปิด (CSV)

### 👤 บัญชีผู้ใช้และผู้ดูแลระบบ
| ฟีเจอร์ | คำอธิบาย |
|---------|----------|
| เข้าสู่ระบบ | อีเมล + รหัสผ่าน (ยืนยันอีเมล), Google, LINE, Passkey |
| บัญชี | โปรไฟล์, เปลี่ยน/ลืมรหัสผ่าน, ผูก LINE สำหรับแจ้งเตือน, ตั้ง API Key ส่วนตัวสำหรับ AI (เลือกผู้ให้บริการได้), ลบบัญชี · **รูปโปรไฟล์** อัปโหลด (ครอป, ลบ EXIF) หรืออีโมจิ 18 แบบวาดด้วย Pillow เปลี่ยนสีได้ (`services/avatar_service.py`, เก็บใน `users.avatar_png`) |
| แพ็กเกจและโควต้า | พื้นที่เก็บไฟล์และจำนวนอุปกรณ์ตามแพ็กเกจ (free / pro / premium — ตั้งในหน้าแอดมิน) · แพ็กเกจมีวันหมดอายุ ครบแล้วกลับเป็น free อัตโนมัติ |
| ☕ สนับสนุนผู้พัฒนา | หน้า `/support`: QR พร้อมเพย์ตามยอด (EMVCo สร้างในเครื่อง `services/promptpay.py`) → แจ้งโอน + สลิป → แอดมินตรวจ/อนุมัติ → ได้แพ็กเกจชั่วคราวตามระดับยอด · หน้า `/supporters` รายชื่อ (แสดงชื่อหรือไม่ออกนาม ไม่แสดงยอด) · เลขพร้อมเพย์และระดับสิทธิ์ตั้งในหน้าแอดมิน (เก็บในฐานข้อมูล ไม่อยู่ใน `.env`) · **ปิดเป็นค่าเริ่มต้น** · สลิปลบทันทีที่ตรวจเสร็จ · `services/donation_service.py` · **ตรวจสลิป** (`services/slip_verify.py`): อ่าน QR ในสลิปด้วย zxing-cpp → เลขอ้างอิงกันแจ้งซ้ำ · ต่อ EasySlip (API key ในหน้าแอดมิน เก็บเข้ารหัส) ยืนยันยอด/ผู้รับ/วันที่กับธนาคาร แล้วอนุมัติอัตโนมัติได้ |
| ผู้ดูแลระบบ | จัดการผู้ใช้/แพ็กเกจ, ตั้งค่าข้อจำกัดของแพ็กเกจ, ติดตามโควต้าบริการภายนอก (อีเมล, AI, LINE) พร้อมแจ้งเตือน |

### 🇹🇭 ภาษาไทย
จัดรูปข้อความไทยที่ดึงจาก PDF (อักษร PUA ของฟอนต์รุ่นเก่า, สระอำแตก/ฟอนต์ที่เก็บสระอาเป็นสระอำ, วงกลมสระอำที่วาดเป็นเส้น,
ลำดับสระ-วรรณยุกต์, ช่องว่างเทียมหลังอักษรกว้าง 0) ใช้ร่วมกันทั้งการค้นหา เซ็นเซอร์ คัดลอก PDPA และแปลงเป็น Word ·
ตัดบรรทัดตามคำ (PyThaiNLP + คำเสริมใน `backend/app/assets/thai_custom_words.txt`) · OCR ที่ตัดบรรทัดเองไม่ให้วรรณยุกต์หาย

---

## การติดตั้งและรันในเครื่อง (Development)

ต้องมี **Docker** + **Docker Compose** v2+

```bash
git clone https://github.com/jaturon2526/pdf_editor_fullstack.git
cd pdf_editor_fullstack
cp backend/.env.template backend/.env      # อย่างน้อยตั้ง JWT_SECRET และ FRONTEND_URL
cp frontend/.env.template frontend/.env    # ไม่บังคับ — ปุ่ม Google อ่านค่าจาก backend
docker compose -f docker-compose.dev.yml up -d --build
```

เปิด **http://localhost:8080** · สร้างผู้ใช้ทดสอบที่ยืนยันอีเมลแล้ว: `docker compose -f docker-compose.dev.yml exec backend python -m scripts.create_test_user <อีเมล> <รหัสผ่าน>`

| ไฟล์ compose | ใช้เมื่อ |
|---|---|
| `docker-compose.dev.yml` | พัฒนาประจำวันและ CI (PostgreSQL + backend + frontend) |
| `docker-compose.yml` | ระบบเต็มชุดในเครื่องแบบเดียวกับเซิร์ฟเวอร์ (มี Redis) — `docker compose up -d --build` หรือ `./start_app.sh` |
| `docker-compose.prod.yml` | เซิร์ฟเวอร์จริงเท่านั้น (image จาก Docker Hub + `.env.prod`) |
| `docker-compose.sonar.yml` | วิเคราะห์โค้ดด้วย SonarQube |

> โค้ดไม่ได้ mount เข้า container — แก้โค้ดแล้วต้อง `up -d --build <service>` ใหม่ (restart อย่างเดียวไม่ได้โค้ดใหม่)
> รัน backend/frontend นอก Docker ได้ ดู [`backend/README.md`](backend/README.md) และ [`frontend/README.md`](frontend/README.md)

---

## ทดสอบและวัดคุณภาพ

| คำสั่ง | ทดสอบอะไร |
|---|---|
| `cd backend && pytest -q` | unit/API test ของ backend (SQLite + โฟลเดอร์ชั่วคราว ไม่ต้องมี Postgres/Redis) |
| `cd frontend && npm run lint && npm test` | ESLint + Vitest |
| `cd frontend && npm run test:e2e` | Playwright บนระบบที่รันด้วย Docker (CI รันทุก PR) |
| `python -m scripts.thai_eval ../test_pdf_files [--check]` | อ่านข้อความไทยจาก PDF จริง: issues, coverage, ค้นหา/เซ็นเซอร์เจอครบไหม (ด่านก่อน push image ใน `scripts/ship.sh`) |
| `python -m scripts.ocr_eval [--real โฟลเดอร์] [--mode layer\|upload\|text]` | ความแม่น OCR ภาษาไทย (CER) กับภาพสังเคราะห์/ภาพสแกนจริง — `upload` = เส้นทางอัปโหลดรูป/สแกนเอกสาร |
| `python -m scripts.docx_eval ../test_pdf_files` | PDF→Word: รูปแบบตัวอักษรคงอยู่ไหม และคุณภาพข้อความไทย |
| `python -m scripts.scan_eval [--corpus ../test_pdf_files] [--check]` | ไฟล์สแกน→Word: CER/คำถูก/ตารางครบ จากเอกสารสังเคราะห์ (+ หน้า PDF จริงที่ทำให้เป็นภาพสแกน) — `ship.sh deploy` รัน `--check` ก่อน push image |
| `python -m scripts.pii_eval [--pdf โฟลเดอร์]` | การตรวจข้อมูลส่วนบุคคลกับชุดข้อความทดสอบ |
| `scripts/loadtest/run.sh` (หรือดับเบิลคลิก `scripts/loadtest/loadtest-now.command` บน Mac) | **Load test เซิร์ฟเวอร์จริง** ด้วย Locust: สร้างบัญชีทดสอบ `@loadtest.invalid` บนเซิร์ฟเวอร์ (ไม่ส่งอีเมล) → ไล่ 10/25/50/100 ผู้ใช้ (ดู 60% · แก้ไข 35% · บีบอัด 5%) → เก็บ CPU/RAM ของ container ทุก 5 วินาที → ลบบัญชีทดสอบพร้อมไฟล์ · ใช้ค่าเซิร์ฟเวอร์จาก `scripts/deploy.env` · ปรับด้วย `STAGES="10 25" STAGE_SECONDS=120` · ผลอยู่ที่ `loadtest-results/<เวลา>/summary.md` · แผน: `claude/phase-scalability-plan.md` |

สคริปต์ `scripts.*` รันจาก `backend/` · `test_pdf_files/` เป็นไฟล์จริงที่อาจมีข้อมูลส่วนบุคคล — อยู่ใน `.gitignore` ห้าม commit

---

## Deploy ขึ้นเซิร์ฟเวอร์

เซิร์ฟเวอร์จริง (Oracle Cloud, ARM64) รัน image สำเร็จรูปจาก Docker Hub ด้วย `docker-compose.prod.yml` + `.env.prod`
โดย build image บน Mac แล้ว push ขึ้น Docker Hub — งานประจำใช้สคริปต์เดียวบน Mac:

```bash
scripts/ship.sh all       # git bundle → push + PR (gh) → รอ CI → merge → build arm64 → ชุดวัดผล → push → เซิร์ฟเวอร์ pull + up -d → ตรวจ /api/health
scripts/ship.sh deploy    # deploy อย่างเดียว (เฉพาะส่วนที่เปลี่ยนตั้งแต่ครั้งก่อน)
scripts/ship.sh status    # เซิร์ฟเวอร์รัน commit ไหนอยู่
scripts/ship.sh cleanup   # ลบ branch ที่ merge แล้ว (GitHub + ในเครื่อง) และ .bundle ที่ใช้แล้ว
```

ติดตั้งเซิร์ฟเวอร์ใหม่ เตรียม Mac ครั้งแรก ทำเองทีละขั้น rollback และสำรองข้อมูลนอกเครื่อง: ดู [`DEPLOYMENT_ORACLE_GUIDE.md`](DEPLOYMENT_ORACLE_GUIDE.md)

---

## ติดตั้งในองค์กร (On-premise)

ติดตั้งบนเซิร์ฟเวอร์ขององค์กรเอง โดยใช้ซอร์สโค้ดชุดเดียวกับเว็บสาธารณะ ต่างกันที่ไฟล์ค่าตั้งค่า (`DEPLOYMENT_PROFILE=onprem`)

| | เว็บสาธารณะ (`public`) | ติดตั้งในองค์กร (`onprem`) |
|---|---|---|
| เข้าสู่ระบบ | อีเมล/รหัสผ่าน, Passkey, Google, LINE | อีเมล/รหัสผ่าน, Passkey (Google/LINE ปิด — เปิดเองได้ด้วย `AUTH_GOOGLE_ENABLED` / `AUTH_LINE_ENABLED`) |
| ใครสมัครได้ | ทุกคน | เฉพาะอีเมลโดเมนองค์กร (`ALLOWED_EMAIL_DOMAINS`) + ผู้ได้รับเชิญลงนาม |
| ส่งอีเมล | SMTP ภายนอก (เช่น Brevo/Gmail) | mail server ขององค์กร (relay ภายใน หรือบัญชีบริการ) |
| ใบรับรองลงนาม | ใบรับรองระบบ | ใบรับรองขององค์กร (`SIGNING_SEAL_P12`) |
| image | Docker Hub แท็ก `latest` (ARM64) | Docker Hub แท็ก `onprem` / `onprem-v<เวอร์ชัน>-<commit>` (x86_64 — build ด้วย `scripts/onprem/build-push.sh`) หรือ build บนเซิร์ฟเวอร์เอง |
| เข้าจากที่ไหนได้ | internet | กำหนดโดยเครือข่ายขององค์กร — ใช้เฉพาะภายใน หรือเปิดให้เข้าจาก internet ก็ได้ |

### สิ่งที่ต้องเตรียม

- เซิร์ฟเวอร์ Linux (x86_64 หรือ ARM64) ตามสเปกใน [สเปกเครื่อง](#สเปกเครื่องขั้นต่ำและที่แนะนำ) (ขั้นต่ำ 2 vCPU · RAM 4 GB · SSD 40 GB สำหรับทดลอง), ติดตั้ง **Docker Engine + Docker Compose v2** หรือ **Podman + compose** (git จำเป็นเฉพาะวิธี ข)
  - Podman บน Ubuntu: `sudo apt install podman docker-compose-v2` แล้ว `systemctl --user enable --now podman.socket` (`podman compose` ใช้ docker-compose — รองรับครบกว่า podman-compose) · `deploy.sh` เลือก docker/podman ให้เอง
  - Podman แบบไม่ใช้ root เปิดพอร์ต 80/443 ไม่ได้ → `echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee /etc/sysctl.d/90-unprivileged-ports.conf && sudo sysctl --system` หรือใช้พอร์ตอื่น `FRONTEND_BIND=8080` · ให้ทำงานต่อหลังรีบูต: `sudo loginctl enable-linger $USER` และ `systemctl --user enable podman-restart.service`
- เซิร์ฟเวอร์ออก internet ได้ (ดึง base image / แพ็กเกจตอน build, ฟอนต์ Google Fonts, TSA, ผู้ให้บริการ AI ถ้าใช้)
- **ชื่อโดเมน** ของเว็บ เช่น `pdf.company.co.th` และ **ใบรับรอง TLS** ของโดเมนนั้น — passkey ใช้ได้เฉพาะเว็บ https
  - ใช้เฉพาะในเครือข่ายองค์กร: ใบจาก CA ภายในได้ (เครื่องพนักงานต้องเชื่อถือ CA นั้น)
  - เปิดให้เข้าจาก internet (มือถือส่วนตัว, คู่ค้า): ต้องเป็นใบจาก **CA สาธารณะ** (Let's Encrypt, DigiCert, Sectigo ฯลฯ) และเปิดพอร์ต 443 จากภายนอก — ใบจาก CA ภายในจะขึ้นเตือน "ไม่ปลอดภัย" และ passkey ใช้ไม่ได้
- **mail server** ขององค์กร: relay ที่อนุญาตตาม IP (พอร์ต 25) หรือบัญชีบริการสำหรับ SMTP (587/465) และอีเมลผู้ส่ง เช่น `pdf-noreply@company.co.th`
- (ไม่บังคับ) ใบรับรองสำหรับลงนามเอกสารขององค์กร ไฟล์ `.p12`/`.pfx` ที่มี private key — คนละใบกับใบ TLS ของเว็บ

### สเปกเครื่องขั้นต่ำและที่แนะนำ

วัดจาก load test จริงบน Oracle A1 (ARM64 4 OCPU / 24 GB, v1.27.2: 3 worker + แคชภาพหน้า JPEG + คิวงานหนัก) — ผู้ใช้จำลอง ดูเอกสาร 60% · แก้ไข 35% · บีบอัดไฟล์ 5% · ไฟล์ตัวอย่าง 8 หน้า 1 MB:

| ผู้ใช้ออนไลน์พร้อมกัน | คำขอ/วินาที | แสดงหน้า p50 / p95 | แก้ไข p95 | ล้มเหลว | CPU backend สูงสุด | RAM ทั้งเครื่อง |
|---|---|---|---|---|---|---|
| 10 | 4.1 | 0.29 / 0.38 s | 0.07 s | 0% | 0.5 core | 1.9 GB |
| 25 | 10.5 | 0.29 / 0.41 s | 0.11 s | 0% | 0.9 core | 2.9 GB |
| 50 | 20.6 | 0.29 / 0.42 s | 0.12 s | 0% | 2.4 core | 4.6 GB |
| 100 | 39.6 | 0.31 / 1.1 s | 0.27 s | 0% | 3.7 core (เกือบเต็ม) | 8.2 GB |

**คอขวดคือ CPU** (RAM เหลือมาก) — คิดคร่าว ๆ **1 vCPU ต่อผู้ใช้ออนไลน์พร้อมกัน ~25 คน** · ผู้ใช้ทั้งหมดในระบบมักออนไลน์พร้อมกันราว 5–10%

| ขนาดองค์กร (ผู้ใช้ทั้งหมด) | ออนไลน์พีค | CPU | RAM | ดิสก์ (SSD) | `BACKEND_WORKERS` / `HEAVY_JOBS_PER_WORKER` |
|---|---|---|---|---|---|
| ทดลอง / ≤ 50 | ≤ 10 | 2 vCPU | 4 GB | 40 GB | 1 / 1 |
| ≤ 300 | ≤ 30 | 4 vCPU | 8–16 GB | 250 GB | 3 / 1 |
| ~1,000 | 50–100 | 4–8 vCPU (Oracle A1 4 OCPU ผ่านที่ 100 คน) | 16–32 GB | 500 GB | 3–6 / 1 |
| ~3,000 | 150–300 | 16 vCPU หรือแยกเครื่อง DB/ไฟล์ | 64 GB | 1 TB | 12 / 1–2 |

- **ดิสก์** = โควต้าต่อคน × ผู้ใช้ × ~0.4 (ใช้จริง 20–40%) + สำรองข้อมูล 7–14 วัน + Docker image ~10 GB · on-premise โควต้าเริ่มต้น 200 MB/คน (`DEFAULT_STORAGE_MB`) → 1,000 คนใช้ราว 80 GB + สำรอง → SSD 500 GB พอ · `deploy.sh setup` เตือนถ้าพื้นที่ว่างน้อยกว่าที่ควร
- **ใช้ SSD** (ไฟล์ทำงาน/ประวัติ undo อ่านเขียนบ่อย) · แยกข้อมูลไว้บนดิสก์ข้อมูลต่างหากจากดิสก์ระบบได้ยิ่งดี
- **RAM ต่อ worker** ~1.5–3 GB ตอนมีเอกสารเปิดมาก · Redis `REDIS_MAXMEMORY` 1.5 GB (ดีฟอลต์) · ปรับ `BACKEND_WORKERS` ≈ จำนวน core − 1
- Load test เองได้ด้วย `scripts/loadtest/run.sh` (ดู [ทดสอบและวัดคุณภาพ](#ทดสอบและวัดคุณภาพ)) — เครื่องยิงเครื่องเดียวทดสอบได้ราว 120 ผู้ใช้จำลอง (nginx จำกัด 50 คำขอ/วินาทีต่อ IP)

### เลือกวิธีติดตั้ง

| | **ก) build แล้ว push ขึ้น Docker Hub** (แนะนำ) | **ข) build บนเซิร์ฟเวอร์เอง** |
|---|---|---|
| ซอร์สโค้ด | เฉพาะเครื่อง build (Ubuntu) | บนเซิร์ฟเวอร์ |
| เซิร์ฟเวอร์ต้องมี | Docker + ชุดไฟล์ `onprem-deploy-kit.tar.gz` | Docker + git clone ทั้ง repo |
| อัปเดต / rollback | `./deploy.sh deploy <แท็ก>` / `./deploy.sh rollback` | `git pull` + build ใหม่ (นาน) |
| เหมาะกับ | หลายเซิร์ฟเวอร์ / เซิร์ฟเวอร์ที่ไม่อยากวางซอร์ส | เครื่องเดียว ทดลองติดตั้ง |

### วิธี ก) build บนเครื่อง build แล้ว deploy ด้วยสคริปต์

แท็กแยกจากเว็บสาธารณะเสมอ — `onprem-v1.26.18-ab12cd3` (ตรึงเวอร์ชัน) และ `onprem` (ล่าสุด) · สคริปต์ปฏิเสธแท็ก `latest` และแท็กเลข commit ที่ `scripts/ship.sh` ใช้กับเว็บสาธารณะ

**เครื่อง build (Ubuntu ที่มีซอร์สโค้ด)** — ติดตั้ง Docker Engine + git แล้ว `docker login` ครั้งแรก:

```bash
cd pdf_editor_fullstack
git pull
scripts/onprem/build-push.sh            # build backend+frontend (linux/amd64) → ทดสอบ image + ชุดวัดผล → push → dist/onprem-deploy-kit.tar.gz
scripts/onprem/build-push.sh backend    # เฉพาะส่วนเดียว
PLATFORM=linux/arm64 scripts/onprem/build-push.sh                # เซิร์ฟเวอร์ ARM64 (ต้องมี buildx + QEMU)
NO_PUSH=1 scripts/onprem/build-push.sh                           # build + ทดสอบ ไม่ push
scripts/onprem/build-push.sh help                                # ตัวเลือกทั้งหมด
```

ใช้ repository ของ Docker Hub อื่น (เช่นของหน่วยงาน): ใส่ `BACKEND_IMAGE=` / `FRONTEND_IMAGE=` ใน `scripts/onprem/build.env` (ไม่เข้า git)

**เครื่อง build เป็น Windows (Podman)** — ติดตั้ง [Podman Desktop / Podman for Windows](https://podman.io) + Git for Windows แล้วครั้งแรก `podman machine init` · `podman machine start` · `podman login docker.io`:

```powershell
cd pdf_editor_fullstack
git pull
powershell -ExecutionPolicy Bypass -File scripts\onprem\build-push.ps1              # เหมือน build-push.sh: build → ทดสอบ → push → dist\onprem-deploy-kit.tar.gz
.\scripts\onprem\build-push.ps1 -Target backend -NoPush                             # ตัวเลือก: -Target -Platform -Tag -NoPush -SkipEval -NoCache -GitPull -AllowDirty -Yes -DryRun
Get-Help .\scripts\onprem\build-push.ps1 -Detailed
```

build ด้วย `--format docker` (คง HEALTHCHECK ที่ `deploy.sh` ใช้รอ backend พร้อม) · ชุดไฟล์ deploy เขียนเป็น LF เสมอแม้ clone บน Windows · `.gitattributes` บังคับไฟล์ที่รันบน Linux เป็น LF

**เซิร์ฟเวอร์ในองค์กร (Ubuntu ไม่ต้องมีซอร์สโค้ด)** — ติดตั้ง Docker Engine + compose plugin:

```bash
scp dist/onprem-deploy-kit.tar.gz user@server:~/          # จากเครื่อง build
# บนเซิร์ฟเวอร์
tar xzf onprem-deploy-kit.tar.gz && cd pdf-editor
./deploy.sh setup          # ตรวจเครื่อง + สร้าง .env.prod (สุ่ม JWT_SECRET/DB_PASSWORD ให้) → แก้ค่า <...> แล้วรันซ้ำจนผ่าน
#   วางไฟล์ลับ: secrets/tls/fullchain.pem + privkey.pem (HTTPS ในตัว), secrets/seal.p12, secrets/org-ca.pem
docker login               # ถ้า repository บน Docker Hub เป็น private
./deploy.sh deploy         # ดึง image ตามแท็กใน .env.prod → เปิดระบบ → รอ backend พร้อม → ตรวจ /api/health
```

| คำสั่ง | ทำอะไร |
|---|---|
| `./deploy.sh deploy onprem-v1.26.18-ab12cd3` | อัปเดตเป็นแท็กนั้น (บันทึกแท็กใน `.env.prod` + ประวัติใน `.deploy-history`) |
| `./deploy.sh rollback [แท็ก]` | กลับไปแท็กก่อนหน้า (ฐานข้อมูลไม่ย้อน — สำรองก่อนอัปเดตเวอร์ชันใหญ่) |
| `./deploy.sh status` | แท็ก/เวอร์ชัน/commit ที่รันอยู่ + สถานะ container + รูปแบบการติดตั้ง |
| `./deploy.sh backup` | ฐานข้อมูล + ไฟล์ผู้ใช้ + `.env.prod` + `secrets` → `./backups/<วันเวลา>` (เก็บ 7 ชุดล่าสุด) |
| `./deploy.sh backup-schedule [HH:MM\|off]` | ตั้งสำรองอัตโนมัติทุกวันด้วย cron (ค่าเริ่มต้น 02:30 เวลาเครื่อง) · `off` ยกเลิก · log ที่ `backups/backup.log` |
| `./deploy.sh logs [backend]` · `make-admin <email>` · `stop` · `start` | log · ตั้งผู้ดูแล · ปิด/เปิดระบบ |

HTTPS ในตัวเปิดเองเมื่อมี `secrets/tls/fullchain.pem` — องค์กรมี reverse proxy อยู่แล้วให้ตั้ง `ONPREM_TLS=false` ใน `.env.prod`

### วิธี ข) build บนเซิร์ฟเวอร์เอง

```bash
# 1) ดึงซอร์สโค้ด (repository สาธารณะ AGPL-3.0 — หรือคัดลอกโฟลเดอร์โปรเจกต์มาวาง)
git clone https://github.com/jaturon2526/ja-pdf-editor.git
cd ja-pdf-editor

# 2) ค่าตั้งค่า — แก้ทุกค่าที่มี <...> (คำอธิบายอยู่ในไฟล์)
cp .env.onprem.template .env.prod
nano .env.prod
#   DEPLOYMENT_PROFILE=onprem, APP_NAME, ALLOWED_EMAIL_DOMAINS, INITIAL_ADMIN_EMAILS,
#   DB_PASSWORD, JWT_SECRET (python3 -c 'import secrets; print(secrets.token_urlsafe(48))'),
#   FRONTEND_URL=https://<โดเมน>, SMTP_FROM / SMTP_SERVER + แบบการเชื่อมต่อ (ก/ข/ค)

# 3) ไฟล์ลับ (ไม่เข้า git) — โฟลเดอร์ ./secrets ถูก mount เข้า backend ที่ /run/secrets/pdf-editor
mkdir -p secrets/tls && chmod 700 secrets
cp <ใบรับรองเว็บ+intermediate>.pem secrets/tls/fullchain.pem
cp <private key>.pem               secrets/tls/privkey.pem && chmod 600 secrets/tls/privkey.pem
cp <ใบรับรองลงนามขององค์กร>.p12      secrets/seal.p12        # ถ้ามี → ตั้ง SIGNING_SEAL_P12 ใน .env.prod
cp <CA ขององค์กร>.pem               secrets/org-ca.pem      # ถ้า mail server ใช้ใบของ CA ภายใน → ตั้ง SMTP_CA_FILE

# 4) build และเปิดระบบ (ครั้งแรก build backend ใช้เวลานาน — คอมไพล์ Ghostscript)
docker compose --env-file .env.prod \
  -f docker-compose.prod.yml -f docker-compose.onprem-build.yml -f docker-compose.onprem-tls.yml \
  up -d --build
```

- ฐานข้อมูลถูกสร้างเองตอน backend start ครั้งแรก (Alembic) ไม่ต้องรันสคริปต์เพิ่ม
- ใช้ `-f docker-compose.onprem-tls.yml` เอง: ใส่ `FRONTEND_BIND=127.0.0.1:8081` ใน `.env.prod` ด้วย (ย้ายหน้าเว็บออกจากพอร์ต 80 ให้ nginx tls — `deploy.sh` ตั้งให้เอง)
- องค์กรมี reverse proxy / load balancer ที่ทำ HTTPS อยู่แล้ว: ไม่ต้องใช้ `-f docker-compose.onprem-tls.yml` และไม่ต้องวาง `secrets/tls` — ให้ proxy ส่งต่อมาที่ `http://<เซิร์ฟเวอร์>:80` (ตั้ง `client_max_body_size` ≥ 60M และ timeout ≥ 120 วินาที)
- `docker-compose.onprem-build.yml` จำเป็นเพราะ image บน Docker Hub เป็น ARM64 เท่านั้น — build บนเครื่องจะได้ image ตามสถาปัตยกรรมของเซิร์ฟเวอร์

### ตรวจหลังติดตั้ง

วิธี ก: `./deploy.sh status` แสดงข้อมูลเดียวกันนี้ · วิธี ข:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml -f docker-compose.onprem-build.yml -f docker-compose.onprem-tls.yml ps
docker logs pdf_backend_prod 2>&1 | grep -E "รูปแบบการติดตั้ง|ใบรับรองระบบ"
#   → รูปแบบการติดตั้ง: onprem · Google: ปิด · LINE: ปิด · สมัครเอง: ได้ · โดเมน: company.co.th · SMTP: mail.company.co.th:25 (none, no-auth)
curl -fsS https://<โดเมน>/api/health          # {"status":"ok"}
curl -fsS https://<โดเมน>/api/config/public   # google_client_id: null, line_login: false
```

1. เปิด `https://<โดเมน>` → **สมัครสมาชิกใหม่** ด้วยอีเมลใน `INITIAL_ADMIN_EMAILS` → ยืนยันอีเมลจากลิงก์ที่ได้รับ (ไม่ได้รับ = ตรวจค่า SMTP ใน log: `docker logs pdf_backend_prod 2>&1 | grep -i อีเมล`)
2. เข้าสู่ระบบ → เมนูผู้ดูแลระบบต้องปรากฏ · เพิ่ม Passkey ที่หน้า **ความปลอดภัย**
3. ลองสมัครด้วยอีเมลนอกโดเมน → ต้องขึ้น "สมัครได้เฉพาะอีเมลขององค์กร"
4. ส่งเอกสารให้ลงนามและเซ็นดิจิทัล → เปิดใน Adobe Reader ดูผู้ออกใบรับรองเป็นขององค์กร

ตั้งผู้ดูแลเพิ่มภายหลัง: `docker exec pdf_backend_prod python -m scripts.make_admin <email>`

### อัปเดตเวอร์ชัน (วิธี ข)

วิธี ก ใช้ `./deploy.sh deploy <แท็กใหม่>` บนเซิร์ฟเวอร์

```bash
cd pdf_editor_fullstack
git pull
docker compose --env-file .env.prod \
  -f docker-compose.prod.yml -f docker-compose.onprem-build.yml -f docker-compose.onprem-tls.yml \
  up -d --build
docker image prune -f
```

schema ฐานข้อมูลอัปเกรดเองตอน backend start · แก้ `.env.prod` อย่างเดียว: รันคำสั่ง `up -d` เดิม (ไม่ต้อง `--build`) · ต่ออายุใบรับรอง TLS: วางไฟล์ใหม่ทับแล้ว `docker restart pdf_tls_prod`

### สำรองข้อมูล

วิธี ก: `./deploy.sh backup` · **อัตโนมัติทุกวัน: `./deploy.sh backup-schedule`** (ตั้ง cron 02:30 ให้เอง) · ต้องเก็บครบ 4 อย่าง: ฐานข้อมูล (volume `pgdata_prod`), ไฟล์ผู้ใช้ (volume `pdf_data_prod`), `.env.prod` และโฟลเดอร์ `secrets/` — `JWT_SECRET` ต้องใช้ค่าเดิมเมื่อกู้คืน

```bash
docker exec pdf_db_prod pg_dump -U pdf_user -Fc pdf_editor > backup-$(date +%F).dump
docker run --rm -v pdf_editor_fullstack_pdf_data_prod:/data -v "$PWD":/b alpine tar czf /b/files-$(date +%F).tgz -C /data .
```

(ชื่อ volume ขึ้นต้นด้วยชื่อโฟลเดอร์โปรเจกต์ — ตรวจด้วย `docker volume ls`) · วิธีกู้คืนและสำรองนอกเครื่อง: [`DEPLOYMENT_ORACLE_GUIDE.md`](DEPLOYMENT_ORACLE_GUIDE.md) หัวข้อ 10–11

หน้าแอดมิน › **โควต้าบริการภายนอกและสถานะเซิร์ฟเวอร์** แสดงเวลาสำรองล่าสุด (สคริปต์สำรองเขียนไว้ที่ `/data/.last-backup` และ `/data/.last-offsite-backup` ใน backend) และแจ้งแอดมินทาง LINE/อีเมลเมื่อขาดหายเกิน `BACKUP_MAX_AGE_HOURS` (36 ชม.) — พร้อม RAM/CPU ทั้งเครื่อง, หน่วยความจำ Redis, ดิสก์ และขนาดฐานข้อมูล (เตือนเมื่อเกิน `QUOTA_ALERT_PERCENT` 80%)

### ป้องกันการเดารหัสผ่านและการยิงคำขอถี่ ๆ

- **ต่อบัญชี** (backend `app/core/ratelimit.py` · ใช้ Redis ร่วมกันทุก worker): ใส่รหัสผิด 5 ครั้งใน 15 นาที → ล็อกการเข้าสู่ระบบของบัญชีนั้น 15 นาที (รหัสถูกก็เข้าไม่ได้จนครบเวลา · นับรวมการกรอกรหัสเดิมผิดตอนเปลี่ยนรหัส) · IP เดียวผิดรวมทุกบัญชี 30 ครั้ง/15 นาที · ลืมรหัสผ่าน/ส่งอีเมลยืนยันซ้ำ 3 ครั้ง/ชม. ต่ออีเมล (20 ต่อ IP) · สมัครใหม่ 10 บัญชี/ชม. ต่อ IP
- **ต่อ IP** (nginx ใน `frontend/nginx.conf`): หน้าเข้าสู่ระบบ/สมัคร/ลืมรหัส 20 ครั้ง/นาที (กระชากได้ 20) · API ทั้งหมด 50 คำขอ/วินาที (กระชากได้ 200) — เกินตอบ 429 ภาษาไทย
- IP จริงของผู้ใช้: nginx เชื่อ `X-Forwarded-For` จาก proxy ในเครือข่ายส่วนตัว (10/8, 172.16/12, 192.168/16) เท่านั้น — ถ้าองค์กรมี reverse proxy ด้วย IP สาธารณะอยู่หน้าระบบ ต้องเพิ่ม `set_real_ip_from` ของ proxy นั้น ไม่งั้นผู้ใช้ทุกคนจะนับเป็น IP เดียว

### เปิด LINE ขององค์กร (ไม่บังคับ)

ค่าเริ่มต้นของ onprem ปิด LINE ไว้ องค์กรเปิดใช้ด้วย LINE Official Account / channel ของตัวเองได้ และ**ไม่ขัดกับอีเมลองค์กร**: บัญชีจับคู่ด้วยอีเมล (อีเมลตรงกัน = บัญชีเดิม) และ `ALLOWED_EMAIL_DOMAINS` / `ALLOW_SELF_REGISTRATION` ใช้กับบัญชีใหม่ที่มาจาก LINE ด้วย

| ใช้ทำอะไร | channel ใน LINE Developers | ค่าใน `.env.prod` | URL ที่ลงทะเบียน |
|---|---|---|---|
| เข้าสู่ระบบด้วย LINE | LINE Login (Web app) | `LINE_LOGIN_CHANNEL_ID`, `LINE_LOGIN_CHANNEL_SECRET` | Callback URL `https://<โดเมน>/auth/line/callback` |
| แจ้งเตือนการลงนามทาง LINE | Messaging API (ของ LINE Official Account) | `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_OA_BASIC_ID` | Webhook URL `https://<โดเมน>/api/line/webhook` |

1. สร้าง **LINE Official Account** ขององค์กร (manager.line.biz) → เปิด Messaging API เลือก provider ขององค์กร → ใน LINE Developers: Channel secret, Issue channel access token (long-lived), ตั้ง Webhook URL → Verify → เปิด Use webhook · ใน OA Manager ปิดข้อความตอบกลับอัตโนมัติ/ข้อความทักทาย
2. **provider เดียวกัน** → สร้าง channel แบบ **LINE Login** → ตั้ง Callback URL · Linked LINE Official Account = OA จากข้อ 1 · ขอสิทธิ์ Email address (OpenID Connect) · เปลี่ยนเป็น **Published**
3. ใส่ค่าใน `.env.prod` พร้อม `AUTH_LINE_ENABLED=true` (ตัวอย่างและคำอธิบายครบใน `.env.onprem.template` หัวข้อ LINE) → `./deploy.sh setup` ตรวจความยาวค่าและแสดง URL ที่ต้องลงทะเบียน → `./deploy.sh deploy`

ทำไมต้อง provider เดียวกัน: LINE ให้ userId ของคนเดียวกันตรงกันเฉพาะใน provider เดียวกัน — พนักงานเข้าสู่ระบบด้วย LINE ครั้งแรก หน้าอนุญาตชวนเพิ่มเพื่อน OA แล้วระบบ**ผูกรับแจ้งเตือนให้อัตโนมัติ** (คนละ provider = ต้องไปขอรหัสผูกเองที่หน้าความปลอดภัย)

ข้อกำหนด: `FRONTEND_URL` เป็น `https://<โดเมน>` (ใช้ IP ไม่ได้) · เซิร์ฟเวอร์ออกอินเทอร์เน็ตไป `api.line.me` ได้ · **แจ้งเตือน** ต้องให้ LINE เรียก Webhook จากอินเทอร์เน็ตได้ (เข้าสู่ระบบอย่างเดียวไม่ต้อง) · พนักงานที่อีเมลใน LINE เป็นอีเมลส่วนตัว: เข้าด้วยอีเมลองค์กรก่อน → หน้า **ความปลอดภัย** → ผูก LINE → ครั้งต่อไปเข้าด้วย LINE ได้ · แพ็กเกจฟรีของ OA ส่งได้ 300 ข้อความ/เดือน (`LINE_MONTHLY_LIMIT` — ครบแล้วส่งอีเมลแทน)

Google: เปิดเมื่ออีเมลองค์กรอยู่บน Google Workspace เท่านั้น (`AUTH_GOOGLE_ENABLED=true` + `GOOGLE_CLIENT_ID`) — ถ้าอีเมลอยู่บน mail server ขององค์กร พนักงานจะได้ Gmail ส่วนตัวซึ่งไม่ตรงกับบัญชีองค์กร

### ข้อจำกัดปัจจุบัน

- ยังไม่มีหน้าให้ผู้ดูแลสร้างบัญชีให้ผู้อื่น — พนักงานสมัครเอง (จำกัดด้วยโดเมน) · `ALLOW_SELF_REGISTRATION=false` จะเหลือแค่ผู้ดูแลและผู้ได้รับเชิญลงนาม
- ยังไม่รองรับ LDAP / Active Directory / SSO ขององค์กร
- ฟีเจอร์ AI (แปลง Word แบบ AI, OCR) ส่งเนื้อหาเอกสารไปผู้ให้บริการที่ตั้ง (`AI_PROVIDER`: Gemini / Claude / OpenAI) — ใช้โมเดลในองค์กร (`AI_PROVIDER=openai` + `AI_BASE_URL` ภายใน) ถ้านโยบายไม่อนุญาตให้ข้อมูลออกนอกองค์กร · Claude ต้องใช้ API key จาก Claude Console (แผนสมาชิก Claude ใช้แทนไม่ได้)

---

## โครงสร้างโปรเจกต์ (Project Structure)

```
pdf_editor_fullstack/
├── backend/
│   ├── app/
│   │   ├── api/            # routes: pdf/ (แยกตามหมวด), annotation, edit, convert, autogen, signing, auth, passkey, line, admin
│   │   ├── core/           # config, PDF session (memory/Redis), security, auth session
│   │   ├── db/             # database + Alembic migrations (รันเองตอน start)
│   │   ├── models/         # SQLAlchemy models + Pydantic schemas
│   │   ├── services/       # pdf_service/, edit_service/, thai_text, ocr_thai, convert_service, signing_*, ...
│   │   ├── assets/         # ฟอนต์ไทยที่ติดมากับระบบ, ฟอนต์ที่ติดตั้งเพิ่ม, คำเสริมสำหรับตัดคำไทย
│   │   └── main.py         # FastAPI entry point
│   ├── scripts/            # สคริปต์ดูแลระบบและชุดวัดผล (thai_eval, ocr_eval, docx_eval, pii_eval, ...)
│   ├── sample_autogen/     # ไฟล์ตัวอย่างเอกสารอัตโนมัติ (ดาวน์โหลดจากคู่มือ)
│   ├── tests/              # pytest
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/                # pages/, components/, hooks/, api/, utils/, __tests__/
│   ├── public/manual.html  # คู่มือผู้ใช้ (อัปเดตทุกครั้งที่เพิ่ม/เปลี่ยนฟีเจอร์)
│   ├── e2e/                # Playwright
│   ├── Dockerfile + nginx.conf
│   └── package.json
├── scripts/                # ship.sh (deploy จาก Mac), server/ (สคริปต์บนเซิร์ฟเวอร์ เช่น backup นอกเครื่อง)
├── docker-compose*.yml     # ดูตารางด้านบน
├── DEPLOYMENT_ORACLE_GUIDE.md
└── README.md
```

---

## Volumes & Data Persistence

| ไฟล์ compose | Volume | เส้นทางใน container | เก็บอะไร |
|---|---|---|---|
| `docker-compose.prod.yml` | `pgdata_prod` | `/var/lib/postgresql/data` | ฐานข้อมูล |
| | `pdf_data_prod` | `/data` | ไฟล์ที่อัปโหลด/บันทึก, ไฟล์ทำงาน, ฟอนต์ส่วนตัว, ไฟล์การลงนาม, ผลแปลง Word |
| | `pdf_redis_prod` | `/data` (redis) | Redis snapshot |
| `docker-compose.yml` | `pdf_db`, `pdf_uploads`, `pdf_working`, `pdf_redis` | ตามลำดับ: postgres, `/data/uploads`, `/data/working`, redis | ชุดเดียวกันสำหรับเครื่องพัฒนา |
| `docker-compose.dev.yml` | `pgdata`, `pdf_data` | postgres, `/data` | |

ใบรับรองระบบ (.p12) สำหรับลงนาม mount จาก `./secrets` (prod) หรือ `backend/secrets` (dev) — ไม่อยู่ใน git/image

---

## Environment Variables (ตัวแปรสำคัญ)

รายการครบพร้อมคำอธิบายอยู่ใน `backend/.env.template` (เครื่องพัฒนา), `.env.prod.template` (เซิร์ฟเวอร์สาธารณะ), `.env.onprem.template` (ติดตั้งในองค์กร) และ `frontend/.env.template`

| ตัวแปร | คำอธิบาย |
|--------|----------|
| `JWT_SECRET` | คีย์เซ็น JWT ยาว ≥ 32 ตัว — production ไม่ยอม start ถ้าไม่ตั้ง |
| `FRONTEND_URL` | URL ที่ผู้ใช้เปิดจริง ใช้สร้างลิงก์ในอีเมล และเป็นโดเมนของ Passkey |
| `DB_USER` / `DB_PASSWORD` / `DB_NAME` | ฐานข้อมูล (prod — compose ประกอบ `DATABASE_URL` ให้) |
| `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | ส่งอีเมล (สมัคร/ลืมรหัสผ่าน/แจ้งเตือนลงนาม) |
| `DEPLOYMENT_PROFILE` | `public` (ดีฟอลต์) หรือ `onprem` — onprem ปิด Google/LINE เป็นค่าเริ่มต้น (`AUTH_GOOGLE_ENABLED` / `AUTH_LINE_ENABLED` เปิดเองได้) · ดู [ติดตั้งในองค์กร](#ติดตั้งในองค์กร-on-premise) |
| `ALLOWED_EMAIL_DOMAINS`, `ALLOW_SELF_REGISTRATION` | จำกัดโดเมนอีเมลของบัญชีใหม่ / ปิดการสมัครเอง (ผู้ได้รับเชิญลงนามและ `INITIAL_ADMIN_EMAILS` สมัครได้เสมอ) |
| `SMTP_SECURITY`, `SMTP_AUTH`, `SMTP_CA_FILE` | mail server ขององค์กร: starttls/ssl/none, relay ที่ไม่ต้อง login, CA ภายใน |
| `SOURCE_CODE_URL` | ลิงก์ "ซอร์สโค้ด (AGPL-3.0)" ในหน้า Login และหน้าเกี่ยวกับ (ดีฟอลต์ repo สาธารณะของโปรเจกต์) — **ถ้าแก้โค้ดแล้วเปิดให้คนอื่นใช้ผ่านเครือข่าย ต้องชี้ไปที่ซอร์สฉบับที่แก้** |
| `GOOGLE_CLIENT_ID` | ปุ่มเข้าสู่ระบบด้วย Google (หน้าเว็บอ่านจาก `/api/config/public` — ไม่ต้อง build frontend ใหม่) |
| `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL` | AI ของระบบ: `gemini` (ดีฟอลต์ — ใช้ `GEMINI_API_KEY` เดิมได้), `anthropic` (Claude), `openai` (OpenAI / Azure OpenAI / vLLM / Ollama) — ดู `backend/app/services/ai_client.py` |
| `AI_SYSTEM_DAILY_LIMIT`, `AI_USER_KEYS_ENABLED`, `AI_PRIVATE_HOSTS` | โควต้าฟรีรายวันต่อผู้ใช้ · ให้ผู้ใช้ใส่ API key ส่วนตัว (เลือกค่ายเอง) · โฮสต์ภายในที่ผู้ใช้ตั้งเป็น URL ของ API ได้ |
| _(ไม่ตั้ง AI เลย)_ | ไม่มี `AI_API_KEY`/`GEMINI_API_KEY` และผู้ใช้ไม่มี key ส่วนตัว → ไม่แสดงกล่องโควต้า AI, ซ่อนตัวเลือก AI, แปลง Word ใช้ตัวจัดรูปในเครื่อง · ตั้ง `AI_USER_KEYS_ENABLED=false` ด้วยเพื่อซ่อนเมนูตั้งค่า AI ทั้งหมด |
| `LINE_CHANNEL_*`, `LINE_LOGIN_CHANNEL_*` | แจ้งเตือนทาง LINE / เข้าสู่ระบบด้วย LINE |
| `SIGNING_SEAL_P12`, `SIGNING_SEAL_P12_PASSWORD`, `SIGNING_TSA_URL` | ใบรับรองระบบสำหรับลงนาม (ไม่ตั้ง = self-signed) และ timestamp |
| `PDF_MAX_UPLOAD_SIZE`, `PDF_SESSION_TTL_MINUTES`, `REDIS_MAXMEMORY` | ขนาดไฟล์สูงสุด (ดีฟอลต์ 50MB), ปิดเอกสารที่ไม่ได้ใช้หลังกี่นาที (ดีฟอลต์ 120 — ออกจากหน้าแก้ไข/ปิดแท็บก็ปิดทันที เปิดลิงก์เดิมได้ ระบบเปิดใหม่จากไฟล์ที่บันทึก), หน่วยความจำ Redis (prod ดีฟอลต์ 1536mb) |
| `BACKEND_WORKERS`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | จำนวน process ของ backend (prod ดีฟอลต์ 3 — ใช้ CPU หลาย core, ต้องมี Redis) · pool ฐานข้อมูลต่อ process · ผล load test: `claude/phase-scalability-plan.md` |
| `HEAVY_JOBS_PER_WORKER`, `HEAVY_QUEUE_MAX`, `HEAVY_QUEUE_TIMEOUT` | คิวงานหนัก (Ghostscript / LibreOffice / Tesseract — `app/core/heavy.py`): ทำพร้อมกันได้ workers × `HEAVY_JOBS_PER_WORKER` (ดีฟอลต์ 1) ที่เหลือรอคิว · คิวต่อ process เกิน `HEAVY_QUEUE_MAX` (8) หรือรอเกิน `HEAVY_QUEUE_TIMEOUT` (120 วินาที) ตอบ 503 + `Retry-After` |

> ภาพหน้าเอกสาร (`GET /api/pdf/{sid}/page/{n}`) ส่งเป็น JPEG q85 ดีฟอลต์ (`?fmt=png` ได้ PNG แบบเดิม · response มี `image_mime`) และเก็บแคชตามเวอร์ชันเอกสาร — ใน Redis (`render:{sid}:{ver}:…` อายุ 10 นาที ใช้ร่วมกันทุก worker) หรือในหน่วยความจำ 96MB ถ้าไม่มี Redis · แก้ไข/เลิกทำแล้วเวอร์ชันเปลี่ยน แคชเก่าไม่ถูกใช้

---

## เทคโนโลยีที่ใช้ (Tech Stack)

| Layer | เทคโนโลยี |
|-------|-----------|
| **Frontend** | React 18, Vite, Tailwind CSS, React Router, @simplewebauthn/browser |
| **Backend** | FastAPI, Uvicorn, Python 3.11, SQLAlchemy + Alembic |
| **PDF** | PyMuPDF, fpdf2 + uharfbuzz (จัดรูปอักษรไทย), pikepdf, Ghostscript (คอมไพล์รุ่นล่าสุดใน Dockerfile — `GS_VERSION`/`GS_SHA256`), pyHanko (PAdES) |
| **แปลงไฟล์** | LibreOffice headless, pdf2docx, python-docx, docxtpl/docxcompose, openpyxl |
| **ภาษาไทย / OCR** | PyThaiNLP, Tesseract (tha+eng) + pytesseract, Pillow (RAQM), OpenCV (ผ่าน pdf2docx) |
| **สแกนเอกสาร (เบราว์เซอร์)** | getUserMedia / ImageCapture, OpenCV.js 4.10 (`@techstark/opencv-js`, โหลดเฉพาะหน้าสแกน), IndexedDB |
| **AI** | Gemini (google-genai), Anthropic Claude และ OpenAI-compatible (HTTP) — ไม่บังคับ (`app/services/ai_client.py`) |
| **Database / Cache** | PostgreSQL 15, Redis 7 |
| **Auth** | JWT (python-jose), bcrypt, Google OAuth, LINE Login, WebAuthn (Passkey) |
| **ทดสอบ** | pytest, Vitest, Playwright, GitHub Actions |
| **Deploy** | Docker, Docker Compose, Nginx, Oracle Cloud (ARM64), Docker Hub |

---

## License

JA PDF Editor เผยแพร่ภายใต้ **GNU Affero General Public License v3.0 or later** — ข้อความเต็มใน [LICENSE](LICENSE)
ส่วนประกอบของบุคคลที่สามและสัญญาอนุญาตของแต่ละตัว: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) (และเมนู **วิธีใช้ → เกี่ยวกับ JA PDF Editor** ในแอป)

ทำไมเป็น AGPL: แกน PDF คือ PyMuPDF และ Ghostscript ของ Artifex ซึ่งเป็น AGPL-3.0 (หรือซื้อ license เชิงพาณิชย์แยก)
โปรเจกต์นี้เลือกเปิดซอร์สทั้งหมดแทน — เว็บ ja-pdf.com ใช้ฟรีและรับการสนับสนุนแบบบริจาค

สรุปสั้น ๆ สำหรับผู้ที่นำไปใช้ (ไม่ใช่คำแนะนำทางกฎหมาย):

| กรณี | ต้องทำอะไร |
|---|---|
| ติดตั้งใช้ภายในองค์กรโดยไม่แก้โค้ด | ไม่ต้องทำอะไรเพิ่ม — ลิงก์ซอร์สในหน้าเว็บชี้ repo ต้นฉบับอยู่แล้ว |
| แก้โค้ดแล้วให้พนักงาน/ลูกค้าใช้ผ่านเครือข่าย | เปิดซอร์สฉบับที่แก้ (ทั้งโปรเจกต์ ภายใต้ AGPL-3.0) แล้วตั้ง `SOURCE_CODE_URL` ให้ชี้ไปที่นั่น |
| แจกจ่าย/ขาย image หรือซอฟต์แวร์ต่อ | ให้ซอร์สฉบับตรงกันไปพร้อมกัน + คงไฟล์ LICENSE และประกาศลิขสิทธิ์ |
| รับจ้างติดตั้ง ดูแล ปรับแต่ง (บริการ) | คิดค่าบริการได้ตามปกติ — AGPL ไม่ห้ามเก็บเงินค่าบริการ |
| ไม่ต้องการเปิดซอร์สส่วนที่แก้ | ต้องซื้อ commercial license ของ PyMuPDF/Ghostscript จาก Artifex และขออนุญาตจากผู้พัฒนาโปรเจกต์นี้ |

ไม่ต้องเปิดเผย: ไฟล์ `.env*` (รหัสผ่าน/คีย์), ฐานข้อมูล, ไฟล์ผู้ใช้, ใบรับรองของระบบ

### เผยแพร่ซอร์สฉบับใหม่ (ผู้ดูแลโปรเจกต์)

repo พัฒนาหลัก (private) มีประวัติเก่าที่ไม่ควรเผยแพร่ — repo สาธารณะจึงรับเฉพาะ snapshot ของแต่ละ release:

```bash
# ครั้งแรก: สร้าง repo ว่างบน GitHub ชื่อ ja-pdf-editor (Public, ไม่ต้องมี README) แล้ว
PUBLIC_REMOTE=https://github.com/jaturon2526/ja-pdf-editor.git scripts/export-public.sh
# ทุก release หลัง merge เข้า main
scripts/export-public.sh            # ตรวจ → commit "Release vX.Y.Z (source <sha>)" ใน ../ja-pdf-editor-public
scripts/export-public.sh --push     # หรือ push ให้ด้วย
```

สคริปต์หยุดทันทีถ้าพบไฟล์ `.env`/คีย์, คำต้องห้ามใน `.public-blocklist` (เบอร์โทร IP เซิร์ฟเวอร์ ชื่อไฟล์คีย์ บรรทัดละคำ — ไฟล์นี้อยู่ใน `.gitignore` ไม่เข้า git)
หรือ gitleaks พบความลับ · ไม่ส่งออก `archive/`, `CLAUDE.md`, `DEPLOYMENT_ORACLE_GUIDE.md`
