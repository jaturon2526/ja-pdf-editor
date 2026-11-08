from typing import Annotated, Literal, Optional

from pydantic import ConfigDict, BaseModel, Field


# ---------- PDF open / unlock ----------

class UploadResponse(BaseModel):
    session_id: str
    filename: str
    status: Literal["ok", "password_required"]
    page_count: Optional[int] = None


class UnlockRequest(BaseModel):
    password: str


class UnlockResponse(BaseModel):
    status: Literal["ok", "invalid_password"]
    page_count: Optional[int] = None


class PDFInfoResponse(BaseModel):
    session_id: str
    filename: str
    page_count: int
    is_unlocked: bool
    page_sizes: list[tuple[float, float]]  # (width, height) ต่อหน้า หน่วย point
    # เอกสาร (เวอร์ชันที่จะได้ตอนดาวน์โหลด) มีรหัสผ่านป้องกันอยู่ตอนนี้ไหม (ดู
    # pdf_service.get_encryption_state) — frontend ใช้ตัดสินใจว่าเมนู File จะโชว์ "ลบรหัสผ่าน" หรือ
    # "เข้ารหัส PDF" (ผู้ใช้แจ้งขอ) ตรวจไม่ได้ (None) ถือว่า False ไว้ก่อน (โชว์ตัวเลือก "เข้ารหัส PDF"
    # เป็นค่าเริ่มต้น ซึ่งไม่เป็นอันตรายแม้เดาผิด — กดแล้วยังเปลี่ยนสถานะที่ถูกต้องได้เสมอ)
    is_password_protected: bool = False
    # เอกสารนี้ถูกเซ็นแล้วหรือยัง (Electronic Sign หรือ Digital Sign — ผู้ใช้แจ้งขอ) — ใช้โชว์สถานะ
    # ("เซ็นแล้ว") ในหน้าจอเท่านั้น ไม่ได้ใช้ปิดเมนูแก้ไขอีกต่อไป (ผู้ใช้แจ้งขอให้เอาการล็อกเอกสารหลังเซ็น
    # ออกทั้งสองแบบ — ดู app/services/signature_service.py)
    is_signed: bool = False
    signature_type: Optional[Literal["electronic", "digital"]] = None


# ---------- จัดการรหัสผ่าน (เมนู File > ลบรหัสผ่าน / เข้ารหัส PDF — ผู้ใช้แจ้งขอ) ----------

class AddPasswordRequest(BaseModel):
    password: str = Field(max_length=128)
    # aes256 = แนะนำ (PDF 1.7 + Adobe Extension Level 8, รองรับรหัสภาษาไทย) · aes128 = โปรแกรมรุ่นเก่ามาก
    encryption: Literal["aes256", "aes128"] = "aes256"


class PasswordChangeResponse(BaseModel):
    """ผลลัพธ์ของ /add-password และ /remove-password — is_password_protected คือสถานะล่าสุดหลังทำ
    รายการ ให้ frontend อัปเดต state ของเมนู File ทันที ไม่ต้องเรียก /info ซ้ำ"""
    status: Literal["ok"]
    is_password_protected: bool


class BookmarkItem(BaseModel):
    """bookmark หนึ่งรายการ — page เป็น 0-based (ตรงกับเลขหน้าที่ frontend ใช้ภายในทั่วทั้งแอป ไม่ใช่
    เลขหน้าแบบ 1-based ที่ผู้ใช้เห็นบนจอ) ผูกกับ PDF outline/TOC จริงของเอกสาร (ดู
    pdf_service.get_bookmarks/set_bookmarks) — ผู้ใช้แจ้งบั๊ก bookmark หายหลังดาวน์โหลดแล้วเปิดไฟล์ใหม่
    เพราะของเดิม (ฟีเจอร์เปลี่ยนชื่อ bookmark ที่ทำไปก่อนหน้านี้) เก็บเป็น React state ฝั่ง frontend
    ล้วนๆ ไม่เคยลงไปอยู่ในไบต์ไฟล์จริงเลย"""
    page: int
    label: str = Field(max_length=300)
    level: int | None = Field(default=None, ge=1, le=50)  # ชั้น (1 = บนสุด) — None = ใช้ของเดิม/ชั้นบนสุด
    ref: int | None = None  # ตำแหน่งในสารบัญเดิม (จาก GET) — คงจุดหมายเดิมไว้ ดู pdf_service.set_bookmarks


class SetBookmarksRequest(BaseModel):
    """ส่ง bookmark ทั้งชุดที่ต้องการมาแทนของเดิมทั้งหมดเสมอ (full replace ไม่ใช่ add/remove/rename
    ทีละรายการแยก endpoint) เพราะ PyMuPDF TOC ไม่มีกลไก id ต่อรายการที่เสถียรพอจะอ้างอิงทีละตัวได้ —
    ดูเหตุผลเต็มที่ pdf_service.set_bookmarks"""
    bookmarks: list[BookmarkItem] = Field(max_length=5000)


class BookmarksResponse(BaseModel):
    """ผลลัพธ์ของทั้ง GET และ PUT /{session_id}/bookmarks — frontend อัปเดต state จาก response นี้เสมอ
    (ไม่ใช่จากค่าที่ตัวเองส่งไปตอน PUT) เผื่อฝั่ง backend มีการกรอง/ปรับค่าระหว่างทาง"""
    bookmarks: list[BookmarkItem]


class UndoRedoResponse(BaseModel):
    """ผลลัพธ์ของ POST /pdf/{session_id}/undo หรือ /redo (ดู app/core/session.py หมายเหตุ Undo/Redo)
    frontend ใช้ can_undo/can_redo เปิด-ปิดปุ่มเมนู Edit > Undo/Redo และรีเฟรชหน้า/annotation/
    ย่อหน้าที่กำลังแก้ไขใหม่ทั้งหมดเสมอเมื่อ status เป็น "ok" (เอกสารเปลี่ยนไปทั้งฉบับ)"""
    status: Literal["ok", "nothing_to_undo", "nothing_to_redo"]
    can_undo: bool
    can_redo: bool
    # หลัง undo/redo สถานะ "เซ็นแล้ว" อาจเปลี่ยนไปด้วย (เช่น undo ย้อนกลับไปก่อนจุดที่เซ็น หรือ redo
    # กลับไปหลังจุดที่เซ็นอีกครั้ง) frontend ต้องอัปเดตสถานะปิด/เปิดเมนูแก้ไขต่างๆ ตามนี้ทันที ไม่ต้อง
    # เรียก /info ซ้ำ (ดู session._HistoryEntry ที่เก็บ is_signed/signature_type ไว้ต่อ snapshot)
    is_signed: bool = False
    signature_type: Optional[Literal["electronic", "digital"]] = None


class ReorderPagesRequest(BaseModel):
    """ย้ายหน้า (page_numbers, 0-based, อาจเลือกหลายหน้าพร้อมกัน) ไปยังตำแหน่งใหม่ในเอกสาร — ผู้ใช้แจ้งขอ
    2 ทางในแผงหน้าเอกสารด้านซ้าย: (1) กดเมาส์ค้างที่ thumbnail แล้วลากไปวาง — ส่ง target_page มา (แปลว่า
    "แทรกก่อนหน้าเลขนี้" นับตามลำดับเดิมก่อนย้าย — ไม่ส่ง/null แปลว่าวางท้ายสุด) (2) คลิกขวา > เลื่อนหน้า
    ขึ้น/ลง — ส่ง direction มาแทน (ขยับกลุ่มหน้าที่เลือกข้ามหน้าที่อยู่ติดกันไปทีละ 1 หน้า) ต้องส่งมาอย่างใด
    อย่างหนึ่งเท่านั้น (ดู pdf_service.reorder_pages — ถ้าไม่ส่งทั้งคู่จะย้ายไปวางท้ายสุดเป็นค่า fallback)"""
    page_numbers: list[int]
    target_page: Optional[int] = None
    direction: Optional[Literal["up", "down"]] = None


class ReorderPagesResponse(BaseModel):
    status: Literal["ok", "no_change"]
    page_count: int

class DeletePagesRequest(BaseModel):
    page_numbers: list[int]

class RotatePagesRequest(BaseModel):
    page_numbers: list[int]
    angle: int = 90  # 90 for clockwise, -90 for counter-clockwise

class CompressPdfRequest(BaseModel):
    profile: Literal["screen", "ebook", "printer", "prepress"] = "screen"



class SignatureInfo(BaseModel):
    name: Optional[str] = None
    reason: Optional[str] = None
    location: Optional[str] = None
    contact_info: Optional[str] = None
    date: Optional[str] = None
    is_valid: bool = False
    # ลายเซ็นนี้ออกโดย CA ที่ระบบเชื่อถือหรือไม่ (None = ตรวจไม่ได้) — cert แบบ self-signed จะเป็น False
    is_trusted: Optional[bool] = None
    cert_subject: Optional[str] = None
    cert_issuer: Optional[str] = None
    cert_subject_cn: Optional[str] = None
    cert_subject_org: Optional[str] = None
    cert_subject_email: Optional[str] = None
    cert_issuer_cn: Optional[str] = None
    cert_issuer_org: Optional[str] = None
    cert_serial: Optional[str] = None
    cert_valid_from: Optional[str] = None
    cert_valid_to: Optional[str] = None
    cert_expired: Optional[bool] = None
    cert_days_remaining: Optional[int] = None
    cert_signature_algorithm: Optional[str] = None
    cert_key_info: Optional[str] = None
    cert_sha256: Optional[str] = None
    cert_sha1: Optional[str] = None
    cert_self_signed: Optional[bool] = None

class DocumentPropertiesResponse(BaseModel):

    """คุณสมบัติเอกสาร (Document Properties) แบบเดียวกับที่ Acrobat Reader โชว์ (ผู้ใช้แจ้งขอ) — ดึงจาก
    fitz.Document.metadata + ตรวจเพิ่มเติมด้วย pikepdf สำหรับ Tagged PDF/Fast Web View ทุกฟิลด์เป็น
    Optional เพราะ PDF ไม่บังคับต้องมีข้อมูลเหล่านี้ครบ (ไฟล์จำนวนมากไม่ใส่ title/author ฯลฯ เลย) และบาง
    ฟิลด์ (tagged_pdf, fast_web_view, is_encrypted) อาจตรวจไม่ได้ในบางไฟล์ — คืน None ให้ frontend แสดง
    "ไม่ทราบ" แทนที่จะทำให้ทั้ง endpoint error (ดู pdf_service.get_document_properties)"""
    # ---- Description ----
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None
    creator: Optional[str] = None          # แอปที่ใช้สร้างเอกสารต้นฉบับ (เช่น "Microsoft Word")
    producer: Optional[str] = None         # PDF Producer (เช่น "Skia/PDF", "Adobe PDF Library")
    creation_date: Optional[str] = None    # แปลงเป็นข้อความอ่านง่ายแล้ว (dd/mm/yyyy HH:MM)
    mod_date: Optional[str] = None
    # ---- Advanced ----
    pdf_version: Optional[str] = None
    file_size_bytes: int
    file_size_display: str
    page_count: int
    page_width_pt: float
    fonts: Optional[list[str]] = None
    page_height_pt: float
    page_size_display: Optional[str] = None
    tagged_pdf: Optional[bool] = None
    fast_web_view: Optional[bool] = None
    is_encrypted: Optional[bool] = None
    encryption: Optional[str] = None       # วิธีเข้ารหัสที่ตั้งไว้ในเซสชันนี้ (aes256/aes128)
    pdfa: Optional[str] = None             # ไฟล์ประกาศว่าเป็น PDF/A (เช่น "PDF/A-2b") — PDF/A ห้ามเข้ารหัส
    signatures: list[SignatureInfo] = []


# ---------- Rendering ----------

class RenderPageResponse(BaseModel):
    page_number: int
    width: float
    height: float
    image_base64: str  # ภาพ (JPEG ค่าเริ่มต้น / PNG เมื่อขอ fmt=png) เข้ารหัส base64 พร้อมแสดงผลฝั่ง client
    image_mime: str = "image/png"


# ---------- Annotation ----------

AnnotationType = Literal["highlight", "freetext", "rect", "text_note"]


class Rect(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


Color01 = Annotated[float, Field(ge=0, le=1)]
ANNOT_TEXT_MAX = 10000


class AnnotationCreate(BaseModel):
    page_number: int = Field(ge=0)
    type: AnnotationType
    rect: Rect
    content: Optional[str] = Field(default=None, max_length=ANNOT_TEXT_MAX)  # ข้อความ (สำหรับ freetext / text_note)
    color: Optional[tuple[Color01, Color01, Color01]] = None  # RGB 0-1
    fontsize: Optional[float] = Field(default=12, ge=4, le=200)
    fontname: Optional[str] = None         # key จาก GET /edit/fonts — เฉพาะ freetext (ผู้ใช้แจ้งเพิ่ม)
    # freetext: ปรับความสูงกรอบให้พอดีกับข้อความ (คลิกวางกล่องโดยไม่ลากขนาด) — ความกว้างคงตาม rect
    auto_height: bool = False
    # highlight หลายบรรทัด: กรอบของแต่ละบรรทัด → ไฮไลต์เดียวหลาย quad (กด Undo ครั้งเดียวหายทั้งหมด
    # เดิมส่งทีละบรรทัด = annotation ละบรรทัด ต้อง Undo ทีละบรรทัด) · rect = กรอบรวม
    line_rects: Optional[list[Rect]] = Field(default=None, max_length=500)


class AnnotationInfo(BaseModel):
    xref: int
    page_number: int
    type: str
    rect: Rect
    content: Optional[str] = None
    color: Optional[tuple[float, float, float]] = None  # RGB 0-1 (สีเส้น/ไฮไลท์) — ใช้โชว์ swatch ปัจจุบันตอนแก้ไข
    fontname: Optional[str] = None         # ฟอนต์ปัจจุบันของกล่องข้อความ (freetext เท่านั้น) — ใช้โชว์ dropdown ปัจจุบันตอนเลือกแก้ไข
    fontsize: Optional[float] = None       # ขนาดตัวอักษรปัจจุบันของกล่องข้อความ (freetext เท่านั้น)


class AnnotationDeleteRequest(BaseModel):
    page_number: int
    xref: int


class AnnotationUpdateRequest(BaseModel):
    """แก้ไข annotation ที่มีอยู่แล้ว (ไฮไลท์: ย่อ/ขยาย+เปลี่ยนสี, กรอบสี่เหลี่ยม: ย่อ/ขยาย+แก้ข้อความ+
    เปลี่ยนสี, โน้ต: แก้ข้อความ+เปลี่ยนสี) — ส่งเฉพาะฟิลด์ที่ต้องการเปลี่ยน ฟิลด์ที่เว้นว่างไว้จะคงค่าเดิม
    (ดู annotation_service.update_annotation ซึ่ง implement ด้วยการลบของเดิมแล้วสร้างใหม่ — PyMuPDF
    ไม่รองรับการแก้ไข quad points ของ highlight ในตำแหน่งเดิมตรงๆ วิธีนี้ใช้ได้กับทุกชนิดสม่ำเสมอกัน)"""
    page_number: int
    xref: int
    rect: Optional[Rect] = None
    color: Optional[tuple[Color01, Color01, Color01]] = None
    content: Optional[str] = Field(default=None, max_length=ANNOT_TEXT_MAX)
    fontname: Optional[str] = None         # เปลี่ยนฟอนต์ของกล่องข้อความ (freetext เท่านั้น — ผู้ใช้แจ้งเพิ่ม)
    fontsize: Optional[float] = Field(default=None, ge=4, le=200)  # ขนาดตัวอักษรของกล่องข้อความ (freetext เท่านั้น)


class WordInfo(BaseModel):
    """หนึ่งคำในหน้า พร้อมตำแหน่งและ line_key (block_no-line_no จาก PyMuPDF get_text('words'))
    ใช้ให้ frontend คำนวณตอนผู้ใช้ "ลากเลือก" พื้นที่ด้วยเมาส์ (เครื่องมือไฮไลท์/โน้ต) ว่าครอบคำไหนบ้าง
    แล้วรวมเป็นกรอบทีละบรรทัด (snap ให้พอดีตัวอักษรจริง) แทนที่จะใช้กรอบดิบตามที่ลากเป๊ะๆ — ให้ผลลัพธ์
    เหมือนการ "เลือกข้อความ" ใน PDF reader ทั่วไป (ดู annotation_service.get_words)
    """
    rect: Rect
    text: str
    line_key: str


# ---------- Text editing ----------

TextAlign = Literal["left", "center", "right"]


class TextBlock(BaseModel):
    """หนึ่งช่วงข้อความ (ย่อหน้า) ที่ดึงจากหน้า PDF พร้อมตำแหน่งและ font เดิม ใช้ให้ frontend
    คลิกเลือกแล้วส่งกลับมาแก้ไข — block_id อาจมาจาก 2 แหล่ง (ดู edit_service.get_text_blocks):
    "<block>-<กลุ่มบรรทัด>" สำหรับข้อความดิบที่ยังไม่เคยถูกแก้ในเซสชันนี้ หรือ "edit-<id>" สำหรับ
    ย่อหน้าที่เคยถูกแก้ไปแล้วก่อนหน้านี้ (เก็บ track ไว้ใน session ให้เลือกกลับมาแก้ซ้ำได้อีก)
    """
    block_id: str
    text: str
    rect: Rect
    fontname: str
    fontsize: float
    color: int              # sRGB int ตามที่ PyMuPDF คืนมา
    align: TextAlign = "left"  # จัดตัวหนังสือ (ผู้ใช้แจ้งเพิ่ม) — ค่าเริ่มต้นสำหรับข้อความดิบที่ยังไม่เคยแก้ไข
                                # ในเซสชันนี้คือ "left" เสมอ (ยังไม่รู้การจัดวางเดิมจาก PDF) ส่วนย่อหน้าที่เคย
                                # แก้ไขไปแล้วจะได้ค่าจากทะเบียน session.text_edits (ดู edit_service.get_text_blocks)
    valign: Literal["top", "middle", "bottom"] = "top" # จัดแนวตั้ง (ผู้ใช้แจ้งเพิ่ม)
    underline: bool = False    # มีเส้นขีดใต้หรือไม่ (ผู้ใช้แจ้งเพิ่ม — ปุ่ม Underline ในหน้าจอแก้ไขข้อความ)
                                # ค่าเริ่มต้นสำหรับข้อความดิบที่ยังไม่เคยแก้ไขคือ False เสมอ (PyMuPDF ไม่บอก
                                # ว่าข้อความเดิมมีเส้นขีดใต้วาดแยกอยู่หรือเปล่า) ส่วนย่อหน้าที่เคยแก้ไขไปแล้ว
                                # จะได้ค่าจากทะเบียนเหมือน align ด้านบน
    is_bold: bool = False      # ตรวจจากชื่อ font + span flags ของ PDF — ใช้ pre-select ปุ่ม Bold บน Properties Panel
    is_italic: bool = False    # ตรวจจากชื่อ font + span flags ของ PDF — ใช้ pre-select ปุ่ม Italic บน Properties Panel


class TextEditRequest(BaseModel):
    page_number: int
    rect: Rect               # ตำแหน่งที่จะวาดข้อความใหม่ลงไป (ผู้ใช้อาจลากปรับขนาดกล่องเองแล้วก็ได้)
    new_text: str
    fontsize: Optional[float] = 14
    fontname: Optional[str] = "sarabun"  # key จาก GET /edit/fonts (ดู app/services/fonts.py) — ไม่ใช่ base-14 font ของ PyMuPDF อีกต่อไป เพราะต้องรองรับภาษาไทย
    color: Optional[tuple[float, float, float]] = (0, 0, 0)  # RGB 0-1
    align: Optional[TextAlign] = "left"  # จัดตัวหนังสือชิดซ้าย/กึ่งกลาง/ชิดขวาภายในกล่อง (ผู้ใช้แจ้งเพิ่ม)
    valign: Optional[Literal["top", "middle", "bottom"]] = "top" # จัดแนวตั้ง
    underline: Optional[bool] = False  # ขีดเส้นใต้ (ผู้ใช้แจ้งเพิ่ม — ไม่ใช่ font variant ใช้ได้กับทุกฟอนต์)
    block_id: Optional[str] = None
    # ตำแหน่งเดิมของย่อหน้านี้ "ก่อน" การแก้ไขครั้งนี้ (ตามที่ยังวาดอยู่จริงในไฟล์ตอนนี้) — ใช้ตอน
    # แก้ไขซ้ำย่อหน้าที่เคยแก้ไปแล้ว เพื่อให้ redact ลบภาพข้อความเดิมที่เคยวาดไว้ (จาก edit ครั้งก่อน)
    # ออกให้หมดก่อนวาดใหม่ ไม่งั้นจะเหลือภาพเก่าซ้อนอยู่ (ดูหมายเหตุ "แก้บั๊กสำคัญ #6" ใน edit_service.py)
    previous_rect: Optional[Rect] = None


# ---------- Image editing ----------

class ImageInfo(BaseModel):
    id: Optional[str] = None
    xref: int
    page_number: int
    rect: Rect
    width: int
    height: int


class ImageReplaceRequest(BaseModel):
    page_number: int
    xref: int
    # รูปใหม่ส่งมาเป็น multipart file แยกต่างหาก (ดู routes_edit.py) — ฟิลด์นี้ไว้ใช้กรณีอนาคตอยากส่งเป็น base64 แทน
    image_base64: Optional[str] = None


class ImageRepositionRequest(BaseModel):
    """ย้าย/ปรับขนาดรูปภาพที่มีอยู่แล้วในหน้าด้วยเมาส์ (ลาก handle/ลากทั้งกล่อง) — ไม่ได้เปลี่ยนเนื้อรูป
    แค่ขยับ/ย่อ-ขยายกรอบเท่านั้น (ดู edit_service.reposition_image หมายเหตุ "แก้บั๊กสำคัญ #7")
    old_rect คือตำแหน่งจริงของรูปนี้ตอนนี้ (ก่อนย้าย) ใช้ตอน redact ล้างรูปเดิมออกก่อนวาดที่ตำแหน่งใหม่"""
    old_rect: Rect
    new_rect: Rect


class FontOptionResponse(BaseModel):
    """หนึ่งตัวเลือกใน dropdown font ของ properties panel ตอนแก้ไขข้อความ (ดู app/services/fonts.py)
    removable=True เฉพาะฟอนต์ที่ผู้ใช้ติดตั้งเอง (เมนู File > ติดตั้งฟอนต์ใหม่... — ผู้ใช้แจ้งขอ) —
    ฟอนต์ที่ bundle มากับแอปหรือมาจาก Google Fonts ลบไม่ได้ (removable=False) กันเผลอลบทิ้งจนเอกสารเก่า
    ที่เคยใช้ฟอนต์เหล่านั้นแก้ไขต่อไม่ได้ — frontend ใช้ field นี้ตัดสินใจว่าจะโชว์ปุ่มลบให้ฟอนต์ไหนบ้าง"""
    key: str
    label: str
    # URL ไฟล์ฟอนต์สำหรับ @font-face (ฟอนต์ที่ผู้ใช้ติดตั้งเองมี token ของเจ้าของแนบมา — ดู routes_edit.get_font_file)
    file_url: str | None = None
    removable: bool = False


class FontInstallResponse(BaseModel):
    """ผลลัพธ์ของ POST /edit/fonts/install (ผู้ใช้แจ้งขอเพิ่ม — รองรับติดตั้งหลายไฟล์/หลายสไตล์ต่อ 1
    font family เหมือนปุ่ม Bold/Italic/Bold Italic บน toolbar) — `installed` คือไฟล์ที่เพิ่งอัปโหลดไป
    หมาดๆ ตัวเดียว (frontend ใช้ `installed.key` เป็น family_key ตอนจะอัปโหลดไฟล์สไตล์ถัดไปเข้า family
    เดียวกันต่อ ถ้านี่คือไฟล์ style=regular แรกของ family ใหม่) ส่วน `fonts` คือรายการฟอนต์ทั้งชุดล่าสุด
    แบบ flat เหมือน endpoint เดิมทุกประการ (ไม่กระทบ dropdown เดิมที่ยังใช้ flat list อยู่)"""
    installed: FontOptionResponse
    fonts: list[FontOptionResponse]
    # คำเตือนของไฟล์ที่เพิ่งติดตั้ง (ไม่มีตัวอักษรไทย / ผู้ออกแบบห้ามฝังลงเอกสาร) — ติดตั้งสำเร็จแล้ว แค่ให้ผู้ใช้รู้
    warnings: list[str] = []


class FontFamilyResponse(BaseModel):
    """หนึ่ง font family พร้อมสไตล์ที่มีให้ใช้ (ดู app/services/fonts.list_font_families) — ใช้กับ
    GET /edit/font-families แทนที่ FontOptionResponse แบบ flat ตอนต้องเลือก family แล้วกดปุ่มสไตล์
    (Bold/Italic/Bold Italic) แทนที่จะเห็นเป็นหลาย option แยกกันในรายการเดียว ค่าใน `styles` เป็น None
    ถ้าไม่มีไฟล์ของสไตล์นั้นเลย (frontend ต้อง disable ปุ่มสไตล์นั้นๆ ไม่ auto สร้างตัวหนา/เอียงปลอม —
    ดูเหตุผลใน app/services/fonts.py หมายเหตุ install_custom_font)"""
    key: str
    label: str
    removable: bool = False
    styles: dict[str, Optional[str]]


# ---------- Digital Signature (ผู้ใช้แจ้งขอ: เมนู Digital Signature ถัดจาก Tools) ----------
#
# Electronic Sign: ผู้ใช้พิมพ์ข้อความ/อัปโหลดรูปลายเซ็น/วาดจากหน้าจอ ได้รูปลายเซ็น (PNG โปร่งใส) เป็น
# base64 กลับมาจาก frontend เอง (ประมวลผลฝั่ง client ทั้งหมด — canvas วาด/พิมพ์ข้อความ) ส่งมาแค่รูปสำเร็จ
# รูปเดียวพร้อมตำแหน่ง/ขนาดที่ผู้ใช้ลากวางแล้ว ฝัง PDF ด้วย page.insert_image() ตรงๆ (ดู
# signature_service.apply_electronic_signature) ไม่ใช่ลายเซ็นเข้ารหัส แค่ตราประทับภาพ
#
# Digital Sign: ผู้ใช้อัปโหลดไฟล์ p12/pfx + รหัสผ่าน + เลือกพื้นที่แสดงผล — ต้องส่งเป็น multipart/form-data
# (มีไฟล์แนบ) จึงไม่มี Pydantic request schema แยก (รับผ่าน UploadFile/Form โดยตรงใน routes_signature.py)
# ใช้ SignatureStatusResponse ร่วมกันเป็นผลลัพธ์ทั้งสองแบบ

class ElectronicSignRequest(BaseModel):
    page_number: int = Field(ge=0)
    rect: Rect
    image_base64: str  # PNG (มักมีพื้นหลังโปร่งใส) เข้ารหัส base64 — ไม่ใส่ "data:image/png;base64," นำหน้า


class SignatureStatusResponse(BaseModel):
    """ผลลัพธ์ของ POST /signature/{session_id}/electronic และ /digital — เอกสาร "ไม่" ถูกล็อกไม่ให้
    แก้ไขต่ออีกแล้วหลังเซ็นสำเร็จ ไม่ว่าชนิดไหน (ผู้ใช้แจ้งขอเอาการล็อกออกทั้งสองแบบ) is_signed/
    signature_type ใช้โชว์สถานะในหน้าจอเท่านั้น signer_name มีค่าเฉพาะ Digital Sign (ชื่อผู้เซ็นที่ดึง
    จาก certificate ใน p12/pfx)"""
    status: Literal["ok"]
    is_signed: bool
    signature_type: Optional[Literal["electronic", "digital"]] = None
    signer_name: Optional[str] = None

class WatermarkRequest(BaseModel):
    text: str = Field(max_length=200)
    opacity: float = Field(default=0.5, ge=0.05, le=1.0)
    angle: float = Field(default=45.0, ge=-360, le=360)
    color: tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]] = (0.5, 0.5, 0.5)
    font_size: float = Field(default=60.0, ge=8, le=300)

class BarcodeRequest(BaseModel):
    """บาร์โค้ด (เมนูแทรก › บาร์โค้ด) — ดู services/barcode_service.py"""
    type: str = Field(max_length=20)
    data: str = Field(max_length=1000)
    ec_level: Literal["L", "M", "Q", "H"] = "M"
    show_text: bool = True
    bar_color: str = Field(default="#000000", max_length=7)
    bg_color: str = Field(default="#FFFFFF", max_length=7)

    def to_spec(self):
        from app.services.barcode_service import BarcodeSpec
        return BarcodeSpec(**self.model_dump(include={"type", "data", "ec_level", "show_text", "bar_color", "bg_color"}))


class BarcodeInsertRequest(BarcodeRequest):
    x0: float
    y0: float
    x1: float
    y1: float


class PageNumberRequest(BaseModel):
    """ใส่เลขหน้า (เมนูแทรก › เลขหน้า และเมนูไฟล์ใน Dashboard) — ดู edit_service/page_numbers.py"""
    fmt: Literal["n", "n_total"] = "n"
    separator: str = Field(default="/", max_length=20)
    prefix: str = Field(default="", max_length=40)
    suffix: str = Field(default="", max_length=40)
    thai_digits: bool = False
    start_page: int = Field(default=1, ge=1, le=100000)
    end_page: Optional[int] = Field(default=None, ge=1, le=100000)
    start_number: int = Field(default=1, ge=0, le=100000)
    vpos: Literal["top", "bottom"] = "bottom"
    hpos: Literal["left", "center", "right"] = "center"
    mirror_even: bool = False
    margin_pt: float = Field(default=28.0, ge=0, le=200)
    font_size: float = Field(default=11.0, ge=5, le=72)
    color: tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]] = (0.2, 0.2, 0.2)
    font: str = Field(default="sarabun", max_length=100)

    def to_options(self):
        from app.services.edit_service.page_numbers import PageNumberOptions
        return PageNumberOptions(**self.model_dump())


class PlanConfigResponse(BaseModel):
    plan_type: str
    max_sessions: int

    model_config = ConfigDict(from_attributes=True)

class PlanConfigUpdateRequest(BaseModel):
    max_sessions: int
