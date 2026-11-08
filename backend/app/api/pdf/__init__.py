"""Router ของ /pdf — แยกเป็นโมดูลย่อยตามหน้าที่ (เดิมรวมอยู่ใน routes_pdf.py ไฟล์เดียว ~800 บรรทัด)

- files.py    : ไฟล์ของผู้ใช้ (Dashboard), upload/merge/convert-office, open, save, save-as-copy
- document.py : unlock, undo/redo, render หน้า, download/export, รหัสผ่าน, bookmark, properties, close
- pages.py    : ลบ/หมุน/เรียงหน้า, compress, flatten, OCR
- redact.py   : redaction ทุกแบบ
- scan.py     : สแกนเอกสารด้วยกล้องมือถือ → PDF + OCR (งานเบื้องหลัง)

ทุก endpoint ที่รับ {session_id} ต้องใช้ Depends(get_owned_session) (ดู app/api/deps.py)
"""
from fastapi import APIRouter

from app.api.pdf import document, files, pages, redact, scan
from app.api.pdf.files import check_storage_quota  # noqa: F401  (re-export ให้โค้ดเดิมที่ import ไว้)

router = APIRouter(prefix="/pdf", tags=["pdf"])
for _module in (files, redact, document, pages, scan):
    router.include_router(_module.router)
