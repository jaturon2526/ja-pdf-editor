"""สร้างไฟล์ตัวอย่าง Auto-Gen แบบมี QR Code / บาร์โค้ด → backend/sample_autogen/
  template_qr.docx  บัตรพนักงาน: รูปตัวแทน QR (Alt Text) + QR ในข้อความ (ภาษาไทย) + บาร์โค้ด Code 128
  data_qr.xlsx / data_qr.csv  ข้อมูล 4 คน (คนที่ 4 ไม่มีลิงก์ → ไม่มี QR มุมขวา)
รัน: cd backend && python ../scripts/create_qr_sample.py
"""
import csv
import io
from pathlib import Path

import openpyxl
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "backend" / "sample_autogen"
ROWS = [
    {"name": "สมชาย ใจดี", "emp_id": "EMP-00123", "dept": "บัญชี", "profile_url": "https://example.com/staff/EMP-00123", "phone": "081-234-5678"},
    {"name": "สมหญิง รักงาน", "emp_id": "EMP-00124", "dept": "ฝ่ายขาย", "profile_url": "https://example.com/staff/EMP-00124", "phone": "089-111-2222"},
    {"name": "John Smith", "emp_id": "EMP-00125", "dept": "IT", "profile_url": "https://example.com/staff/EMP-00125", "phone": "02-345-6789"},
    {"name": "วิไล มั่นคง", "emp_id": "EMP-00126", "dept": "บุคคล", "profile_url": "", "phone": "086-555-0000"},
]


def placeholder_png() -> bytes:
    img = Image.new("RGB", (300, 300), "#E5E7EB")
    d = ImageDraw.Draw(img)
    d.rectangle((6, 6, 293, 293), outline="#9CA3AF", width=6)
    d.text((105, 120), "QR", fill="#6B7280", font_size=64)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def thai(run, size=14, bold=False, color=None):
    run.font.name = "Sarabun"
    run._element.rPr.rFonts.set(qn("w:cs"), "Sarabun")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.cs_bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def build_template() -> None:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(148), Mm(105)       # การ์ด A6 แนวนอน
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Mm(8))
    style = doc.styles["Normal"]
    style.font.name = "Sarabun"
    style.element.rPr.rFonts.set(qn("w:cs"), "Sarabun")
    style.font.size = Pt(11)

    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    left, right = table.rows[0].cells
    left.width, right.width = Mm(98), Mm(32)
    p = left.paragraphs[0]
    thai(p.add_run("บัตรพนักงาน · JA Company"), 10, color="6B7280")
    thai(left.add_paragraph().add_run("{{ name }}"), 18, bold=True)
    thai(left.add_paragraph().add_run("รหัส {{ emp_id }} · แผนก {{ dept }}"), 11)
    thai(left.add_paragraph().add_run("โทร {{ phone }}"), 11)

    # แบบที่ 2: รูปตัวแทน — ขนาด/ตำแหน่งตามที่จัดไว้ · Alt Text = นิพจน์ QR
    rp = right.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    rp.add_run().add_picture(io.BytesIO(placeholder_png()), width=Mm(28), height=Mm(28))
    doc_pr = rp._p.xpath(".//wp:docPr")[0]
    doc_pr.set("descr", "{{ qr(profile_url) }}")
    doc_pr.set("name", "QR โปรไฟล์ (รูปตัวแทน)")
    cap = right.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    thai(cap.add_run("สแกนดูโปรไฟล์"), 8, color="6B7280")

    # แบบที่ 1: พิมพ์ในข้อความ — บาร์โค้ด Code 128 กว้าง 60 มม. (สูงตามสัดส่วน)
    bp = doc.add_paragraph()
    bp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bp.add_run('{{ barcode("code128", emp_id, 60) }}')
    # QR ข้อความภาษาไทย (รวมหลายคอลัมน์ด้วย ~) ขนาด 16 มม.
    qp = doc.add_paragraph()
    thai(qp.add_run("ข้อมูลติดต่อ: "), 9, color="6B7280")
    qp.add_run('{{ qr("ชื่อ: " ~ name ~ "\\nโทร: " ~ phone, 16) }}')
    doc.save(OUT / "template_qr.docx")


def build_data() -> None:
    headers = list(ROWS[0])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "staff"
    ws.append(headers)
    for r in ROWS:
        ws.append([r[h] for h in headers])
    for col in "ABCDE":
        ws.column_dimensions[col].width = 32
    wb.save(OUT / "data_qr.xlsx")
    with open(OUT / "data_qr.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(ROWS)


if __name__ == "__main__":
    build_template()
    build_data()
    print("สร้าง template_qr.docx, data_qr.xlsx, data_qr.csv ใน", OUT)
