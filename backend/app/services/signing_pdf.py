"""งาน PDF ของการลงนามตามลำดับ (pyHanko) — แยกจากส่วน workflow/DB ใน signing_service.py

หลักการ (ดู claude/plan-sequential-signing.md):
- สร้างฟิลด์ลายเซ็นของ "ทุกคน" ไว้ล่วงหน้าตอนส่งคำขอ (prepare_signature_fields) ชื่อกำหนดตายตัวต่อขั้น
  ผู้ลงนามเซ็นลงฟิลด์ของตัวเองเท่านั้น ไม่มีการสร้างฟิลด์ใหม่หลังมีลายเซ็นแล้ว → ชื่อไม่ชนกัน และโปรแกรมอ่าน PDF
  ไม่แจ้งว่าเอกสารถูกแก้หลังเซ็น
- ทุกการเขียนเป็นแบบ incremental (IncrementalPdfFileWriter) ไบต์เดิมไม่ถูกแตะ ลายเซ็นก่อนหน้าจึงยัง valid
- ลายเซ็นอิเล็กทรอนิกส์ก็เป็นลายเซ็นดิจิทัลจริงในฟิลด์ของผู้ลงนาม แต่เซ็นด้วยใบรับรองของระบบ (system seal)
  พร้อมรูปลายมือชื่อ + ชื่อ/อีเมลผู้ลงนามที่ยืนยันตัวตนผ่านบัญชี — แบบเดียวกับบริการ e-signature ทั่วไป
  (ถ้าแปะรูปลงเนื้อหาหน้าแบบฟีเจอร์ลายเซ็นอิเล็กทรอนิกส์เดิม ลายเซ็นดิจิทัลของคนก่อนหน้าจะถูกระบุว่าเอกสารถูกแก้)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from app.core.config import settings

logger = logging.getLogger("signing_pdf")

_SEAL_DIRNAME = "_seal"
_SEAL_CN = "JA PDF Editor e-Signature Seal"


class SigningPdfError(Exception):
    """ข้อความภาษาไทยที่แสดงให้ผู้ใช้ได้"""


@dataclass
class FieldSpec:
    name: str
    page: int
    # พิกัดแบบ Editor (pt, มุมซ้ายบน = 0,0)
    x0: float
    y0: float
    x1: float
    y1: float


MAX_SIGNATURE_PIXELS = 25_000_000  # รูปลายเซ็นจากกล้องมือถือ ~12–20 MP ผ่าน แต่ภาพยักษ์ (decompression bomb) ไม่ผ่าน
MIN_INK_PIXELS = 30


def normalize_signature_image(data: bytes) -> bytes:
    """ตรวจรูปลายมือชื่อที่ผู้ใช้ส่งมา → PNG (RGBA) ที่หมุนตาม EXIF แล้ว

    เดิมรูปเสีย/ไม่ใช่รูป ถูกข้ามเงียบๆ (log เตือน) แล้วลงนามสำเร็จโดย "ไม่มีลายมือชื่อ" — ผู้ลงนามไม่รู้ตัว
    ตอนนี้: ไม่ใช่รูป / ภาพใหญ่ผิดปกติ / ภาพว่าง (ขาวหรือโปร่งใสทั้งภาพ) → แจ้งให้วาด/อัปโหลดใหม่
    รูปถ่ายจากมือถือที่เก็บทิศทางไว้ใน EXIF หมุนให้ตั้งตรง (เดิมลายเซ็นตะแคง)"""
    from PIL import ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            w, h = probe.size
            if w * h > MAX_SIGNATURE_PIXELS:
                raise SigningPdfError("รูปลายเซ็นใหญ่เกินไป — ใช้รูปที่เล็กกว่านี้ หรือครอปเฉพาะลายเซ็น")
            img = ImageOps.exif_transpose(probe).convert("RGBA")
    except SigningPdfError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise SigningPdfError("ไฟล์รูปลายเซ็นไม่ถูกต้อง — ใช้ไฟล์ PNG หรือ JPG") from None
    gray = img.convert("L")
    ink = Image.eval(gray, lambda v: 255 if v < 240 else 0)              # ไม่ใช่พื้นขาว
    alpha = img.getchannel("A").point(lambda a: 255 if a > 16 else 0)    # ไม่โปร่งใส
    from PIL import ImageChops

    if sum(ImageChops.multiply(ink, alpha).histogram()[255:]) < MIN_INK_PIXELS:
        raise SigningPdfError("รูปลายเซ็นว่างเปล่า — กรุณาวาดหรืออัปโหลดลายเซ็นใหม่")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _page_geometry(pdf_bytes: bytes) -> list[tuple[object, int]]:
    """ต่อหน้า: (เมทริกซ์แปลงพิกัดที่ผู้ใช้เห็น → พิกัด PDF, องศาที่หน้าถูกหมุน /Rotate)

    พิกัดใน FieldSpec เป็นพิกัดบนภาพหน้าที่แสดงจริง (หมุนแล้ว มุมซ้ายบน = 0,0) แต่กล่องฟิลด์ใน PDF ต้องเป็น
    พิกัดของหน้าแบบยังไม่หมุน (มุมซ้ายล่าง = 0,0) — derotation_matrix + ~transformation_matrix แปลงให้ครบทั้งสองอย่าง
    """
    import fitz

    with fitz.open("pdf", pdf_bytes) as doc:
        return [(page.derotation_matrix * ~page.transformation_matrix, page.rotation % 360) for page in doc]


def _pdf_box(spec: "FieldSpec", matrix) -> tuple[float, float, float, float]:
    import fitz

    r = fitz.Rect(spec.x0, spec.y0, spec.x1, spec.y1) * matrix
    r.normalize()
    return (r.x0, r.y0, r.x1, r.y1)


def prepare_signature_fields(pdf_bytes: bytes, specs: list[FieldSpec]) -> bytes:
    """เพิ่มฟิลด์ลายเซ็น (ว่าง) ของทุกขั้นลงในเอกสาร แบบ incremental"""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields

    geometry = _page_geometry(pdf_bytes)
    try:
        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)
    except Exception as exc:
        raise SigningPdfError(f"เปิดเอกสารไม่สำเร็จ: {exc}") from exc
    existing = {name for name, *_ in fields.enumerate_sig_fields(writer)}
    for spec in specs:
        if spec.name in existing:
            raise SigningPdfError(f"มีฟิลด์ลายเซ็นชื่อ {spec.name} อยู่แล้ว")
        if not (0 <= spec.page < len(geometry)):
            raise SigningPdfError("ตำแหน่งลายเซ็นอยู่นอกหน้าเอกสาร")
        box = _pdf_box(spec, geometry[spec.page][0])
        fields.append_signature_field(writer, fields.SigFieldSpec(sig_field_name=spec.name, on_page=spec.page, box=box))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# ใบรับรองของระบบสำหรับลายเซ็นอิเล็กทรอนิกส์ (สร้างครั้งแรกแล้วเก็บไว้ใน volume ของ uploads)
# ---------------------------------------------------------------------------

def _seal_paths() -> tuple[Path, Path]:
    d = settings.UPLOAD_DIR / "_signing" / _SEAL_DIRNAME
    return d / "seal_key.pem", d / "seal_cert.pem"


def _ensure_system_seal() -> tuple[Path, Path]:
    key_path, cert_path = _seal_paths()
    if key_path.is_file() and cert_path.is_file():
        return key_path, cert_path
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _SEAL_CN),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JA PDF Editor")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365 * 10))
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
        .sign(key, hashes.SHA256())
    )
    tmp_key = key_path.with_suffix(".tmp")
    tmp_key.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    tmp_key.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    tmp_key.replace(key_path)
    logger.info("สร้างใบรับรองระบบสำหรับลายเซ็นอิเล็กทรอนิกส์แล้ว: %s", cert_path)
    return key_path, cert_path


_configured_seal_cache: dict = {}


def _configured_seal_signer():
    """ใบรับรองระบบจากไฟล์ .p12 ที่ตั้งค่าไว้ (SIGNING_SEAL_P12) — โหลดใหม่เมื่อไฟล์ถูกเปลี่ยน"""
    path = Path(settings.SIGNING_SEAL_P12)
    if not path.is_file():
        raise SigningPdfError(f"ไม่พบไฟล์ใบรับรองระบบตาม SIGNING_SEAL_P12 ({path}) — ติดต่อผู้ดูแลระบบ")
    key = (str(path), path.stat().st_mtime_ns, settings.SIGNING_SEAL_P12_PASSWORD)
    if _configured_seal_cache.get("key") != key:
        try:
            signer = load_pkcs12_signer(path.read_bytes(), settings.SIGNING_SEAL_P12_PASSWORD)
        except SigningPdfError as exc:
            raise SigningPdfError(f"เปิดใบรับรองระบบ (SIGNING_SEAL_P12) ไม่สำเร็จ — ตรวจรหัสผ่าน: {exc}") from exc
        _configured_seal_cache.update(key=key, signer=signer)
    return _configured_seal_cache["signer"]


def system_seal_signer():
    """ผู้ลงนามสำหรับลายเซ็นอิเล็กทรอนิกส์และหนังสือรับรอง: ใบรับรองจาก CA ถ้าตั้งค่าไว้ ไม่งั้น self-signed

    ถ้าตั้ง SIGNING_SEAL_P12 แล้วแต่ไฟล์/รหัสผ่านผิด จะไม่ถอยไปใช้ self-signed เงียบๆ (ผู้ใช้จะได้ลายเซ็นที่เชื่อถือน้อยกว่า
    ที่องค์กรตั้งใจโดยไม่รู้ตัว) — ให้ลงนามล้มพร้อมข้อความแทน
    """
    if settings.SIGNING_SEAL_P12:
        return _configured_seal_signer()
    from pyhanko.sign import signers

    key_path, cert_path = _ensure_system_seal()
    signer = signers.SimpleSigner.load(str(key_path), str(cert_path))
    if signer is None:
        raise SigningPdfError("โหลดใบรับรองของระบบไม่สำเร็จ")
    return signer


def seal_info() -> dict:
    """ข้อมูลใบรับรองระบบที่ใช้อยู่ + คำเตือน (ใช้ตอน start และ scripts/seal_info.py) — ไม่มีข้อมูลลับ"""
    import hashlib as _hashlib

    signer = system_seal_signer()
    cert = signer.signing_cert
    subject, issuer = cert.subject.native, cert.issuer.native
    tbs = cert["tbs_certificate"]["validity"]
    not_after = tbs["not_after"].native
    now = dt.datetime.now(dt.timezone.utc)
    chain = [c for c in signer.cert_registry if c.sha256 != cert.sha256] if signer.cert_registry else []
    warnings = []
    self_signed = cert.self_signed != "no"
    if self_signed:
        warnings.append("เป็นใบรับรอง self-signed — Adobe จะไม่แสดงว่าเชื่อถือได้")
    elif not chain:
        warnings.append("ไม่มีใบรับรองของผู้ออก (intermediate/root): ไฟล์ .p12 ไม่ได้รวม chain และดาวน์โหลดจาก URL "
                        "ในใบรับรองไม่ได้ — export .p12 แบบรวม chain หรือเปิดให้ backend ออกอินเทอร์เน็ตได้")
    days_left = (not_after - now).days
    if days_left < 0:
        warnings.append("ใบรับรองหมดอายุแล้ว")
    elif days_left < 30:
        warnings.append(f"ใบรับรองจะหมดอายุในอีก {days_left} วัน")
    key_usage = cert.key_usage_value.native if cert.key_usage_value else None
    if key_usage is not None and not ({"digital_signature", "non_repudiation"} & set(key_usage)):
        warnings.append("ใบรับรองไม่ได้อนุญาตให้ใช้ลงนาม (Key Usage ไม่มี digitalSignature/nonRepudiation)")
    return {
        "source": "p12" if settings.SIGNING_SEAL_P12 else "self-signed",
        "subject": subject.get("common_name"),
        "organization": subject.get("organization_name"),
        "issuer": issuer.get("common_name"),
        "self_signed": self_signed,
        "not_after": not_after.isoformat(),
        "days_left": days_left,
        "chain": [c.subject.native.get("common_name") for c in chain],
        "sha256": _hashlib.sha256(cert.dump()).hexdigest(),
        "warnings": warnings,
    }


def load_pkcs12_signer(pfx_bytes: bytes, password: str):
    from pyhanko.sign import signers

    try:
        signer = signers.SimpleSigner.load_pkcs12_data(pfx_bytes, other_certs=set(), passphrase=password.encode("utf-8"))
    except Exception as exc:
        raise SigningPdfError(f"เปิดไฟล์ p12/pfx ไม่สำเร็จ: {exc}") from exc
    if signer is None:
        raise SigningPdfError("เปิดไฟล์ p12/pfx ไม่สำเร็จ — ตรวจสอบว่าเป็นไฟล์ .p12/.pfx จริงและรหัสผ่านถูกต้อง")
    try:
        complete_chain(signer)
    except Exception:  # pragma: no cover - ไม่ให้เรื่อง chain ทำให้ลงนามไม่ได้
        logger.exception("เติม chain ของใบรับรองไม่สำเร็จ")
    return signer


# ---------------------------------------------------------------------------
# เติม chain ของใบรับรอง (intermediate/root) จาก URL "CA Issuers" (AIA) ในใบรับรอง
# ---------------------------------------------------------------------------

_MAX_AIA_BYTES = 1024 * 1024


def _public_host(url: str) -> bool:
    """URL ชี้ไปยังเครื่องสาธารณะเท่านั้น — URL มาจากใบรับรองที่ผู้ใช้อัปโหลด (ใครก็สร้างได้)
    ถ้าไม่กรอง ใบรับรองปลอมจะสั่งให้เซิร์ฟเวอร์ยิงคำขอไปยังบริการภายใน (redis, db, metadata ของ cloud
    169.254.169.254) ได้ (SSRF) — ตรวจทุก IP ที่ชื่อโฮสต์ resolve ได้"""
    import ipaddress
    import socket
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(infos)


def _fetch_url(url: str) -> bytes:
    """ดาวน์โหลดใบรับรองของผู้ออก (เทสต์แทนที่ฟังก์ชันนี้ได้) — เฉพาะโฮสต์สาธารณะ ไม่ตาม redirect"""
    import urllib.error
    import urllib.request

    if not _public_host(url):
        raise SigningPdfError(f"ไม่ดาวน์โหลดจากที่อยู่ภายใน: {url}")

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # redirect ไปที่อยู่ภายในได้ จึงไม่ตาม
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(url, timeout=settings.SIGNING_FETCH_CHAIN_TIMEOUT) as resp:  # noqa: S310 - http(s) เท่านั้น
        return resp.read(_MAX_AIA_BYTES + 1)[:_MAX_AIA_BYTES]


def _ca_issuer_urls(cert) -> list[str]:
    aia = cert.authority_information_access_value
    if not aia:
        return []
    urls = []
    for desc in aia:
        if desc["access_method"].native == "ca_issuers":
            url = desc["access_location"].native
            if isinstance(url, str) and url.lower().startswith(("http://", "https://")):
                urls.append(url)
    return urls


def _parse_certs(data: bytes) -> list:
    """ไฟล์ใบรับรองจาก CA มีได้ทั้ง DER (.cer/.crt), PEM และ PKCS#7 (.p7c)"""
    from asn1crypto import cms, pem, x509 as asn1_x509

    if pem.detect(data):
        return [asn1_x509.Certificate.load(der) for kind, _h, der in pem.unarmor(data, multiple=True)
                if kind == "CERTIFICATE"]
    try:
        cert = asn1_x509.Certificate.load(data)
        cert.subject.native  # บังคับ parse — ถ้าไม่ใช่ใบรับรองจะ error ตรงนี้
        return [cert]
    except Exception:
        info = cms.ContentInfo.load(data)
        return [c.chosen for c in info["content"]["certificates"]]


def _cached_fetch(url: str) -> bytes:
    cache_dir = settings.UPLOAD_DIR / "_signing" / "_aia"
    path = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".bin")
    if path.is_file():
        return path.read_bytes()
    data = _fetch_url(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return data


def complete_chain(signer, max_depth: int = 5) -> int:
    """ถ้าไฟล์ .p12 ไม่มีใบรับรองของผู้ออก ให้ดาวน์โหลดตาม AIA ขึ้นไปจนถึง root แล้วเพิ่มเข้า cert_registry
    (pyHanko ฝังใบรับรองใน registry ไปกับลายเซ็น ทำให้โปรแกรมอ่าน PDF ต่อ chain ได้) คืนจำนวนใบรับรองที่เพิ่ม"""
    if not settings.SIGNING_FETCH_CHAIN:
        return 0
    registry = signer.cert_registry
    known = list(registry)
    cert, added = signer.signing_cert, 0
    for _ in range(max_depth):
        if cert.self_signed != "no":
            break
        issuer = next((c for c in known if c.subject == cert.issuer), None)
        if issuer is None:
            for url in _ca_issuer_urls(cert):
                try:
                    found = _parse_certs(_cached_fetch(url))
                except Exception as exc:
                    logger.warning("ดาวน์โหลดใบรับรองผู้ออกจาก %s ไม่สำเร็จ: %s", url, exc)
                    continue
                issuer = next((c for c in found if c.subject == cert.issuer), None)
                if issuer is not None:
                    registry.register_multiple(found)
                    known.extend(found)
                    added += len(found)
                    break
        if issuer is None:
            break
        cert = issuer
    return added


def signer_subject(signer) -> dict:
    """ชื่อ (CN) และอีเมลใน certificate ของผู้เซ็น"""
    try:
        native = signer.signing_cert.subject.native
    except Exception:
        return {}
    return {"common_name": native.get("common_name"), "email": native.get("email_address")}


# ---------------------------------------------------------------------------
# ลงนามในฟิลด์ที่สร้างไว้
# ---------------------------------------------------------------------------

def _stamp_image(width_pt: float, height_pt: float, caption: list[str], signature_png: Optional[bytes]) -> Image.Image:
    """รูปลายเซ็น (RGBA พื้นโปร่งใส): ลายมือชื่อ (ถ้ามี) ด้านบน + ข้อความกำกับ (ชื่อ/เวลา) ด้านล่าง"""
    from app.services.signature_service import _render_signature_stamp_image

    if not signature_png:
        return _render_signature_stamp_image(caption, width_pt, height_pt)
    caption_h = height_pt * 0.38
    top = _render_signature_stamp_image([], width_pt, height_pt - caption_h, signature_png).convert("RGBA")
    bottom = _render_signature_stamp_image(caption, width_pt, caption_h).convert("RGBA")
    out = Image.new("RGBA", (top.width, top.height + bottom.height), (255, 255, 255, 0))  # โปร่งใส
    out.paste(top, (0, 0), top)
    out.paste(bottom, (0, top.height), bottom)
    return out


def _timestamper():
    """TSA ตาม SIGNING_TSA_URL (ไม่ตั้ง = None) — เทสต์แทนที่ฟังก์ชันนี้ด้วย DummyTimeStamper ได้"""
    if not settings.SIGNING_TSA_URL:
        return None
    from pyhanko.sign.timestamps import HTTPTimeStamper

    return HTTPTimeStamper(settings.SIGNING_TSA_URL, timeout=settings.SIGNING_TSA_TIMEOUT)


def sign_with_optional_tsa(pdf_bytes: bytes, meta, signer, stamp_style=None) -> bytes:
    """ลงนามแบบ incremental พร้อม timestamp จาก TSA ถ้าตั้งค่าไว้ — TSA ล้มเหลวให้ลงนามต่อโดยไม่มี timestamp"""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers

    timestamper = _timestamper()
    if timestamper is not None:
        try:
            writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)
            return signers.PdfSigner(meta, signer=signer, timestamper=timestamper,
                                     stamp_style=stamp_style).sign_pdf(writer).getvalue()
        except Exception as exc:
            logger.warning("ขอ timestamp จาก TSA ไม่สำเร็จ (%s) — ลงนามต่อโดยไม่มี timestamp: %s",
                           settings.SIGNING_TSA_URL, exc)
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)
    return signers.PdfSigner(meta, signer=signer, stamp_style=stamp_style).sign_pdf(writer).getvalue()


def sign_field(
    pdf_bytes: bytes,
    spec: FieldSpec,
    signer,
    caption: list[str],
    signature_png: Optional[bytes] = None,
    reason: Optional[str] = None,
    name: Optional[str] = None,
    location: Optional[str] = None,
) -> bytes:
    """ลงนามในฟิลด์ spec.name ที่มีอยู่แล้ว (incremental) คืนไบต์ไฟล์ใหม่"""
    from pyhanko import stamp
    from pyhanko.pdf_utils.images import PdfImage
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    try:
        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)
    except Exception as exc:
        raise SigningPdfError(f"เปิดเอกสารไม่สำเร็จ: {exc}") from exc
    status = {fname: sig is not None for fname, sig, _ in fields.enumerate_sig_fields(writer)}
    if spec.name not in status:
        raise SigningPdfError("ไม่พบฟิลด์ลายเซ็นของคุณในเอกสาร")
    if status[spec.name]:
        raise SigningPdfError("ฟิลด์ลายเซ็นนี้ถูกลงนามไปแล้ว")

    image = _stamp_image(spec.x1 - spec.x0, spec.y1 - spec.y0, caption, signature_png)
    geometry = _page_geometry(pdf_bytes)
    rotation = geometry[spec.page][1] if 0 <= spec.page < len(geometry) else 0
    if rotation:
        # หน้าที่หมุน r องศา (ตามเข็ม) จะหมุนภาพในกล่องไปด้วย — หมุนภาพทวนเข็มไว้ก่อนให้แสดงผลตั้งตรง
        image = image.rotate(rotation, expand=True)
    style = stamp.StaticStampStyle(background=PdfImage(image), background_opacity=1.0, border_width=0)
    meta = signers.PdfSignatureMetadata(field_name=spec.name, reason=reason or None, name=name or None,
                                        location=location or None)
    try:
        return sign_with_optional_tsa(pdf_bytes, meta, signer, stamp_style=style)
    except Exception as exc:
        logger.exception("sign_field ไม่สำเร็จ field=%s", spec.name)
        raise SigningPdfError(f"ลงนามไม่สำเร็จ: {exc}") from exc


def signature_report(pdf_bytes: bytes) -> list[dict]:
    """ตรวจลายเซ็นทุกฟิลด์: เซ็นแล้วหรือยัง, ไบต์ที่ครอบคลุมไม่ถูกแก้ (intact), คณิตศาสตร์ถูกต้อง (valid),
    และการแก้ไขหลังเซ็นอยู่ในระดับที่อนุญาต (modification_ok) — ไม่ตรวจ trust chain (ใบรับรองส่วนตัว/ของระบบ)"""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign import fields
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    signed = {sig.field_name: sig for sig in reader.embedded_signatures}
    report = []
    for name, _value, _ref in fields.enumerate_sig_fields(reader):
        item = {"field_name": name, "signed": name in signed}
        if name in signed:
            sig = signed[name]
            try:
                st = validate_pdf_signature(sig, ValidationContext(allow_fetching=False))
                item.update(
                    intact=bool(st.intact),
                    valid=bool(st.valid),
                    signer=st.signing_cert.subject.native.get("common_name"),
                    modification_ok=st.docmdp_ok is not False,
                    coverage=str(st.coverage),
                    # เวลาจาก TSA (ถ้ามี) — ตรวจว่าโทเค็น timestamp ครอบคลุมลายเซ็นนี้จริง
                    timestamp=(st.timestamp_validity.timestamp.isoformat()
                               if st.timestamp_validity is not None and st.timestamp_validity.intact else None),
                )
            except Exception as exc:  # pragma: no cover - ไฟล์เสีย
                item.update(intact=False, valid=False, error=str(exc))
        report.append(item)
    return report
