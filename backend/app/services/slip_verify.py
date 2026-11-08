"""ตรวจสลิปโอนเงิน

1) อ่าน QR ในรูปสลิป (zxing-cpp, ทำในเครื่อง) — QR มาตรฐานของสลิปธนาคารไทยเก็บแค่ รหัสธนาคารผู้โอน + เลขอ้างอิงรายการ
   (transRef) **ไม่มียอดเงิน** → ใช้กันสลิปเดิมถูกแจ้งซ้ำ และให้แอดมินเทียบเลขอ้างอิงกับแอปธนาคาร
2) (ไม่บังคับ) ถามบริการตรวจสลิป (EasySlip) ด้วยข้อความใน QR — ไม่ส่งรูปสลิปออกไป — ได้ยอด/ผู้รับ/เวลาจากฝั่งธนาคาร
   แล้วเทียบกับค่าที่ตั้งไว้ ผ่านทุกข้อ + เปิดอนุมัติอัตโนมัติ → ให้สิทธิ์ทันที

ยอดที่เป็นตัวหนังสือบนรูปสลิปไม่ใช้ตัดสิน (แก้รูปได้) — เชื่อเฉพาะข้อมูลที่ได้จากบริการตรวจสลิป/ธนาคาร
"""
from __future__ import annotations

import datetime as dt
import io
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.services.promptpay import crc16, normalize_id

logger = logging.getLogger(__name__)

EASYSLIP_URL = "https://api.easyslip.com/v1/verify"
TIMEOUT = 15
DATE_TOLERANCE = dt.timedelta(minutes=30)


# ---------------------------------------------------------------- QR ในสลิป

@dataclass
class SlipQR:
    payload: str
    bank_code: str
    trans_ref: str


def _tlv(data: str) -> Optional[dict[str, str]]:
    out, i = {}, 0
    while i < len(data):
        if i + 4 > len(data) or not data[i:i + 4].isdigit():
            return None
        tag, n = data[i:i + 2], int(data[i + 2:i + 4])
        if i + 4 + n > len(data):
            return None
        out[tag] = data[i + 4:i + 4 + n]
        i += 4 + n
    return out


def parse_slip_payload(payload: str) -> Optional[SlipQR]:
    """ข้อความใน QR ของสลิป → SlipQR · ไม่ใช่ QR สลิป (เช่น QR รับเงิน, ลิงก์) = None"""
    payload = (payload or "").strip()
    top = _tlv(payload)
    if not top or "00" not in top or "91" not in top:
        return None
    if top.get("91", "").upper() != crc16(payload[:-4]):
        return None
    sub = _tlv(top["00"])
    if not sub or "02" not in sub or not sub.get("02"):
        return None
    return SlipQR(payload=payload, bank_code=sub.get("01", ""), trans_ref=sub["02"])


def read_slip_qr(image_bytes: bytes) -> Optional[SlipQR]:
    """หา QR ของสลิปในรูป (ลองทุก QR ที่เจอ) — อ่านไม่ได้/ไม่มี = None"""
    try:
        import zxingcpp
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as im:
            im = ImageOps.exif_transpose(im).convert("L")
            for candidate in (im, ImageOps.autocontrast(im)):
                for result in zxingcpp.read_barcodes(candidate, formats=zxingcpp.BarcodeFormat.QRCode):
                    slip = parse_slip_payload(result.text)
                    if slip:
                        return slip
    except Exception:  # noqa: BLE001 — รูปเสีย/ไลบรารีไม่มี ไม่ควรทำให้แจ้งโอนไม่ได้
        logger.warning("อ่าน QR สลิปไม่สำเร็จ", exc_info=True)
    return None


# ---------------------------------------------------------------- บริการตรวจสลิป

@dataclass
class VerifyResult:
    status: str                       # verified | mismatch | retry (ชั่วคราว ลองใหม่อัตโนมัติ) | error (ต้องตรวจเอง)
    amount: Optional[Decimal] = None
    date: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None
    problems: list[str] = field(default_factory=list)

    def detail(self) -> dict:
        return {"amount": float(self.amount) if self.amount is not None else None, "date": self.date,
                "sender": self.sender, "receiver": self.receiver, "problems": self.problems}


class VerifyError(Exception):
    pass


def _http_get(url: str, api_key: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json",
                                               "User-Agent": "JA-PDF-Editor"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 — URL คงที่ (https)
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise VerifyError(f"ติดต่อบริการตรวจสลิปไม่ได้ ({exc.__class__.__name__})") from None


def call_easyslip(payload: str, api_key: str) -> tuple[int, dict]:
    url = f"{EASYSLIP_URL}?{urllib.parse.urlencode({'payload': payload, 'checkDuplicate': 'true'})}"
    return _http_get(url, api_key)


def _name(account: dict) -> str:
    name = (account or {}).get("name") or {}
    return (name.get("th") or name.get("en") or "").strip()


def _accounts(account: dict) -> list[str]:
    out = []
    for key in ("proxy", "bank"):
        value = ((account or {}).get(key) or {}).get("account")
        if value:
            out.append(str(value))
    return out


def masked_match(masked: str, actual: str, min_revealed: int = 4) -> bool:
    """เลขบัญชีที่ธนาคารปิดบางหลัก (xxx-xxx-5678) ตรงกับเลขจริงไหม — เทียบจากขวา ทุกหลักที่เปิดต้องตรง และเปิด ≥ 4 หลัก"""
    m = re.sub(r"[^0-9xX*]", "", masked or "")
    a = re.sub(r"\D", "", actual or "")
    if not m or not a:
        return False
    if a.startswith("0") and len(m) == len(a) + 1 and m.startswith("66"):  # เบอร์แบบ 66xxxxxxxxx
        a = "66" + a[1:]
    revealed = 0
    for mc, ac in zip(reversed(m), reversed(a)):
        if mc.isdigit():
            if mc != ac:
                return False
            revealed += 1
    return revealed >= min_revealed


def _norm_name(s: str) -> str:
    s = re.sub(r"^(นาย|นางสาว|นาง|น\.ส\.|ด\.ช\.|ด\.ญ\.|mr\.?|mrs\.?|ms\.?|miss)\s*", "", (s or "").strip().lower())
    return re.sub(r"[\s.]+", " ", s).strip()


def receiver_matches(receiver: dict, promptpay_id: str, bank_account: str = "", receiver_name: str = "") -> bool:
    accounts = _accounts(receiver)
    targets = [normalize_id(promptpay_id)[1]] if promptpay_id else []
    if bank_account:
        targets.append(re.sub(r"\D", "", bank_account))
    if any(masked_match(acc, t) for acc in accounts for t in targets if t):
        return True
    # ธนาคารบางแห่งไม่ส่งเลข → เทียบชื่อ (ชื่อแรกต้องตรง และตัวแรกของนามสกุลตรงถ้ามี)
    got, want = _norm_name(_name(receiver)), _norm_name(receiver_name)
    if got and want:
        g, w = got.split(" "), want.split(" ")
        if g[0] == w[0] and (len(g) < 2 or len(w) < 2 or w[1].startswith(g[1].rstrip("."))):
            return True
    return False


def verify(payload: str, *, api_key: str, claimed_amount: Decimal, transferred_at: dt.datetime,
           promptpay_id: str, bank_account: str = "", receiver_name: str = "") -> VerifyResult:
    """ถาม EasySlip แล้วเทียบ: ผู้รับเป็นบัญชีเรา · ยอด ≥ ยอดที่แจ้ง · เวลาใกล้กับที่แจ้ง · ไม่ซ้ำ"""
    code, body = call_easyslip(payload, api_key)
    message = str(body.get("message") or "")
    data = body.get("data") or {}
    if code == 404 and message == "slip_pending":
        return VerifyResult("retry", problems=["ธนาคารยังไม่พร้อมให้ตรวจ (โอนไม่ถึง 5 นาที) — ลองตรวจอีกครั้งภายหลัง"])
    if code == 400 and message == "duplicate_slip":
        return VerifyResult("mismatch", problems=["สลิปนี้เคยถูกตรวจไปแล้ว (ใช้ซ้ำ)"])
    if code in (400, 404) and message in ("invalid_payload", "slip_not_found"):
        return VerifyResult("mismatch", problems=["ไม่พบรายการนี้ที่ธนาคาร (สลิปอาจไม่ถูกต้อง)"])
    if code in (401, 403):  # key ผิด/หมดอายุ/โควต้าเต็ม — ลองซ้ำก็ไม่ผ่าน → แอดมินตรวจเอง
        return VerifyResult("error", problems=[f"บริการตรวจสลิปปฏิเสธ ({message or code}) — ตรวจ API key/โควต้า แล้วตรวจรายการนี้เอง"])
    if code == 429 or code >= 500:  # บริการล่ม/ยุ่งชั่วคราว → ลองใหม่อัตโนมัติ
        return VerifyResult("retry", problems=[f"บริการตรวจสลิปไม่พร้อม ({code}) — ระบบจะลองใหม่อัตโนมัติ"])
    if code != 200 or not data:
        return VerifyResult("error", problems=[f"บริการตรวจสลิปตอบผิดปกติ ({message or code})"])

    try:
        amount = Decimal(str((data.get("amount") or {}).get("amount")))
    except Exception:  # noqa: BLE001
        amount = None
    result = VerifyResult("verified", amount=amount, date=data.get("date"),
                          sender=_name((data.get("sender") or {}).get("account")) or None,
                          receiver=_name((data.get("receiver") or {}).get("account")) or None)
    if not receiver_matches((data.get("receiver") or {}).get("account") or {}, promptpay_id, bank_account, receiver_name):
        result.problems.append("ผู้รับเงินในสลิปไม่ใช่บัญชีพร้อมเพย์ที่ตั้งไว้")
    if amount is None:
        result.problems.append("ไม่ทราบยอดเงินจากธนาคาร")
    elif amount < claimed_amount:
        result.problems.append(f"ยอดจริง {amount:,.2f} บาท น้อยกว่าที่แจ้ง {claimed_amount:,.2f} บาท")
    try:
        when = dt.datetime.fromisoformat(str(data.get("date")).replace("Z", "+00:00"))
        if transferred_at.tzinfo is None:
            transferred_at = transferred_at.replace(tzinfo=dt.timezone.utc)
        if abs(when - transferred_at) > dt.timedelta(days=1):
            result.problems.append("วันที่โอนในสลิปไม่ตรงกับที่แจ้ง")
        if when < dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60):
            result.problems.append("สลิปเก่าเกิน 60 วัน")
    except (TypeError, ValueError):
        result.problems.append("ไม่ทราบวันที่โอนจากธนาคาร")
    if result.problems:
        result.status = "mismatch"
    return result
