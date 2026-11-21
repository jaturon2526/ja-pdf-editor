"""สร้าง frontend/e2e/fixtures/barcodes.pdf — บาร์โค้ด/QR สมมติสำหรับเทสต์ย้าย/ลบบาร์โค้ด (ห้ามใช้เอกสารจริง)

    cd backend && /home/claude/venv311/bin/python scripts/create_barcode_fixture.py
"""
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import barcode_service as bc  # noqa: E402

OUT = ROOT / "frontend" / "e2e" / "fixtures" / "barcodes.pdf"


def main() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 50), "Delivery note DN-0001 (sample)", fontsize=14)
    bc.insert_into_page(page, fitz.Rect(60, 70, 260, 120), bc.validate(bc.BarcodeSpec("code128", "DN-0001")))
    page.insert_image(fitz.Rect(420, 70, 520, 170),
                      stream=bc.render_png(bc.validate(bc.BarcodeSpec("qrcode", "https://example.com/dn/0001"))))
    page.insert_text((60, 220), "Total 1,250.00", fontsize=12)
    doc.save(OUT, garbage=4, deflate=True)
    print(OUT)


if __name__ == "__main__":
    main()
