"""ใส่ลายน้ำข้อความทุกหน้า"""
from __future__ import annotations

import io

import fitz  # PyMuPDF
from fpdf import FPDF

from app.core.session import PDFSession
from app.services import fonts
from app.services.pdf_service import PDFError, require_unlocked

RENDER_DPI = 300
MAX_PX = 4000      # ด้านยาวของภาพลายน้ำก่อนหมุน
FIT = 0.9          # ลายน้ำกว้าง/สูงได้ไม่เกิน 90% ของหน้า


def apply_watermark(session: PDFSession, text: str, opacity: float, angle: float, color: tuple[float, float, float], font_size: float):
    """
    ประทับลายน้ำ (Watermark) ลงบนเอกสารทุกหน้า
    รองรับการจัดวางภาษาไทยแบบ OpenType Shaping (fpdf2 + uharfbuzz) 
    ป้องกันปัญหาวรรณยุกต์จม สระลอย หรือสระซ้อนทับกัน
    และหมุนองศาอิสระด้วยความละเอียดสูง (300 DPI) ผ่าน Pillow พร้อม Transparency
    """
    text = " ".join((text or "").split())  # ขึ้นบรรทัด/แท็บ → ช่องว่าง (ลายน้ำเป็นบรรทัดเดียว)
    if not text:
        return

    from PIL import Image
    doc = require_unlocked(session)
    _, font_path = fonts.resolve_font_path("sarabun", user_id=session.user_id)

    # 1. วัดขนาดข้อความด้วย FPDF + uharfbuzz (Thai text shaping)
    temp_pdf = FPDF(unit="pt")
    temp_pdf.set_auto_page_break(False)
    temp_pdf.add_font("WatermarkFont", "", font_path)
    temp_pdf.add_page()
    temp_pdf.set_font("WatermarkFont", size=font_size)
    temp_pdf.set_text_shaping(True, script="thai", language="tha")

    text_width = temp_pdf.get_string_width(text)
    text_height = font_size * 1.6
    padding = 20.0

    box_w = max(text_width + padding * 2, 50.0)
    box_h = max(text_height + padding * 2, 50.0)

    # 2. สร้าง micro-PDF ที่เรนเดอร์ข้อความพร้อมจัดรูปสระ/วรรณยุกต์อย่างถูกต้อง
    pdf = FPDF(format=(box_w, box_h), unit="pt")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.add_font("WatermarkFont", "", font_path)
    pdf.set_font("WatermarkFont", size=font_size)
    r = max(0, min(255, int(color[0] * 255)))
    g = max(0, min(255, int(color[1] * 255)))
    b = max(0, min(255, int(color[2] * 255)))
    pdf.set_text_color(r, g, b)
    pdf.set_text_shaping(True, script="thai", language="tha")
    pdf.c_margin = 0
    pdf.set_xy(padding, padding + font_size * 0.25)
    pdf.cell(w=text_width, h=font_size, text=text, align="C")

    micro_pdf_bytes = pdf.output()
    micro_doc = fitz.open("pdf", micro_pdf_bytes)
    # เรนเดอร์เป็นภาพพร้อม Alpha channel — 300 DPI แต่จำกัดด้านยาวไม่เกิน MAX_PX
    # (ข้อความยาว × ฟอนต์ใหญ่ที่ 300 DPI = ภาพกว้างนับแสนพิกเซล กินหน่วยความจำจนเซิร์ฟเวอร์ค้าง)
    dpi = max(1, min(RENDER_DPI, int(MAX_PX * 72.0 / max(box_w, box_h))))
    pix = micro_doc[0].get_pixmap(dpi=dpi, alpha=True)
    micro_doc.close()

    # 3. นำภาพมาปรับความโปร่งใส (Opacity) และหมุนองศา (Rotate)
    img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)

    clamped_opacity = max(0.01, min(1.0, float(opacity)))
    a_ch = img.getchannel("A").point(lambda p: int(p * clamped_opacity))
    img.putalpha(a_ch)

    # หมุนภาพตามมุมที่ผู้ใช้กำหนด (มุมบวกหมุนทวนเข็มนาฬิกา เอียงขึ้นแบบลายน้ำมาตรฐาน)
    rotated_img = img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    bbox = rotated_img.getbbox()  # ตัดขอบโปร่งใสออก → จัดกึ่งกลาง/ย่อให้พอดีหน้าตามตัวอักษรจริง
    if bbox:
        rotated_img = rotated_img.crop(bbox)

    buf = io.BytesIO()
    rotated_img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # แปลงขนาด pixel กลับเป็น point (72 DPI)
    scale = 72.0 / dpi
    img_w = rotated_img.width * scale
    img_h = rotated_img.height * scale

    # 4. วางลายน้ำไว้กึ่งกลางหน้า "ตามที่ผู้ใช้เห็น" ทุกหน้า
    # - หน้าที่ถูกหมุน (/Rotate 90/180/270): คำนวณในพิกัดที่มองเห็นแล้วแปลงกลับ + หมุนภาพตามหน้า
    #   (เดิมใช้ page.rect ตรงๆ → ลายน้ำเยื้องกึ่งกลางและเอียงผิดทิศ)
    # - ข้อความยาว/หน้าเล็ก (A5, ใบเสร็จ, แนวนอน): ย่อให้อยู่ในหน้า ไม่ให้ล้นขอบจนอ่านไม่ออก
    try:
        for page in doc:
            vis = page.rect
            fit = min(1.0, FIT * vis.width / img_w, FIT * vis.height / img_h)
            w_pt, h_pt = img_w * fit, img_h * fit
            x0 = vis.x0 + (vis.width - w_pt) / 2
            y0 = vis.y0 + (vis.height - h_pt) / 2
            target = fitz.Rect(x0, y0, x0 + w_pt, y0 + h_pt) * page.derotation_matrix
            page.insert_image(target, stream=png_bytes, overlay=True, rotate=page.rotation)
    except Exception as exc:
        raise PDFError(f"ใส่ลายน้ำไม่สำเร็จ: {exc}")

    session.mark_dirty()
