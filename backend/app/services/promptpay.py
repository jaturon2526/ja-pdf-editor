"""สร้างข้อมูล QR พร้อมเพย์ (Thai QR Payment / EMVCo Merchant-Presented Mode) — ทำในเครื่องทั้งหมด ไม่เรียกบริการภายนอก

ผลลัพธ์ตรงกับไลบรารี promptpay-qr (npm) ที่แอปธนาคารไทยใช้กันทั่วไป (ทดสอบใน tests/test_donations.py)
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

AID_PROMPTPAY = "A000000677010111"


class PromptPayError(ValueError):
    pass


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def crc16(data: str) -> str:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) เป็นเลขฐาน 16 ตัวพิมพ์ใหญ่ 4 หลัก"""
    crc = 0xFFFF
    for byte in data.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def normalize_id(raw: str) -> tuple[str, str]:
    """เลขพร้อมเพย์ → (ชนิด, เลขล้วน) · phone = เบอร์มือถือ 10 หลัก, national_id = บัตรประชาชน/เลขผู้เสียภาษี 13 หลัก,
    ewallet = e-Wallet ID 15 หลัก"""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits.startswith("0"):
        return "phone", digits
    if len(digits) == 11 and digits.startswith("66"):  # +66 8x xxx xxxx
        return "phone", "0" + digits[2:]
    if len(digits) == 13:
        return "national_id", digits
    if len(digits) == 15:
        return "ewallet", digits
    raise PromptPayError("เลขพร้อมเพย์ต้องเป็นเบอร์มือถือ 10 หลัก เลขบัตรประชาชน/ผู้เสียภาษี 13 หลัก หรือ e-Wallet 15 หลัก")


def mask_id(raw: str) -> str:
    """แสดงบางส่วน เช่น 081-xxx-5678 — ใช้ในหน้าเว็บให้ผู้โอนตรวจได้ว่าโอนถูกคน โดยไม่เปิดเลขเต็ม"""
    kind, d = normalize_id(raw)
    if kind == "phone":
        return f"{d[:3]}-xxx-{d[-4:]}"
    return f"{d[:1]}{'x' * (len(d) - 5)}{d[-4:]}"


def payload(promptpay_id: str, amount: Optional[Decimal | float | int] = None) -> str:
    """ข้อความใน QR · มียอด = QR แบบใช้ครั้งเดียว (dynamic, 12) ไม่มียอด = ผู้โอนกรอกเอง (static, 11)"""
    kind, d = normalize_id(promptpay_id)
    if kind == "phone":
        account = _tlv("01", ("0000000000000" + "66" + d[1:])[-13:])
    elif kind == "national_id":
        account = _tlv("02", d)
    else:
        account = _tlv("03", d)
    parts = [
        _tlv("00", "01"),
        _tlv("01", "12" if amount else "11"),
        _tlv("29", _tlv("00", AID_PROMPTPAY) + account),
        _tlv("58", "TH"),
        _tlv("53", "764"),
    ]
    if amount:
        value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if value <= 0 or value > Decimal("999999.99"):
            raise PromptPayError("ยอดเงินไม่ถูกต้อง")
        parts.append(_tlv("54", f"{value:.2f}"))
    data = "".join(parts) + "6304"
    return data + crc16(data)


def qr_svg(promptpay_id: str, amount=None, scale: int = 6) -> str:
    """QR เป็น SVG (segno) — error correction M ตามที่แอปธนาคารอ่านได้ดี"""
    import io

    import segno

    out = io.BytesIO()
    segno.make(payload(promptpay_id, amount), error="m", micro=False).save(
        out, kind="svg", scale=scale, border=2, xmldecl=False, svgns=True)
    return out.getvalue().decode("utf-8")
