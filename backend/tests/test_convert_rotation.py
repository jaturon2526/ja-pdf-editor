"""PDF→Word: หน้าที่ถูกหมุน (/Rotate) ต้องได้ข้อความแนวนอนเสมอ ไม่ใช่ข้อความตะแคงในหน้าแนวนอน"""
import fitz

from app.services.pdf2docx_fixes import _ltr_text_share, upright_rotated_pages


def _doc_bytes(build) -> bytes:
    doc = fitz.open()
    build(doc)
    return doc.tobytes()


def test_rotated_upright_page_is_unrotated():
    # หน้าแนวตั้งปกติที่ผู้ใช้กดหมุน 90° ใน Editor ก่อนแปลง
    def build(doc):
        doc.new_page().insert_text((72, 100), "Upright text on a portrait page", fontsize=14)
        doc.new_page().insert_text((72, 100), "Page two rotated by the user", fontsize=14)
        doc[1].set_rotation(90)

    out = fitz.open("pdf", upright_rotated_pages(_doc_bytes(build)))
    assert [p.rotation for p in out] == [0, 0]
    assert out[1].rect.width < out[1].rect.height  # กลับเป็นแนวตั้งตามต้นฉบับ
    assert _ltr_text_share(out[1]) == 1.0


def test_sideways_content_made_readable_by_rotation_is_baked_in():
    # เนื้อหาวาดตะแคงไว้ และ /Rotate คือสิ่งที่ทำให้อ่านได้ (เช่น ตารางแนวนอน) → ได้หน้าแนวนอน ข้อความตั้งตรง
    def build(doc):
        page = doc.new_page()
        page.insert_text((100, 700), "Landscape table header", fontsize=14, rotate=90)
        page.set_rotation(90)

    data = _doc_bytes(build)
    assert _ltr_text_share(fitz.open("pdf", data)[0]) == 0.0  # ต้นฉบับ: ข้อความไม่แนวนอนในพิกัดเดิม
    out = fitz.open("pdf", upright_rotated_pages(data))
    page = out[0]
    assert page.rotation == 0
    assert _ltr_text_share(page) == 1.0
    assert page.rect.width > page.rect.height


def test_unrotated_pdf_is_returned_unchanged():
    data = _doc_bytes(lambda doc: doc.new_page().insert_text((72, 100), "Plain", fontsize=12))
    assert upright_rotated_pages(data) is data
