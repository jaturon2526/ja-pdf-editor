"""pdf_service.properties — คุณสมบัติเอกสาร (Document Properties) รวมข้อมูลลายเซ็นดิจิทัล/ใบรับรอง"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
import pikepdf
from app.core.session import PDFSession
from app.services.pdf_service.core import get_encryption_state, require_unlocked

import logging

logger = logging.getLogger("pdf_service")


_TRUST_CONTEXT = None


def _get_trust_context():
    global _TRUST_CONTEXT
    if _TRUST_CONTEXT is not None:
        return _TRUST_CONTEXT
    try:
        import certifi
        import re
        from pathlib import Path
        from asn1crypto.pem import unarmor
        from asn1crypto.x509 import Certificate
        from pyhanko_certvalidator.context import ValidationContext
        
        certs = []
        
        # 1. Load Standard Global Roots (Mozilla Bundle via certifi)
        with open(certifi.where(), "rb") as f:
            pem_data = f.read()
        for match in re.finditer(b"(?s)-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", pem_data):
            type_name, headers, der_bytes = unarmor(match.group(0))
            if type_name == "CERTIFICATE":
                certs.append(Certificate.load(der_bytes))
                
        # 2. Load Custom Local Roots (e.g. Thai CAs) from /data/trusted_certs
        custom_certs_dir = Path("/data/trusted_certs")
        if custom_certs_dir.exists():
            for cert_file in custom_certs_dir.glob("*.pem"):
                with open(cert_file, "rb") as f:
                    custom_pem = f.read()
                for match in re.finditer(b"(?s)-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", custom_pem):
                    type_name, headers, der_bytes = unarmor(match.group(0))
                    if type_name == "CERTIFICATE":
                        certs.append(Certificate.load(der_bytes))
                        
        _TRUST_CONTEXT = ValidationContext(trust_roots=certs)
    except Exception as e:
        logger.warning(f"Failed to load certifi roots: {e}")
        _TRUST_CONTEXT = False
    return _TRUST_CONTEXT if _TRUST_CONTEXT is not False else None


# ขนาดกระดาษมาตรฐานที่รู้จัก (หน่วย point, 72pt = 1 นิ้ว) ใช้ทาย label ให้เหมือน Acrobat (เช่น "A4",
# "Letter") เทียบทั้งแนวตั้ง/แนวนอน ด้วย tolerance ±2pt (กันปัดเศษเพี้ยนนิดหน่อยจากโปรแกรมสร้าง PDF)
_STANDARD_PAGE_SIZES_PT = [
    ("A4", 595.0, 842.0),
    ("Letter", 612.0, 792.0),
    ("Legal", 612.0, 1008.0),
    ("A3", 842.0, 1191.0),
    ("A5", 420.0, 595.0),
    ("Tabloid", 792.0, 1224.0),
    ("B5", 499.0, 709.0),
]


def _parse_pdf_date(raw: str | None) -> str | None:
    """แปลงวันที่แบบ PDF ("D:20230115143000+07'00'") เป็นข้อความอ่านง่าย (dd/mm/yyyy HH:MM) — ฟิลด์นี้
    เป็น optional ตามสเปก PDF (ไฟล์จำนวนมากไม่ใส่ หรือใส่รูปแบบเพี้ยนไปจากสเปก) parse ไม่ได้ก็คืนค่าดิบ
    กลับไปแทน (ดีกว่าซ่อนข้อมูลที่มีอยู่จริงไปเฉยๆ)"""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("D:"):
        s = s[2:]
    core = s[:14]
    try:
        return datetime.strptime(core, "%Y%m%d%H%M%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        pass
    try:
        return datetime.strptime(core[:8], "%Y%m%d").strftime("%d/%m/%Y")
    except ValueError:
        return raw


def _format_file_size(num_bytes: int) -> str:
    size = float(num_bytes)
    units = ["bytes", "KB", "MB", "GB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.2f} {units[idx]}"


def _detect_page_size_label(width_pt: float, height_pt: float) -> str | None:
    for name, w, h in _STANDARD_PAGE_SIZES_PT:
        if (abs(width_pt - w) <= 2 and abs(height_pt - h) <= 2) or (
            abs(width_pt - h) <= 2 and abs(height_pt - w) <= 2
        ):
            return name
    return None


def _first_name_value(native: dict, key: str) -> str | None:
    """ค่าแรกของฟิลด์ใน X.509 Name.native (บางฟิลด์อาจเป็น list ถ้ามีหลายค่า)"""
    value = native.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return str(value) if value else None


def _format_fingerprint(digest: bytes) -> str:
    """AA:BB:CC:... (ตัวพิมพ์ใหญ่ คั่นด้วย ':') แบบเดียวกับที่ Acrobat/openssl แสดง"""
    return ":".join(f"{b:02X}" for b in digest)


def _extract_cert_details(cert) -> dict:
    """แปลง asn1crypto x509.Certificate ของผู้เซ็นเป็น dict ที่ frontend แสดงได้ตรง ๆ
    ทุกฟิลด์เป็น None ได้ถ้า certificate ไม่มีข้อมูลนั้น — ไม่ throw (อ่านพลาดทีละฟิลด์ถือเป็น 'ไม่ทราบ')"""
    details: dict = {}

    try:
        subject_native = cert.subject.native
        issuer_native = cert.issuer.native
        details.update({
            "cert_subject": cert.subject.human_friendly,
            "cert_issuer": cert.issuer.human_friendly,
            "cert_subject_cn": _first_name_value(subject_native, "common_name"),
            "cert_subject_org": _first_name_value(subject_native, "organization_name"),
            "cert_subject_email": _first_name_value(subject_native, "email_address"),
            "cert_issuer_cn": _first_name_value(issuer_native, "common_name"),
            "cert_issuer_org": _first_name_value(issuer_native, "organization_name"),
        })
    except Exception:
        logger.warning("_extract_cert_details: อ่านชื่อ subject/issuer ไม่สำเร็จ", exc_info=True)

    try:
        details["cert_serial"] = format(cert.serial_number, "X")
    except Exception:
        logger.warning("_extract_cert_details: อ่าน serial ไม่สำเร็จ", exc_info=True)

    try:
        not_before = cert.not_valid_before
        not_after = cert.not_valid_after
        details["cert_valid_from"] = not_before.isoformat() if not_before else None
        details["cert_valid_to"] = not_after.isoformat() if not_after else None
        if not_after:
            remaining = not_after - datetime.now(timezone.utc)
            details["cert_expired"] = remaining.total_seconds() < 0
            details["cert_days_remaining"] = remaining.days
    except Exception:
        logger.warning("_extract_cert_details: อ่านวันที่ cert ไม่สำเร็จ", exc_info=True)

    try:
        der = cert.dump()
        details["cert_sha256"] = _format_fingerprint(hashlib.sha256(der).digest())
        details["cert_sha1"] = _format_fingerprint(hashlib.sha1(der).digest())  # nosec B324 - แสดงผลเท่านั้น ไม่ใช้เพื่อความปลอดภัย
    except Exception:
        logger.warning("_extract_cert_details: คำนวณ fingerprint ไม่สำเร็จ", exc_info=True)

    try:
        sig_algo_labels = {"rsassa_pkcs1v15": "RSA", "rsassa_pss": "RSA-PSS", "ecdsa": "ECDSA", "ed25519": "Ed25519"}
        sig_algo = sig_algo_labels.get(cert.signature_algo, cert.signature_algo.upper())
        details["cert_signature_algorithm"] = f"{cert.hash_algo.upper()} with {sig_algo}"
        public_key = cert.public_key
        details["cert_key_info"] = f"{public_key.algorithm.upper()} {public_key.bit_size} bit"
        # asn1crypto คืน 'yes' | 'no' | 'maybe' ('maybe' เกิดเมื่อ cert ไม่มี key identifier) —
        # self-signed/self-issued คือ subject == issuer
        details["cert_self_signed"] = cert.self_signed == "yes" or cert.subject == cert.issuer
    except Exception:
        logger.warning("_extract_cert_details: อ่านอัลกอริทึม/คีย์ไม่สำเร็จ", exc_info=True)

    return details


def get_document_properties(session: PDFSession) -> dict:
    """รวบรวมคุณสมบัติเอกสาร (Document Properties) แบบเดียวกับที่ Acrobat Reader โชว์ เท่าที่
    PyMuPDF/pikepdf ทำได้ (ผู้ใช้แจ้งขอ — บอกให้ทำเท่าที่ทำได้ถ้ามีข้อจำกัด): metadata มาตรฐาน (title/
    author/...) จาก fitz.Document.metadata ตรงๆ, ขนาดไฟล์คำนวณจาก doc.tobytes() ปัจจุบัน (สะท้อนการ
    แก้ไขที่ทำในเซสชันนี้แล้ว ไม่ใช่ขนาดไฟล์ตอน upload ครั้งแรกซึ่งอาจเก่าไปแล้ว) ส่วน Tagged PDF/Fast Web
    View ต้องพึ่ง pikepdf (fitz ไม่มี API ตรงให้) เปิดจากไบต์เดียวกันนั้นเลยเพื่อความสอดคล้องกัน — ถ้าตรวจ
    ไม่ได้ (ไฟล์แปลก/pikepdf เปิดไม่ได้) คืน None ให้ frontend แสดง "ไม่ทราบ" แทนที่จะทำให้ endpoint นี้
    error ทั้งหมด (ฟิลด์อื่นที่ตรวจได้ปกติควรยังเห็นอยู่)
    """
    doc = require_unlocked(session)
    meta = doc.metadata or {}

    raw_bytes = doc.tobytes()
    file_size_bytes = len(raw_bytes)

    page_count = doc.page_count
    width_pt, height_pt = (0.0, 0.0)
    if page_count > 0:
        rect = doc[0].rect
        width_pt, height_pt = rect.width, rect.height

    page_size_display = None
    if page_count > 0:
        label = _detect_page_size_label(width_pt, height_pt)
        page_size_display = f"{width_pt / 72.0:.2f} x {height_pt / 72.0:.2f} in"
        if label:
            page_size_display += f" ({label})"

    fmt = (meta.get("format") or "").strip()
    pdf_version = None
    parts = fmt.split()
    if len(parts) >= 2 and parts[0].upper() == "PDF":
        pdf_version = parts[1]
    elif fmt:
        pdf_version = fmt

    tagged_pdf: bool | None = None
    fast_web_view: bool | None = None
    pdfa = None
    try:
        with pikepdf.open(io.BytesIO(raw_bytes)) as pdf:
            from app.services.pdf_service.core import pdfa_claim

            pdfa = pdfa_claim(pdf)
            try:
                fast_web_view = bool(pdf.is_linearized)
            except Exception:
                fast_web_view = None
            try:
                tagged_pdf = bool(pdf.Root.MarkInfo.Marked)
            except Exception:
                # ไม่มี /MarkInfo /Marked เลย = ตรวจได้แน่ชัดว่าไม่ใช่ tagged PDF (ไม่ใช่ "ไม่ทราบ")
                tagged_pdf = False
    except Exception:
        logger.warning(
            "get_document_properties: เปิดด้วย pikepdf เพื่อตรวจ Tagged PDF/Fast Web View ไม่สำเร็จ session=%s",
            session.session_id,
        )

    is_encrypted = get_encryption_state(session)

    signatures = []
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign import validation

        reader = PdfFileReader(io.BytesIO(raw_bytes), strict=False)
        for sig in reader.embedded_signatures:
            sig_dict = sig.sig_object
            
            def _get_str(key):
                val = sig_dict.get(f"/{key}")
                if val:
                    try:
                        if hasattr(val, "get_original_bytes"):
                            b = val.get_original_bytes()
                            return b.decode("utf-16-be") if b.startswith(b'\xfe\xff') else b.decode("utf-8", "ignore")
                        return str(val)
                    except:
                        return str(val)
                return None
            
            name = _get_str("Name")
            reason = _get_str("Reason")
            location = _get_str("Location")
            contact = _get_str("ContactInfo")
            date_str = _get_str("M")
            
            is_valid = False
            is_trusted = None
            cert = None

            try:
                # simple validation (no revocation checking)
                status = validation.validate_pdf_signature(sig, signer_validation_context=_get_trust_context())
                is_valid = bool(status.valid)
                is_trusted = bool(status.trusted)
                cert = getattr(status, "signing_cert", None) or getattr(status, "signer_cert", None)
            except Exception:
                logger.warning(
                    "get_document_properties: ตรวจลายเซ็นไม่สำเร็จ session=%s", session.session_id, exc_info=True
                )

            if cert is None:
                # ตรวจลายเซ็นพัง (เช่นไฟล์เสียหาย/อัลกอริทึมไม่รองรับ) — ยังอ่านข้อมูล cert จากลายเซ็นตรง ๆ ได้
                try:
                    cert = sig.signer_cert
                except Exception:
                    logger.warning(
                        "get_document_properties: อ่าน cert จากลายเซ็นไม่สำเร็จ session=%s",
                        session.session_id,
                        exc_info=True,
                    )

            cert_details = _extract_cert_details(cert) if cert is not None else {}

            signatures.append({
                "name": name,
                "reason": reason,
                "location": location,
                "contact_info": contact,
                "date": _parse_pdf_date(date_str),
                "is_valid": is_valid,
                "is_trusted": is_trusted,
                **cert_details,
            })
    except Exception:
        logger.warning("get_document_properties: อ่านลายเซ็นดิจิทัลไม่สำเร็จ session=%s", session.session_id, exc_info=True)

    fonts_set = set()
    try:
        for page in doc:
            for font in page.get_fonts():
                # font is tuple: (xref, ext-name, type, base-font, name, enc)
                # base-font is index 3
                if len(font) > 3 and font[3]:
                    # Remove subset prefix if exists (e.g. ABCDEF+Arial -> Arial)
                    font_name = font[3]
                    if "+" in font_name and len(font_name.split("+")[0]) == 6:
                        font_name = font_name.split("+", 1)[1]
                    fonts_set.add(font_name)
    except Exception as e:
        pass

    return {
        "fonts": sorted(list(fonts_set)),
        "signatures": signatures,
        "title": meta.get("title") or None,
        "author": meta.get("author") or None,
        "subject": meta.get("subject") or None,
        "keywords": meta.get("keywords") or None,
        "creator": meta.get("creator") or None,
        "producer": meta.get("producer") or None,
        "creation_date": _parse_pdf_date(meta.get("creationDate")),
        "mod_date": _parse_pdf_date(meta.get("modDate")),
        "pdf_version": pdf_version,
        "file_size_bytes": file_size_bytes,
        "file_size_display": _format_file_size(file_size_bytes),
        "page_count": page_count,
        "page_width_pt": width_pt,
        "page_height_pt": height_pt,
        "page_size_display": page_size_display,
        "tagged_pdf": tagged_pdf,
        "fast_web_view": fast_web_view,
        "is_encrypted": is_encrypted,
        "encryption": (session.output_encryption or "aes256") if is_encrypted and session.encryption_touched else None,
        "pdfa": pdfa,
    }
