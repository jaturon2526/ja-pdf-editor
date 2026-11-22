"""
routes_signature — เมนู "Digital Signature" (ผู้ใช้แจ้งขอ): Electronic Sign และ Digital Sign

Electronic Sign ส่งมาเป็น JSON ธรรมดา (รูปลายเซ็นเรนเดอร์เป็น PNG base64 ฝั่ง frontend เสร็จแล้ว
ไม่มีไฟล์แนบ) ส่วน Digital Sign ต้องแนบไฟล์ p12/pfx จริง จึงรับเป็น multipart/form-data (UploadFile +
Form fields) เหมือน pattern เดียวกับ /edit/{session_id}/page/{page_number}/image ใน routes_edit.py
(ส่ง rect เป็น x0/y0/x1/y1 แยกฟิลด์ ไม่ใช่ JSON ซ้อนใน form field เพื่อความง่ายฝั่ง frontend)

ทั้งสอง endpoint ตั้ง session.is_signed = True ทันทีที่เซ็นสำเร็จ แล้ว push_history() เหมือนการแก้ไข
ชนิดอื่นๆ ทุกประการ — is_signed เป็นแค่สถานะโชว์ผล ไม่ได้ล็อกเอกสารอีกต่อไป (ผู้ใช้แจ้งขอ: แก้ไข/ย้าย
ตำแหน่งลายเซ็น/เซ็นซ้อนต่อได้ตามปกติหลังเซ็นแล้ว ดู app/services/signature_service.py และ
app/core/session.py สำหรับรายละเอียด)

หมายเหตุสำคัญเรื่อง /digital (พบจากการทดสอบจริง ไม่ใช่แค่เดา): pyhanko.sign.signers.PdfSigner.sign_pdf()
เรียก asyncio.run(...) ภายในตัวเอง (เพื่อรองรับการเซ็นแบบ async ด้วยเหตุผลอื่นของไลบรารี) ซึ่งจะ raise
RuntimeError ทันทีถ้าถูกเรียกจาก thread ที่มี event loop กำลังรันอยู่แล้ว — endpoint นี้เป็น `async def`
(จำเป็นต้องใช้ `await file.read()`) จึงรันอยู่ใน event loop thread ของ FastAPI/Starlette เอง ถ้าเรียก
signature_service.apply_digital_signature() ตรงๆ จาก endpoint นี้จะชนกันทันที (ทดสอบแล้วเจอ error
"asyncio.run() cannot be called from a running event loop" จริง) ทางแก้: ย้ายส่วนที่ล็อก
session.lock + เรียก apply_digital_signature() + push_history() ทั้งหมดไปรันใน thread แยกด้วย
asyncio.to_thread() แทน (thread นั้นไม่มี event loop ของตัวเอง ทำให้ pyHanko เรียก asyncio.run()
ได้ตามปกติ) — เป็นผลพลอยได้ที่ดีด้วยเพราะการเซ็นจริงอาจใช้เวลาสักครู่ ไม่ควรบล็อก event loop หลักอยู่แล้ว
"""
from __future__ import annotations

import asyncio
import base64
import binascii

from app.api.deps import get_current_active_user, get_owned_session
from app.db.database import get_db
from app.models.domain import User
from app.core.session import PDFSession
from fastapi import Body, Depends, APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.schemas import ElectronicSignRequest, Rect, SignatureStatusResponse
from app.services import certificate_store, signature_service, signature_store
from app.services.pdf_service import PDFError

router = APIRouter(prefix="/signature", tags=["signature"])




_MAX_UPLOAD = 5 * 1024 * 1024


def _checked_image(data: bytes) -> bytes:
    """รูปลายมือชื่อต้องเป็นรูปจริงและไม่ว่าง (เดิมรูปเสียถูกข้ามเงียบๆ) — ดู signing_pdf.normalize_signature_image"""
    from app.services import signing_pdf

    try:
        return signing_pdf.normalize_signature_image(data)
    except signing_pdf.SigningPdfError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/{session_id}/electronic", response_model=SignatureStatusResponse)
def electronic_sign(session_id: str, payload: ElectronicSignRequest, session: PDFSession = Depends(get_owned_session)):
    """Electronic Sign — แปะรูปลายเซ็น (พิมพ์ข้อความ/อัปโหลดรูป/วาดลายมือ — frontend เรนเดอร์เป็น PNG
    base64 มาให้แล้ว) ลงตำแหน่ง/ขนาดที่ผู้ใช้ลากเลือก ดู signature_service.apply_electronic_signature"""
    try:
        image_bytes = base64.b64decode(payload.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="ข้อมูลรูปลายเซ็น (image_base64) ไม่ถูกต้อง")
    image_bytes = _checked_image(image_bytes)

    try:
        with session.lock:
            signature_service.apply_electronic_signature(session, payload.page_number, payload.rect, image_bytes)
            session.push_history()
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return SignatureStatusResponse(status="ok", is_signed=True, signature_type="electronic")


# ---------- ใบรับรองที่เก็บไว้บนระบบ (app/services/certificate_store.py) ----------

def _cert_http(exc: certificate_store.CertificateError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _pfx_from(file: UploadFile | None, certificate_id: int | None, password: str,
                    user: User, db: Session) -> bytes:
    """ไบต์ p12 จากไฟล์ที่แนบมา หรือจากใบรับรองที่เก็บไว้ (ตรวจรหัส + นับครั้งผิด) — ต้องมีอย่างใดอย่างหนึ่ง"""
    if certificate_id is not None:
        try:
            return await asyncio.to_thread(certificate_store.unlock, db, user, certificate_id, password)
        except certificate_store.CertificateError as exc:
            raise _cert_http(exc)
    if file is None:
        raise HTTPException(status_code=400, detail="เลือกไฟล์ใบรับรอง หรือใบรับรองที่บันทึกไว้")
    pfx_bytes = await file.read(_MAX_UPLOAD + 1)
    if len(pfx_bytes) > _MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="ไฟล์ใบรับรองใหญ่เกินไป (สูงสุด 5 MB)")
    return pfx_bytes


@router.get("/certificates")
def list_certificates(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """ใบรับรองที่เก็บไว้ (ไม่มีไฟล์/กุญแจในคำตอบ)"""
    return certificate_store.list_for(db, current_user)


@router.post("/certificates", status_code=201)
async def upload_certificate(password: str = Form(...), file: UploadFile = File(...), label: str | None = Form(None),
                             current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """เก็บใบรับรอง — ตรวจรหัสครั้งแรกก่อนเก็บ (รหัสไม่ถูกบันทึก)"""
    pfx_bytes = await file.read(certificate_store.MAX_FILE_BYTES + 1)
    try:
        return await asyncio.to_thread(certificate_store.add, db, current_user, pfx_bytes, password, label)
    except certificate_store.CertificateError as exc:
        raise _cert_http(exc)


@router.post("/certificates/{certificate_id}/delete", status_code=204)
async def delete_certificate(certificate_id: int, password: str = Body(..., embed=True),
                             current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """ลบใบรับรองที่เก็บไว้ — ต้องยืนยันรหัสของใบรับรองก่อน"""
    try:
        await asyncio.to_thread(certificate_store.delete, db, current_user, certificate_id, password)
    except certificate_store.CertificateError as exc:
        raise _cert_http(exc)


@router.post("/certificates/{certificate_id}/passkeys/options")
def certificate_passkey_options(certificate_id: int, current_user: User = Depends(get_current_active_user),
                                db: Session = Depends(get_db)):
    """challenge สำหรับผูก passkey กับใบรับรอง (ขอไว้ก่อนกดปุ่ม — Safari ต้องเรียก WebAuthn ทันทีจากการกด)"""
    try:
        return certificate_store.passkey_options(db, current_user, certificate_id)
    except certificate_store.CertificateError as exc:
        raise _cert_http(exc)


@router.post("/certificates/{certificate_id}/passkeys", status_code=201)
async def bind_certificate_passkey(certificate_id: int, payload: dict = Body(...),
                                   current_user: User = Depends(get_current_active_user),
                                   db: Session = Depends(get_db)):
    """ผูก passkey: {flow_id, credential, password, prf_salt, wrapped} — wrapped เข้ารหัสในเบราว์เซอร์ด้วยค่าจาก passkey"""
    credential = payload.get("credential")
    if not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="ข้อมูล passkey ไม่ถูกต้อง")
    try:
        return await asyncio.to_thread(
            certificate_store.bind_passkey, db, current_user, certificate_id,
            password=str(payload.get("password") or ""), flow_id=str(payload.get("flow_id") or ""),
            credential=credential, prf_salt=str(payload.get("prf_salt") or ""), wrapped=str(payload.get("wrapped") or ""),
        )
    except certificate_store.CertificateError as exc:
        raise _cert_http(exc)


@router.delete("/certificates/{certificate_id}/passkeys/{binding_id}")
def unbind_certificate_passkey(certificate_id: int, binding_id: int,
                               current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    try:
        return certificate_store.unbind_passkey(db, current_user, certificate_id, binding_id)
    except certificate_store.CertificateError as exc:
        raise _cert_http(exc)


# ---------- รูปลายเซ็นที่บันทึกไว้และปลดล็อกด้วย Passkey (v1.48.0 — app/services/signature_store.py) ----------

def _sig_store_http(exc: signature_store.SignatureStoreError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/saved")
def list_saved_signatures(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """รายการรูปลายเซ็นที่บันทึกไว้ (เฉพาะ metadata — ไม่ส่งข้อมูลรูปจนกว่าจะกดปลดล็อก)"""
    return signature_store.list_for(db, current_user)


@router.get("/saved/{sig_id}/blob")
def get_saved_signature_blob(sig_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """คืน ciphertext ของรูปลายเซ็น (เข้ารหัสด้วย AES-GCM จาก Passkey PRF — ต้องปลดล็อกในเบราว์เซอร์)"""
    try:
        return signature_store.get_blob(db, current_user, sig_id)
    except signature_store.SignatureStoreError as exc:
        raise _sig_store_http(exc)


@router.post("/saved/options")
def saved_signature_options(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """challenge สำหรับยืนยันตัวตนด้วย Passkey ก่อนบันทึกรูปลายเซ็น (ขอไว้ก่อนกดปุ่ม — รองรับ Safari)"""
    try:
        return signature_store.save_options(db, current_user)
    except signature_store.SignatureStoreError as exc:
        raise _sig_store_http(exc)


@router.post("/saved", status_code=201)
def create_saved_signature(payload: dict = Body(...), current_user: User = Depends(get_current_active_user),
                           db: Session = Depends(get_db)):
    """บันทึกรูปลายเซ็นที่เข้ารหัสแล้วจากเบราว์เซอร์: {label, prf_salt, encrypted_png_b64, flow_id, credential}"""
    credential = payload.get("credential")
    if not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="ข้อมูล passkey ไม่ถูกต้อง")
    try:
        return signature_store.add(
            db,
            current_user,
            label=str(payload.get("label") or ""),
            prf_salt=str(payload.get("prf_salt") or ""),
            encrypted_png_b64=str(payload.get("encrypted_png_b64") or ""),
            flow_id=str(payload.get("flow_id") or ""),
            credential=credential,
        )
    except signature_store.SignatureStoreError as exc:
        raise _sig_store_http(exc)


@router.delete("/saved/{sig_id}", status_code=204)
def delete_saved_signature(sig_id: int, current_user: User = Depends(get_current_active_user),
                           db: Session = Depends(get_db)):
    try:
        signature_store.delete(db, current_user, sig_id)
    except signature_store.SignatureStoreError as exc:
        raise _sig_store_http(exc)


@router.post("/check-certificate")
async def check_certificate(password: str = Form(...), file: UploadFile | None = File(None),
                            certificate_id: int | None = Form(None),
                            current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """ตรวจไฟล์ใบรับรอง (หรือใบที่เก็บไว้) + รหัสผ่านตั้งแต่หน้าต่างเลือกใบรับรอง (ก่อนวางตำแหน่ง)
    — คืนชื่อผู้เซ็น/วันหมดอายุ/คำเตือน"""
    pfx_bytes = await _pfx_from(file, certificate_id, password, current_user, db)
    try:
        _signer, info = await asyncio.to_thread(signature_service.load_signer, pfx_bytes, password)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return info


@router.post("/{session_id}/digital", response_model=SignatureStatusResponse)
async def digital_sign(
    session_id: str,
    page_number: int = Form(...),
    x0: float = Form(...),
    y0: float = Form(...),
    x1: float = Form(...),
    y1: float = Form(...),
    password: str = Form(...),
    reason: str | None = Form(None),
    location: str | None = Form(None),
    contact: str | None = Form(None),
    name: str | None = Form(None),
    file: UploadFile | None = File(None),
    certificate_id: int | None = Form(None),
    signature_image: UploadFile = File(None), session: PDFSession = Depends(get_owned_session),
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
):
    """Digital Sign — เซ็นด้วยลายเซ็นดิจิทัลแบบเข้ารหัสจริง (PAdES) จากไฟล์ p12/pfx ที่ผู้ใช้อัปโหลด
    หรือใบรับรองที่เก็บไว้บนระบบ (certificate_id + รหัสผ่าน)
    ดู signature_service.apply_digital_signature สำหรับรายละเอียดการเซ็น/รักษาไบต์ลายเซ็นให้ไม่เสียหาย"""
    pfx_bytes = await _pfx_from(file, certificate_id, password, current_user, db)
    image_bytes = await signature_image.read(_MAX_UPLOAD + 1) if signature_image else None
    if image_bytes is not None and len(image_bytes) > _MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="รูปลายเซ็นใหญ่เกินไป (สูงสุด 5 MB)")
    image_bytes = _checked_image(image_bytes) if image_bytes else None
    rect = Rect(x0=x0, y0=y0, x1=x1, y1=y1)

    def _sign_in_thread() -> str:
        # รันใน thread แยก (ไม่มี event loop ของตัวเอง) — ดูหมายเหตุหัวไฟล์ว่าทำไมจำเป็น (pyHanko
        # เรียก asyncio.run() ภายในตัวเอง ชนกับ event loop ของ FastAPI ถ้าเรียกตรงๆ จาก endpoint นี้)
        with session.lock:
            signer_name = signature_service.apply_digital_signature(
                session,
                page_number,
                rect,
                pfx_bytes,
                password,
                reason=reason,
                location=location,
                contact=contact,
                name=name,
                image_bytes=image_bytes,
            )
            session.push_history()
            return signer_name

    try:
        signer_name = await asyncio.to_thread(_sign_in_thread)
    except PDFError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return SignatureStatusResponse(status="ok", is_signed=True, signature_type="digital", signer_name=signer_name)
