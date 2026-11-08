# Third-party software / ซอฟต์แวร์ของบุคคลที่สาม

JA PDF Editor เผยแพร่ภายใต้ **GNU Affero General Public License v3.0 or later** (ดู [LICENSE](LICENSE))
เหตุผลหลัก: แกนประมวลผล PDF คือ PyMuPDF (AGPL-3.0, Artifex) ซึ่งเชื่อมเข้ากับโค้ดของแอปโดยตรง

ตารางนี้คือส่วนประกอบหลักที่ใช้ ณ เวอร์ชันปัจจุบัน — ข้อความสัญญาอนุญาตฉบับเต็มของแต่ละแพ็กเกจ
อยู่ในแพ็กเกจนั้น (`site-packages/*/LICENSE*`, `node_modules/*/LICENSE*`, `/usr/share/doc/*/copyright` ใน image)
รายการทั้งหมดของแพ็กเกจที่ติดตั้งจริงดูได้ด้วย `pip-licenses` (backend) และ `npx license-checker` (frontend)

## Backend (Python — ติดตั้งจาก `backend/requirements.txt`)

| แพ็กเกจ | ใช้ทำอะไร | License |
|---|---|---|
| PyMuPDF (fitz / MuPDF) | อ่าน/เขียน/เรนเดอร์ PDF | AGPL-3.0 (หรือ commercial จาก Artifex) |
| FastAPI, Pydantic | API framework, validate ข้อมูล | MIT |
| Uvicorn | ASGI server | BSD-3-Clause |
| python-multipart | รับไฟล์อัปโหลด | Apache-2.0 |
| fpdf2 | วาดข้อความไทยแบบ vector, หนังสือรับรองการลงนาม | LGPL-3.0 |
| uharfbuzz (HarfBuzz) | จัดรูปอักษรไทย (text shaping) | Apache-2.0 (HarfBuzz: MIT "Old") |
| fontTools, Brotli | ตรวจ/แปลงฟอนต์ | MIT |
| pikepdf (qpdf) | ถอดรหัส PDF, โปรไฟล์ sRGB ICC สำหรับ PDF/A | MPL-2.0 (qpdf: Apache-2.0) |
| PyThaiNLP | ตัดคำไทย | Apache-2.0 |
| pyHanko, pyhanko-certvalidator, asn1crypto | ลายเซ็นดิจิทัล PAdES, ตรวจใบรับรอง | MIT |
| cryptography | เข้ารหัส, X.509/PKCS#12 | Apache-2.0 / BSD-3-Clause |
| certifi | Mozilla CA bundle | MPL-2.0 |
| aiohttp | ขอ timestamp จาก TSA | Apache-2.0 |
| webauthn (py_webauthn) | Passkey | BSD-3-Clause |
| segno | QR code (SVG) — LINE, พร้อมเพย์ | BSD-3-Clause |
| zxing-cpp | อ่าน QR ในสลิปโอนเงิน | Apache-2.0 |
| treepoem (+ BWIPP) | บาร์โค้ด/QR | MIT |
| docxtpl | Word template (Auto-Gen) | LGPL-2.1 |
| docxcompose, python-docx, openpyxl | รวม/สร้าง Word, อ่าน Excel | MIT |
| Jinja2 | template engine | BSD-3-Clause |
| pdf2docx | PDF → Word | GPL-3.0 (ใช้ร่วมกับ AGPL-3.0 ได้ตาม GPLv3 ข้อ 13) |
| Pillow | ประมวลผลภาพ | MIT-CMU (HPND) |
| pytesseract | เรียก Tesseract | Apache-2.0 |
| SQLAlchemy, Alembic | ORM, migrations | MIT |
| psycopg 3 | PostgreSQL driver | LGPL-3.0 |
| redis-py | Redis client | MIT |
| passlib, bcrypt | hash รหัสผ่าน | BSD / Apache-2.0 |
| python-jose | JWT | MIT |
| email-validator | ตรวจอีเมล | Unlicense |
| google-genai, google-auth | Gemini SDK, Google Sign-In | Apache-2.0 |
| tzdata | ฐานข้อมูลเขตเวลา | Apache-2.0 |

## Frontend (JavaScript — `frontend/package.json`)

| แพ็กเกจ | ใช้ทำอะไร | License |
|---|---|---|
| React, React DOM, React Router | UI | MIT |
| @react-oauth/google | ปุ่ม Google Sign-In | MIT |
| @simplewebauthn/browser | Passkey | MIT |
| @techstark/opencv-js (OpenCV) | หาขอบเอกสารในเครื่องสแกน | Apache-2.0 |
| Tailwind CSS, Vite, ESLint, Vitest | build/dev tools (ไม่อยู่ใน bundle ที่ส่งให้ผู้ใช้ ยกเว้น CSS ที่สร้าง) | MIT |
| Playwright | ทดสอบ E2E (dev only) | Apache-2.0 |

## โปรแกรมที่รันแยก (ใน Docker image / container)

| โปรแกรม | ใช้ทำอะไร | License | หมายเหตุ |
|---|---|---|---|
| Ghostscript 10.x | ลดขนาด, PDF/A, เวอร์ชัน PDF, บาร์โค้ด | AGPL-3.0 (Artifex) | เรียกเป็น subprocess · คอมไพล์จากซอร์สทางการใน `backend/Dockerfile` |
| LibreOffice (headless) | แปลงไฟล์ Office → PDF | MPL-2.0 | Debian package |
| Tesseract OCR + ภาษา tha | OCR | Apache-2.0 | Debian package |
| OpenJDK (default-jre-headless) | ส่วนเสริมของ LibreOffice | GPL-2.0 + Classpath Exception | Debian package |
| PostgreSQL 15 | ฐานข้อมูล | PostgreSQL License | image ทางการ |
| Redis 7 | session/cache/rate limit | BSD-3-Clause (≤7.2) / RSALv2 หรือ SSPLv1 (7.4+) | ใช้ภายในระบบเท่านั้น ไม่ได้ให้บริการ Redis แก่บุคคลภายนอก · ใช้ Valkey (BSD-3-Clause) แทนได้ |
| nginx (nginx-unprivileged) | web server / reverse proxy | BSD-2-Clause | image ทางการ |
| Python 3.11, Node.js 22 | runtime / build | PSF-2.0 / MIT | image ทางการ |

## ฟอนต์

| ฟอนต์ | ที่อยู่ | License |
|---|---|---|
| Sarabun, Kanit (มากับ repo: `backend/app/assets/fonts/`) | ฟอนต์หลักของเอกสาร/รายงาน | SIL Open Font License 1.1 |
| Noto Sans Thai, Prompt, Mitr และฟอนต์จาก Google Fonts ที่ผู้ใช้เลือกติดตั้ง | ดาวน์โหลดจาก Google Fonts ตอนใช้งาน | SIL OFL 1.1 (ตามข้อมูลของแต่ละฟอนต์) |
| fonts-thai-tlwg, fonts-urw-base35 | ฟอนต์ระบบใน image | GPL-2.0 + font exception / AGPL-3.0 (URW base35) |

## สิ่งที่ไม่ใช่ซอร์สโค้ด และไม่อยู่ใน repo

ค่าตั้ง `.env*` (รหัสผ่าน, API key, secret), ฐานข้อมูล, ไฟล์ผู้ใช้, ใบรับรอง/คีย์ลงนามของระบบ
และข้อมูลเฉพาะเครื่องติดตั้ง — ไม่ใช่ "Corresponding Source" ตาม AGPL และไม่ต้องเปิดเผย
