"""สร้าง frontend/e2e/fixtures/table.pdf — ตารางสมมติสำหรับเทสต์แก้ไขตาราง (ห้ามใช้เอกสารจริง)

    /home/claude/venv311/bin/python backend/scripts/create_table_fixture.py
"""
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "backend" / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf"
OUT = ROOT / "frontend" / "e2e" / "fixtures" / "table.pdf"

XS = [60, 110, 300, 420, 535]
YS = [120, 150, 175, 200, 225]
ROWS = [
    ["ลำดับ", "รายการ", "วันที่", "จำนวนเงิน"],
    ["1", "ค่าเดินทางไปประชุมวิชาการ", "01/11/26 - 03/11/26", "1,250.00"],
    ["2", "ค่าที่พัก", "01/11/26", "980.50"],
    ["3", "ค่าอาหาร", "02/11/26", "420.00"],
]


def main() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="th", fontfile=str(FONT))
    page.insert_text((60, 90), "ใบสรุปค่าใช้จ่าย (ตัวอย่าง)", fontname="th", fontsize=16)
    page.draw_rect(fitz.Rect(XS[0], YS[0], XS[-1], YS[1]), color=None, fill=(0.88, 0.92, 0.97))
    for x in XS:
        page.draw_line((x, YS[0]), (x, YS[-1]), color=(0, 0, 0), width=0.75)
    for y in YS:
        page.draw_line((XS[0], y), (XS[-1], y), color=(0, 0, 0), width=0.75)
    for r, row in enumerate(ROWS):
        for c, text in enumerate(row):
            page.insert_text((XS[c] + 5, YS[r] + 17), text, fontname="th", fontsize=10.5)
    page.insert_text((360, 300), "รวมทั้งสิ้น 2,650.50 บาท", fontname="th", fontsize=12)
    doc.save(OUT, garbage=4, deflate=True)
    print(OUT)


if __name__ == "__main__":
    main()
