from pathlib import Path
from typing import Optional

from app.api.deps import get_owned_session
from app.core.session import PDFSession
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import get_current_active_user
from app.models.domain import User

from app.models.schemas import (
    FontFamilyResponse,
    FontInstallResponse,
    FontOptionResponse,
    ImageInfo,
    ImageRepositionRequest,
    Rect,
    TextBlock,
    WatermarkRequest, TextEditRequest, PageNumberRequest, BarcodeRequest, BarcodeInsertRequest,
)
from app.services import edit_service, font_url, fonts
from app.core.security import make_resource_token, verify_resource_token
from urllib.parse import quote
from app.services.pdf_service import PDFError

router = APIRouter(prefix="/edit", tags=["edit"])




_FONT_SCOPE = "font-file"


def _font_file_url(key: str, user_id: int, removable: bool) -> str:
    url = f"/api/edit/fonts/{quote(key)}/file"
    # ฟอนต์ที่ติดตั้งเองเป็นของผู้ใช้คนนั้นเท่านั้น — แนบ token ของเจ้าของ (browser ส่ง header ใน @font-face ไม่ได้)
    return f"{url}?t={make_resource_token(_FONT_SCOPE, user_id)}" if removable else url


def _font_options_response(user_id: int) -> list[FontOptionResponse]:
    options = []
    for f in fonts.get_font_options(user_id):
        removable = fonts.is_removable(f.key, user_id)
        options.append(FontOptionResponse(
            key=f.key, label=f.label, removable=removable, file_url=_font_file_url(f.key, user_id, removable),
        ))
    return options


@router.get("/fonts", response_model=list[FontOptionResponse])
def list_fonts(current_user: User = Depends(get_current_active_user)):
    """รายชื่อ font แบบ flat ที่ frontend ใช้ทำ dropdown..."""
    return _font_options_response(current_user.id)


@router.get("/font-families", response_model=list[FontFamilyResponse])
def list_font_families(current_user: User = Depends(get_current_active_user)):
    """รายชื่อ font จัดกลุ่มเป็น family..."""
    return [FontFamilyResponse(**f) for f in fonts.list_font_families(current_user.id)]


@router.post("/fonts/install", response_model=FontInstallResponse)
async def install_font(
    file: UploadFile = File(...),
    label: str | None = Form(None),
    family_key: str | None = Form(None),
    style: str = Form("regular"),
    current_user: User = Depends(get_current_active_user)
):
    """ติดตั้งฟอนต์ใหม่ (.ttf/.otf/.woff/.woff2) — ดู fonts.install_custom_font"""
    file_bytes = await file.read(fonts.MAX_FONT_FILE_BYTES + 1)
    try:
        opt = fonts.install_custom_font(
            file_bytes, file.filename or "font", label, current_user.id, family_key=family_key, style=style
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FontInstallResponse(
        installed=FontOptionResponse(
            key=opt.key, label=opt.label, removable=True, file_url=_font_file_url(opt.key, current_user.id, True),
        ),
        fonts=_font_options_response(current_user.id),
        warnings=_font_warnings(getattr(opt, "info", None)),
    )


def _font_warnings(info) -> list[str]:
    out = []
    if info is not None and not info.has_thai:
        out.append("ฟอนต์นี้ไม่มีตัวอักษรไทย — ใช้ได้กับข้อความภาษาอังกฤษ/ตัวเลขเท่านั้น")
    if info is not None and info.restricted:
        out.append("ผู้ออกแบบฟอนต์นี้ตั้งค่าห้ามฝังลงในเอกสาร — ตรวจสิทธิ์การใช้งาน (license) ก่อนใช้กับเอกสารที่ส่งต่อให้ผู้อื่น")
    return out


class FontUrlRequest(BaseModel):
    url: str = Field(max_length=2000)


class FontUrlInstallRequest(BaseModel):
    token: str = Field(max_length=64)
    label: Optional[str] = Field(default=None, max_length=80)


@router.post("/fonts/url/preview")
def preview_font_url(payload: FontUrlRequest, current_user: User = Depends(get_current_active_user)):
    """ติดตั้งฟอนต์จากลิงก์ ขั้น 1: ตรวจลิงก์ (Google Fonts + https เท่านั้น) ดาวน์โหลดเก็บชั่วคราว 30 นาที
    แล้วคืนข้อมูลให้หน้าจอแสดงตัวอย่าง — ดู services/font_url.py"""
    try:
        data = font_url.create_preview(payload.url, current_user.id)
    except font_url.FontUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    data["styles"] = [{**s, "file_url": f"/api/edit/fonts/url/preview/{data['token']}/{s['style']}"} for s in data["styles"]]
    return data


@router.get("/fonts/url/preview/{token}/{style}")
def preview_font_url_file(token: str, style: str):
    """ไฟล์ฟอนต์ชั่วคราวสำหรับ @font-face ตัวอย่าง — token สุ่ม 128 บิตจากขั้นตรวจลิงก์เป็นสิทธิ์ (หมดอายุ 30 นาที)"""
    try:
        data = font_url.preview_font_file(token, style)
    except font_url.FontUrlError:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ฟอนต์")
    return Response(content=data, media_type="font/ttf", headers={"Cache-Control": "private, max-age=1800"})


@router.post("/fonts/url/install", response_model=FontInstallResponse)
def install_font_url(payload: FontUrlInstallRequest, current_user: User = Depends(get_current_active_user)):
    """ติดตั้งฟอนต์จากลิงก์ ขั้น 2: ติดตั้งทุกสไตล์ที่ตรวจไว้เป็น family เดียว"""
    try:
        opt = font_url.install_preview(payload.token, current_user.id, payload.label)
    except (font_url.FontUrlError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FontInstallResponse(
        installed=FontOptionResponse(key=opt.key, label=opt.label, removable=True,
                                     file_url=_font_file_url(opt.key, current_user.id, True)),
        fonts=_font_options_response(current_user.id),
    )


@router.get("/fonts/{key}/file")
def get_font_file(key: str, t: str | None = None):
    """คืนไบต์ไฟล์ font จริง (.ttf/.otf) ให้ frontend ใช้ประกาศ @font-face

    ไม่ใช้ Authorization header เพราะ browser ส่ง header ใน @font-face src: url() ไม่ได้
    - ฟอนต์ที่มากับระบบ/Google Fonts: เปิดสาธารณะ
    - ฟอนต์ที่ผู้ใช้ติดตั้งเอง: ต้องมี token ของเจ้าของ (?t=... ได้จาก file_url ใน GET /edit/fonts)
      เดิมรับ ?user_id= ตรงๆ ใครเดา user id ได้ก็ดาวน์โหลดฟอนต์ (ที่อาจซื้อลิขสิทธิ์มา) ของคนอื่นได้
    """
    user_id = verify_resource_token(_FONT_SCOPE, t)
    if not fonts.is_global_font(key) and user_id is None:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ฟอนต์นี้บนเซิร์ฟเวอร์")
    resolved_key, path = fonts.resolve_font_path(key, user_id=user_id)
    if not path:
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์ฟอนต์นี้บนเซิร์ฟเวอร์")
    data = Path(path).read_bytes()
    media_type = "font/otf" if Path(path).suffix.lower() == ".otf" else "font/ttf"
    # ฟอนต์ส่วนตัว: cache เฉพาะในเบราว์เซอร์ของเจ้าของ (private) ไม่ให้ proxy/CDN เก็บ
    cache = "private, max-age=86400" if user_id is not None else "public, max-age=86400"
    return Response(content=data, media_type=media_type, headers={"Cache-Control": cache})


@router.delete("/fonts/{family_key}", response_model=list[FontOptionResponse])
def remove_font(family_key: str, current_user: User = Depends(get_current_active_user)):
    """ลบฟอนต์ที่เคยติดตั้งเองทั้ง family..."""
    try:
        fonts.remove_custom_font_family(family_key, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _font_options_response(current_user.id)


# ---------- Text ----------

@router.get("/{session_id}/page/{page_number}/text-blocks", response_model=list[TextBlock])
def get_text_blocks(session_id: str, page_number: int, session: PDFSession = Depends(get_owned_session)):
    """คืนรายการ span ข้อความทั้งหมดในหน้า พร้อม bbox/font เดิม
    ให้ frontend วาดเป็นกล่องคลิกเลือกทับ preview เพื่อเลือกช่วงที่จะแก้ (รวมถึงย่อหน้าที่เคยถูกแก้ไป
    แล้วก่อนหน้านี้ในเซสชันนี้ด้วย — ดู session.text_edits / edit_service หมายเหตุ "แก้บั๊กสำคัญ #6"
    เพื่อให้ยังคลิกกลับมาแก้ไขซ้ำได้เรื่อยๆ ไม่ใช่แก้ได้แค่ครั้งเดียว)"""
    try:
        with session.lock:
            return edit_service.get_text_blocks(session, page_number)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/text")
def edit_text(session_id: str, payload: TextEditRequest, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            edit_service.replace_text(
                session,
                payload.page_number,
                payload.rect,
                payload.new_text,
                payload.fontsize,
                payload.fontname,
                payload.color,
                block_id=payload.block_id,
                previous_rect=payload.previous_rect,
                align=payload.align,
                valign=payload.valign,
                underline=payload.underline,
            )
            session.push_history()  # ดู app/core/session.py หมายเหตุ Undo/Redo
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


# ---------- Image ----------

@router.get("/{session_id}/page/{page_number}/images", response_model=list[ImageInfo])
def get_images(session_id: str, page_number: int, session: PDFSession = Depends(get_owned_session)):
    try:
        with session.lock:
            return edit_service.get_images(session, page_number)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{session_id}/page/{page_number}/image/{xref}/raw")
def get_image_raw(session_id: str, page_number: int, xref: int, session: PDFSession = Depends(get_owned_session)):
    """คืนไบต์ดิบของรูปภาพ (ตาม xref) ให้ frontend ใช้เป็น src ของ <img> ตรงๆ เพื่อโชว์พรีวิวจริง
    ตอนลากย้าย/ปรับขนาดกล่องรูปภาพ ก่อนกดบันทึกจริง (ดู edit_service.get_image_bytes)"""
    try:
        with session.lock:
            image_bytes, ext = edit_service.get_image_bytes(session, page_number, xref)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=image_bytes, media_type=f"image/{ext}")


@router.post("/{session_id}/page/{page_number}/image")
async def insert_image(session_id: str, page_number: int, x0: float = Form(...), y0: float = Form(...), x1: float = Form(...), y1: float = Form(...), file: UploadFile = File(...), session: PDFSession = Depends(get_owned_session)):
    """แทรกรูปภาพใหม่เข้าไปในหน้า (ปุ่ม Insert Image) — ต่างจาก /image/{xref} ด้านล่างซึ่งเป็นการ
    "แทนที่" รูปที่มีอยู่แล้ว (ดู edit_service.insert_image หมายเหตุ "แก้บั๊กสำคัญ #7")"""
    new_bytes = await file.read()
    try:
        with session.lock:
            edit_service.insert_image(session, page_number, Rect(x0=x0, y0=y0, x1=x1, y1=y1), new_bytes)
            session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.delete("/{session_id}/page/{page_number}/image/{xref}")
def delete_image(
    session_id: str,
    page_number: int,
    xref: int,
    x0: Optional[float] = None,
    y0: Optional[float] = None,
    x1: Optional[float] = None,
    y1: Optional[float] = None, session: PDFSession = Depends(get_owned_session),
):
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1) if (x0 is not None and y0 is not None and x1 is not None and y1 is not None) else None
    try:
        with session.lock:
            edit_service.delete_image(session, page_number, xref, rect=rect)
            session.push_history()
        return {"status": "ok"}
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/page/{page_number}/image/{xref}")
async def replace_image(session_id: str, page_number: int, xref: int, file: UploadFile = File(...), session: PDFSession = Depends(get_owned_session)):
    new_bytes = await file.read()
    try:
        with session.lock:
            edit_service.replace_image(session, page_number, xref, new_bytes)
            session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.post("/{session_id}/page/{page_number}/image/{xref}/reposition")
def reposition_image(session_id: str, page_number: int, xref: int, payload: ImageRepositionRequest, session: PDFSession = Depends(get_owned_session)):
    """ย้าย/ปรับขนาดรูปภาพที่มีอยู่แล้วด้วยเมาส์ (ดู edit_service.reposition_image หมายเหตุ
    "แก้บั๊กสำคัญ #7") — คนละ endpoint กับ replace_image ด้านบน (อันนั้นเปลี่ยนเนื้อรูป ไม่ย้ายตำแหน่ง)"""
    try:
        with session.lock:
            edit_service.reposition_image(session, page_number, xref, payload.old_rect, payload.new_rect)
            session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}

@router.post("/{session_id}/watermark")
def apply_watermark(session_id: str, payload: WatermarkRequest, session: PDFSession = Depends(get_owned_session)):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="กรุณากรอกข้อความลายน้ำ")
    try:
        with session.lock:  # เดิมแก้เอกสารนอก lock — คำขออื่นของ session เดียวกันแทรกกลางได้
            edit_service.apply_watermark(
                session,
                text=payload.text,
                opacity=payload.opacity,
                angle=payload.angle,
                color=payload.color,
                font_size=payload.font_size
            )
            session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.post("/{session_id}/page-numbers")
def apply_page_numbers(session_id: str, payload: PageNumberRequest, session: PDFSession = Depends(get_owned_session)):
    """ใส่เลขหน้า — ข้อความจริงในไฟล์ (ดู edit_service/page_numbers.py) · undo ได้"""
    try:
        with session.lock:
            count = edit_service.apply_page_numbers(session, payload.to_options())
            session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok", "count": count}


# ---------- บาร์โค้ด (เมนูแทรก › บาร์โค้ด) ----------

@router.get("/barcode/types")
def barcode_types(current_user: User = Depends(get_current_active_user)):
    from app.services import barcode_service
    return [{"key": t.key, "label": t.label, "two_d": t.two_d, "unicode": t.unicode, "hint": t.hint}
            for t in barcode_service.TYPES.values()]


@router.post("/barcode/preview")
def barcode_preview(payload: BarcodeRequest, current_user: User = Depends(get_current_active_user)):
    """ตรวจข้อมูล + ภาพตัวอย่าง PNG (หน้าต่างตั้งค่า และกล่องลากวางบนหน้า) — ข้อมูลไม่ถูกต้อง → 400 พร้อมเหตุผล
    header X-Barcode-Data = ข้อมูลหลังปรับ (เช่น เติมเลขตรวจสอบ EAN) แบบ percent-encoded"""
    from app.services import barcode_service
    try:
        spec = barcode_service.validate(payload.to_spec())
        png = barcode_service.render_png(spec)
    except barcode_service.BarcodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=png, media_type="image/png",
                    headers={"X-Barcode-Data": quote(spec.data), "Cache-Control": "no-store"})


@router.post("/{session_id}/page/{page_number}/barcode")
def insert_barcode(session_id: str, page_number: int, payload: BarcodeInsertRequest,
                   session: PDFSession = Depends(get_owned_session)):
    """วางบาร์โค้ดแบบเวกเตอร์ลงกรอบที่ผู้ใช้ลาก (คมทุกขนาด) · undo ได้"""
    import fitz

    from app.services import barcode_service
    from app.services.pdf_service import require_unlocked
    try:
        spec = barcode_service.validate(payload.to_spec())
        with session.lock:
            doc = require_unlocked(session)
            if not (0 <= page_number < doc.page_count):
                raise PDFError(f"page_number {page_number} อยู่นอกช่วง")
            rect = fitz.Rect(payload.x0, payload.y0, payload.x1, payload.y1).normalize()
            if rect.width < 5 or rect.height < 5:
                raise PDFError("บาร์โค้ดเล็กเกินไป — ลากกรอบให้ใหญ่ขึ้น")
            page = doc[page_number]
            barcode_service.insert_into_page(page, rect, spec)  # พิกัดเดียวกับการแทรกรูป (edit_service.insert_image)
            session.mark_dirty()
            session.push_history()
    except barcode_service.BarcodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}
