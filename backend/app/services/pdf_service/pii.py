"""pdf_service.pii — ตรวจหาข้อมูลส่วนบุคคล (PDPA) แล้วปิดทับถาวร

ทำงานบนเซิร์ฟเวอร์ทั้งหมด (ไม่ส่งข้อความในเอกสารออกไปที่ AI/บริการภายนอก)

ขั้นตอน
1. ``scan_pii`` อ่านข้อความทีละตัวอักษร (rawdict) พร้อมกรอบของแต่ละตัว ต่อเป็นสตริงต่อหน้า
   แล้วใช้ regex + ตัวตรวจ (checksum บัตรประชาชน, Luhn บัตรเครดิต) หา "รายการ" ที่น่าจะเป็นข้อมูลส่วนบุคคล
   กรอบของรายการ = รวมกรอบตัวอักษรที่อยู่บรรทัดเดียวกัน → ปิดได้ตรงเฉพาะจุด (ไม่ใช้ search_for ที่ปิดทุกที่ที่เจอคำเดียวกัน)
2. ``redact_pii`` สแกนซ้ำแล้วปิดเฉพาะ id ที่ผู้ใช้เลือก — id คำนวณจากตำแหน่งในหน้า จึงคงที่ถ้าเอกสารไม่เปลี่ยน
   ถ้ามี id ที่หาไม่เจอ (เอกสารถูกแก้ระหว่างนั้น) → PIIStaleError ให้ผู้ใช้สแกนใหม่

ห้าม log ค่าจริงที่ตรวจพบ — รายงานใช้ค่าที่ปิดบางส่วนแล้ว (``mask_value``)

ชื่อ: คำนำหน้า (นาย/นาง/คุณ/ยศทหาร-ตำรวจแบบย่อและเต็ม/ศ.ดร./ม.ร.ว./พระครู ฯลฯ) + ชื่อ + นามสกุล แยกด้วยช่องว่าง
หรือขึ้นบรรทัด · ชื่อหลังหัวข้อ ("ชื่อ-นามสกุล:", "ชื่อลูกค้า :", "ผู้ติดต่อ :", "Name:" — ค้นบนข้อความเรียงตามแถวที่เห็นด้วย
เพราะหัวข้อกับค่ามักเป็นคนละ block) · ชื่อในวงเล็บหลัง "ลงชื่อ" · ชื่อที่ไม่มีคำนำหน้า/หัวข้อจากรายชื่อคนไทยของ PyThaiNLP
(person_name_guess ความมั่นใจต่ำ) · เลขไทยแปลงเป็นอารบิกก่อนตรวจ · วัดผล: scripts/pii_eval.py
NER ของ PyThaiNLP (thainer) ยังไม่ใช้: ต้องดาวน์โหลดโมเดลตอนรัน (เซิร์ฟเวอร์ต่อเน็ตออกไม่ได้เสมอไป) + python-crfsuite
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import fitz

from app.core.session import PDFSession
from app.services.pdf_service import text_index
from app.services.pdf_service.core import require_unlocked

logger = logging.getLogger("pdf_service")

# ---------------------------------------------------------------- ประเภท

PII_TYPES = {
    "national_id": {"label": "เลขประจำตัวประชาชน / ผู้เสียภาษี", "confidence": "high"},
    "credit_card": {"label": "หมายเลขบัตรเครดิต", "confidence": "high"},
    "email": {"label": "อีเมล", "confidence": "high"},
    "phone": {"label": "เบอร์โทรศัพท์", "confidence": "high"},
    "bank_account": {"label": "เลขบัญชีธนาคาร", "confidence": "medium"},
    "person_name": {"label": "ชื่อ-นามสกุล", "confidence": "medium"},
    # ชื่อที่ไม่มีคำนำหน้า/หัวข้อ — พบจากรายชื่อคนไทย (PyThaiNLP) เท่านั้น จึงต้องให้ผู้ใช้ตรวจเอง
    "person_name_guess": {"label": "อาจเป็นชื่อ-นามสกุล", "confidence": "low"},
    "address": {"label": "ที่อยู่", "confidence": "medium"},
}
# ลำดับการตรวจ — ตัวที่มาก่อน "จอง" ช่วงตัวอักษรไว้ ตัวหลังที่ทับซ้อนจะถูกข้าม
_ORDER = ["email", "national_id", "credit_card", "bank_account", "phone", "address", "person_name", "person_name_guess"]

# ---------------------------------------------------------------- ตัวตรวจ


def thai_id_checksum_ok(digits: str) -> bool:
    """เลขประจำตัวประชาชน/นิติบุคคล 13 หลัก: หลักที่ 13 = (11 - Σ d[i]*(13-i) mod 11) mod 10"""
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum(int(digits[i]) * (13 - i) for i in range(12))
    return (11 - total % 11) % 10 == int(digits[12])


def luhn_ok(digits: str) -> bool:
    if not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card_prefix_ok(digits: str) -> bool:
    if len(digits) == 16 and (digits[0] == "4" or re.match(r"5[1-5]|2[2-7]|6", digits)):
        return True  # Visa / Mastercard / UnionPay
    return len(digits) == 15 and bool(re.match(r"3[47]", digits))  # Amex


# ตัวเลขที่ไม่ติดกับตัวเลขอื่น (ยอมให้คั่นด้วยช่องว่าง/ขีดได้ทีละ 1 ตัว)
_NB = r"(?<!\d)(?<!\d[ \-])"   # ไม่มีเลขอยู่ก่อนหน้า
_NA = r"(?![ \-]?\d)"          # ไม่มีเลขต่อท้าย

_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_RE_ID = re.compile(_NB + r"\d(?:[ \-]?\d){12}" + _NA)
_RE_CARD = re.compile(_NB + r"\d(?:[ \-]?\d){14,15}" + _NA)
_RE_DIGITS_10_12 = re.compile(_NB + r"\d(?:[ \-]?\d){9,11}" + _NA)
_RE_PHONE = re.compile(
    r"(?<![\d+])(?<!\d[ \-])"
    r"(?:\+66[ \-]?(?:\(0\))?|0[ \-]?)"
    r"(?:[689](?:[ \-]?\d){8}|[2-7](?:[ \-]?\d){7})" + _NA
)
_BANK_CONTEXT = re.compile(r"(บัญชี|ธนาคาร|A/C|a/c|Acc(?:oun)?t|ACCOUNT|ออมทรัพย์|กระแสรายวัน)")

_THAI = r"[\u0E01-\u0E3A\u0E40-\u0E4E]"   # อักษรไทย (ไม่รวมเลขไทย ฯ ๆ) — ใช้กับชื่อ
# ช่องว่างระหว่างส่วนของชื่อ: ช่องว่าง 1–3 ตัว หรือขึ้นบรรทัด (ชื่อที่ถูกตัดข้ามบรรทัดในเอกสาร)
_SEP = r"(?:[ ]{1,3}|[ ]*\n[ ]*)"
_SEP_OPT = r"(?:[ ]{0,2}|[ ]*\n[ ]*)"


def _rank_words() -> list[str]:
    """ยศทหาร/ตำรวจแบบเต็ม: พล/พัน/ร้อย/จ่าสิบ/สิบ (+ตำรวจ/เรือ/อากาศ) + เอก/โท/ตรี ฯลฯ"""
    levels = ("เอก", "โท", "ตรี")
    out = []
    for base in ("พล", "พัน", "ร้อย", "จ่าสิบ", "สิบ"):
        for branch in ("", "ตำรวจ", "เรือ", "อากาศ"):
            out += [base + branch + lv for lv in levels]
    for base in ("นาวา", "นาวาอากาศ", "พันจ่า", "พันจ่าอากาศ", "จ่า", "จ่าอากาศ"):
        out += [base + lv for lv in levels]
    return out + ["ดาบตำรวจ", "พลตำรวจ", "พลทหาร"]


def _rank_abbrevs() -> list[str]:
    a = ["พล.อ.", "พล.ท.", "พล.ต.", "พ.อ.", "พ.ท.", "พ.ต.", "ร.อ.", "ร.ท.", "ร.ต.",       # ทหารบก
         "จ.ส.อ.", "จ.ส.ท.", "จ.ส.ต.", "ส.อ.", "ส.ท.", "ส.ต.",
         "พล.ร.อ.", "พล.ร.ท.", "พล.ร.ต.", "น.อ.", "น.ท.", "น.ต.", "พ.จ.อ.", "พ.จ.ท.", "พ.จ.ต.",  # เรือ/อากาศ
         "จ.อ.", "จ.ท.", "จ.ต.", "พล.อ.อ.", "พล.อ.ท.", "พล.อ.ต.", "พ.อ.อ.", "พ.อ.ท.", "พ.อ.ต.",
         "พล.ต.อ.", "พล.ต.ท.", "พล.ต.ต.", "พ.ต.อ.", "พ.ต.ท.", "พ.ต.ต.",                     # ตำรวจ
         "ร.ต.อ.", "ร.ต.ท.", "ร.ต.ต.", "ด.ต.", "ส.ต.อ.", "ส.ต.ท.", "ส.ต.ต.", "พลฯ"]
    return a


_TITLE_WORDS = [
    "นางสาว", "นาง", "นาย", "เด็กชาย", "เด็กหญิง", "คุณ",
    "ศาสตราจารย์", "รองศาสตราจารย์", "ผู้ช่วยศาสตราจารย์",
    "นายแพทย์", "แพทย์หญิง", "ทันตแพทย์หญิง", "ทันตแพทย์", "เภสัชกรหญิง", "เภสัชกร",
    "หม่อมราชวงศ์", "หม่อมหลวง", "หม่อมเจ้า",
    "พระครู", "พระมหา", "พระอธิการ", "พระปลัด", "พระใบฎีกา", "พระสมุห์",
] + _rank_words()
_TITLE_ABBREVS = [
    "น.ส.", "ด.ช.", "ด.ญ.", "ดร.", "นพ.", "พญ.", "ทพ.", "ทพญ.", "ภก.", "ภญ.",
    "ศ.", "รศ.", "ผศ.", "ม.ร.ว.", "ม.ล.", "ม.จ.",
] + _rank_abbrevs()


def _alt(words) -> str:
    return "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))


# คำนำหน้าหนึ่งชุด: (ว่าที่) + คำนำหน้า (+หญิง) (+ ศ./รศ./ผศ. ตามด้วย ดร./นพ. ฯลฯ ได้อีกชั้น)
_ONE_TITLE = r"(?:" + _alt(_TITLE_WORDS + _TITLE_ABBREVS) + r")(?:[ ]?หญิง)?"
_TITLES_TH = r"(?:ว่าที่[ ]?)?" + _ONE_TITLE + r"(?:[ ]?(?:ดร\.|นพ\.|พญ\.|ทพ\.|ทพญ\.))?"
_RE_NAME_TH = re.compile(r"(?P<title>" + _TITLES_TH + r")" + _SEP_OPT + r"(" + _THAI + r"{2,25})" + _SEP
                         + r"(" + _THAI + r"{2,30})")
# ชื่อหลังหัวข้อในแบบฟอร์ม (ไม่มีคำนำหน้า): "ชื่อ-นามสกุล: สมชาย ใจดี"
_RE_NAME_LABEL = re.compile(r"(?:ชื่อ[ ]?[-–][ ]?(?:นาม)?สกุล|ชื่อและนามสกุล|ชื่อสกุล)[ ]*[:：]?[ ]*\n?[ ]*"
                            r"(?P<name>" + _THAI + r"{2,25}" + _SEP + _THAI + r"{2,30})")
# หัวข้อที่ตามด้วยชื่อคน (ต้องมี ":" — กันข้อความบรรยาย เช่น "ผู้รับผิดชอบโครงการ")
_NAME_LABELS = ("ชื่อลูกค้า", "ชื่อผู้รับ(?:สินค้า)?", "ชื่อผู้ส่ง", "ชื่อผู้ติดต่อ", "ชื่อผู้ขอ", "ชื่อผู้ซื้อ", "ชื่อผู้ขาย",
                "ชื่อผู้เช่า", "ชื่อผู้กู้", "ชื่อผู้ป่วย", "ชื่อผู้สมัคร", "ชื่อผู้ใช้", "ชื่อผู้ถือบัตร", "ชื่อพนักงาน",
                "ชื่อ", "ลูกค้า", "ผู้รับ(?:สินค้า)?", "ผู้ส่ง", "ผู้ติดต่อ", "ผู้ซื้อ", "ผู้ขอ", "ผู้ยื่นคำขอ", "ผู้สมัคร",
                "ผู้ป่วย", "ผู้ถือบัตร", "ผู้เช่า", "ผู้กู้", "ผู้ค้ำประกัน", "ผู้รับมอบอำนาจ", "ผู้มอบอำนาจ", "พนักงาน")
_RE_NAME_LABEL2 = re.compile(r"(?<![\u0E01-\u0E4E])(?:" + "|".join(_NAME_LABELS) + r")[ ]*[:：][ ]*\n?[ ]*"
                             r"(?P<name>" + _THAI + r"{2,25}" + _SEP + _THAI + r"{2,30})")
# ลายมือชื่อ: "ลงชื่อ ............ (สมชาย ใจดี)" — ชื่อในวงเล็บหลัง "ลงชื่อ"
_RE_NAME_SIGN = re.compile(r"ลงชื่อ[^()\n]{0,80}\n?[^()\n]{0,40}\([ ]*(?P<name>" + _THAI + r"{2,25}" + _SEP + _THAI + r"{2,30})[ ]*\)")
_RE_NAME_EN_LABEL = re.compile(r"\b(?:Customer Name|Full Name|Name|Contact|Recipient|Attn\.?)[ ]*:[ ]*"
                               r"(?P<name>[A-Z][a-zA-Z'\-]+(?:[ ]+[A-Z][a-zA-Z'\-]+){1,2})")
_RE_THAI_RUN = re.compile(r"[\u0E01-\u0E4E]+")
# คำทั่วไปที่ไม่ใช่ชื่อหรือนามสกุล ("พล.อ.อ. คือ ยศ", "นาย ที่ ปรึกษา")
_FUNCTION_WORDS = frozenset((
    "คือ", "เป็น", "และ", "หรือ", "ที่", "ซึ่ง", "ได้", "ให้", "ของ", "ใน", "จะ", "ไม่", "มี", "กับ", "แก่", "โดย",
    "ยศ", "ตำแหน่ง", "ชื่อ", "นามสกุล", "สกุล", "ท่าน", "ทั้ง", "เช่น", "ว่า", "ต้อง", "แล้ว", "นี้", "นั้น",
))
# คำนำหน้าชื่อที่ติดกับอักษรไทยตัวก่อนหน้า ยอมรับเฉพาะเมื่อคำก่อนหน้าเป็นคำเหล่านี้ (กัน "ทำนาย", "สนาม" ฯลฯ)
_NAME_PRECEDERS = ("ข้าพเจ้า", "ระหว่าง", "โดย", "และ", "กับ", "ชื่อ", "ผู้", "แก่", "ให้", "ของ", "คือ", "จาก", "ถึง", "เรียน")
_RE_NAME_EN = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?[ ]+[A-Z][a-zA-Z'\-]+(?:[ ]+[A-Z][a-zA-Z'\-]+){1,2}")
# คำที่ขึ้นต้นด้วย "นาย/นาง" แต่ไม่ใช่คำนำหน้าชื่อ
_NOT_NAME = (
    "ก", "จ้าง", "หน้า", "ทุน", "อำเภอ", "ทะเบียน", "ประกัน", "ร้อย", "พล", "สิบ", "ท้าย", "ช่าง", "ด่าน",
    "ฟ้า", "แบบ", "เอก", "พยาบาล", "งาม", "ใน", "กำนัล", "ไม้",
)

_ADDR_START = re.compile(
    r"(?:บ้านเลขที่|เลขที่|(?<![\d/])\d{1,5}/\d{1,5}(?![\d/])|หมู่ที่|หมู่บ้าน|ม\.\s?\d|ซอย|ซ\.|ถนน|ถ\.|ตำบล|ต\.|แขวง)"
)
_ADDR_PARTS = [
    re.compile(r"(?:ตำบล|ต\.|แขวง)"),
    re.compile(r"(?:อำเภอ|อ\.|เขต)"),
    re.compile(r"(?:จังหวัด|จ\.|กรุงเทพ|กทม)"),
]
_RE_POSTCODE = re.compile(r"(?<!\d)[1-9]\d{4}(?!\d)")
_ADDR_MAX = 180


# ---------------------------------------------------------------- ข้อความ + ตำแหน่ง


# _PageText / _page_text / _rects_for ย้ายไป text_index.py (ใช้ร่วมกับการค้นหาเพื่อเซ็นเซอร์)
_PageText = text_index.PageText
_page_text = text_index.page_text
_rects_for = text_index.rects_for


# ---------------------------------------------------------------- ค้นหา


@dataclass
class PIIFinding:
    id: str
    type: str
    page: int
    text: str
    rects: list = field(default_factory=list)  # fitz.Rect (พิกัดหน้าที่ยังไม่หมุน — ใช้ redact)
    # ข้อมูลที่อยู่ในช่องกรอกฟอร์ม/กล่องข้อความ/บันทึกย่อ (ไม่ใช่ข้อความบนหน้า): ("widget"|"annot", xref)
    source: tuple | None = None

    @property
    def confidence(self) -> str:
        return PII_TYPES[self.type]["confidence"]


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _title_is_part_of_word(title: str, rest: str) -> bool:
    """คำนำหน้าที่จริง ๆ เป็นส่วนต้นของคำในพจนานุกรม — "คุณสมบัติ", "คุณภาพ", "พระมหากษัตริย์", "นายจ้าง" """
    from app.services import thai_text

    word = title.replace(" ", "")
    if word.endswith(".") or not rest:
        return False
    first = thai_text.tokenize(word + rest, keep_whitespace=False)[0]
    return len(first) > len(word) and first in thai_text._dictionary()


def _candidates(text: str):
    """yield (type, start, end) — ยังไม่ตัดการทับซ้อน
    เลขไทย (๐–๙) ถูกแปลงเป็นเลขอารบิกก่อนตรวจ (แทนที่ทีละตัว ตำแหน่งไม่เลื่อน)"""
    text = text.translate(_THAI_DIGITS)
    for m in _RE_EMAIL.finditer(text):
        yield "email", m.start(), m.end()
    for m in _RE_ID.finditer(text):
        if thai_id_checksum_ok(_digits(m.group(0))):
            yield "national_id", m.start(), m.end()
    for m in _RE_CARD.finditer(text):
        d = _digits(m.group(0))
        if _card_prefix_ok(d) and luhn_ok(d):
            yield "credit_card", m.start(), m.end()
    for m in _RE_DIGITS_10_12.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        if _BANK_CONTEXT.search(before):
            yield "bank_account", m.start(), m.end()
    for m in _RE_PHONE.finditer(text):
        yield "phone", m.start(), m.end()
    for m in _ADDR_START.finditer(text):
        window = text[m.start():m.start() + _ADDR_MAX]
        pc = _RE_POSTCODE.search(window)
        if not pc:
            continue
        span = window[:pc.end()]
        if sum(1 for p in _ADDR_PARTS if p.search(span)) >= 2:
            yield "address", m.start(), m.start() + pc.end()
    for m in _RE_NAME_TH.finditer(text):
        prev = text[max(0, m.start() - 1):m.start()]
        if prev == "." or (prev and re.match(_THAI, prev)
                           and not text[max(0, m.start() - 10):m.start()].endswith(_NAME_PRECEDERS)):
            continue  # "พ.ศ." / "ทำนาย" — คำนำหน้าเป็นส่วนท้ายของคำ/อักษรย่ออื่น
        title, first = m.group("title"), m.group(2)
        if title in ("นาย", "นาง") and any(first.startswith(w) for w in _NOT_NAME):
            continue
        if _title_is_part_of_word(title, first) or first in _FUNCTION_WORDS or m.group(3) in _FUNCTION_WORDS:
            continue
        yield "person_name", m.start(), m.end()
    for rx in (_RE_NAME_LABEL, _RE_NAME_LABEL2, _RE_NAME_SIGN):
        for m in rx.finditer(text):
            first, *_rest = re.split(r"[ \n]+", m.group("name"))
            if first in _FUNCTION_WORDS or _rest and _rest[-1] in _FUNCTION_WORDS:
                continue
            yield "person_name", m.start("name"), m.end("name")
    for m in _RE_NAME_EN_LABEL.finditer(text):
        yield "person_name", m.start("name"), m.end("name")
    yield from _guess_names(text)
    for m in _RE_NAME_EN.finditer(text):
        yield "person_name", m.start(), m.end()


def _name_lists() -> tuple[frozenset, frozenset]:
    """(ชื่อจริง, นามสกุล) คนไทยจาก PyThaiNLP — ไฟล์มากับแพ็กเกจ ไม่ต้องดาวน์โหลด"""
    global _NAMES
    if _NAMES is None:
        try:
            from pythainlp.corpus.common import thai_family_names, thai_female_names, thai_male_names

            _NAMES = (frozenset(thai_male_names()) | frozenset(thai_female_names()), frozenset(thai_family_names()))
        except Exception:  # noqa: BLE001 — ไม่มีรายชื่อ: ข้ามการเดาชื่อ
            _NAMES = (frozenset(), frozenset())
    return _NAMES


_NAMES: tuple[frozenset, frozenset] | None = None


def _guess_names(text: str):
    """ชื่อ + นามสกุลที่ไม่มีคำนำหน้า/หัวข้อ: คำไทยสองคำติดกัน (คั่นด้วยช่องว่าง/ขึ้นบรรทัด) ที่คำแรกอยู่ในรายชื่อจริง
    และคำที่สองอยู่ในรายชื่อนามสกุล — ไม่นับคู่ที่เป็นคำทั่วไปทั้งสองคำ ("มานะ อดทน")"""
    from app.services import thai_text

    first_names, family = _name_lists()
    if not first_names:
        return
    common = thai_text._dictionary()
    runs = list(_RE_THAI_RUN.finditer(text))
    for a, b in zip(runs, runs[1:]):
        gap = text[a.end():b.start()]
        if not gap or len(gap) > 4 or gap.strip(" \n"):
            continue
        first, last = a.group(0), b.group(0)
        if first not in first_names or last not in family or len(last) < 3:
            continue
        if first in common and last in common:
            continue
        yield "person_name_guess", a.start(), b.end()


def find_in_text(text: str) -> list[tuple[str, int, int]]:
    """รายการข้อมูลส่วนบุคคลในข้อความ [(type, start, end)] หลังตัดการทับซ้อนตามลำดับ _ORDER
    ใช้กับข้อความทั้งหน้า (ตำแหน่งตรงกับ PageText.text) และใน scripts/pii_eval.py"""
    order = {t: i for i, t in enumerate(_ORDER)}
    cands = sorted(set(_candidates(text)), key=lambda c: (order[c[0]], c[1], -(c[2] - c[1])))
    taken = [False] * len(text)
    out = []
    for typ, s, e in cands:
        if any(taken[s:e]):
            continue
        for i in range(s, e):
            taken[i] = True
        out.append((typ, s, e))
    return sorted(out, key=lambda c: c[1])


def _visual_rows(pt: _PageText) -> tuple[str, list[int | None]]:
    """ข้อความเรียงตามแถวที่เห็นบนหน้า (บรรทัดที่อยู่ระดับเดียวกันต่อกันจากซ้ายไปขวา) + ตำแหน่งในข้อความเดิมของแต่ละตัว
    — แบบฟอร์มที่หัวข้อ ("ชื่อลูกค้า :") กับค่าเป็นคนละ block ข้อความเดิมจะไม่อยู่ติดกัน"""
    spans: dict[int, list[int]] = {}
    for i, ln in enumerate(pt.lines):
        spans.setdefault(ln, []).append(i)
    info = []
    for ln, idx in spans.items():
        boxes = [pt.boxes[i] for i in idx if pt.boxes[i] is not None and pt.text[i].strip()]
        if boxes:
            info.append((min(b[1] for b in boxes), max(b[3] for b in boxes), min(b[0] for b in boxes), idx))
    info.sort(key=lambda t: (t[0], t[2]))
    rows: list[list] = []
    for y0, y1, x0, idx in info:
        for row in rows:
            ry0, ry1 = row[0]
            if min(y1, ry1) - max(y0, ry0) > 0.5 * min(y1 - y0, ry1 - ry0):
                row[1].append((x0, idx))
                break
        else:
            rows.append([(y0, y1), [(x0, idx)]])
    chars: list[str] = []
    origin: list[int | None] = []
    for _yy, parts in rows:
        for x0, idx in sorted(parts):
            for i in idx:
                if pt.text[i] == "\n":
                    continue
                chars.append(pt.text[i])
                origin.append(i)
            chars.append(" ")
            origin.append(None)
        chars.append("\n")
        origin.append(None)
    return "".join(chars), origin


def _label_names(pt: _PageText):
    """ชื่อหลังหัวข้อในแบบฟอร์ม ค้นบนข้อความเรียงตามแถวที่เห็น → (type, start, end) ในข้อความเดิม"""
    vtext, origin = _visual_rows(pt)
    for typ, s, e in find_in_text(vtext):
        if typ != "person_name":
            continue
        idx = [origin[k] for k in range(s, e) if origin[k] is not None]
        if not idx:
            continue
        # ชื่อต้องอยู่ในบรรทัดเดิมเดียวกัน (ไม่ข้ามไปต่อกับข้อความคอลัมน์อื่น)
        if len({pt.lines[i] for i in idx}) == 1:
            yield typ, min(idx), max(idx) + 1


def _scan_page(page: fitz.Page, page_index: int) -> tuple[list[PIIFinding], bool]:
    pt = _page_text(page)
    has_text = bool(pt.text.strip())
    if not has_text:
        objs = _object_findings(page, page_index)
        objs.sort(key=lambda f: (f.rects[0].y0, f.rects[0].x0))
        return objs, False
    taken = [False] * len(pt.text)
    found: list[PIIFinding] = []
    for typ, s, e in sorted(set(find_in_text(pt.text)) | set(_label_names(pt)),
                            key=lambda c: (_ORDER.index(c[0]), c[1])):
        if any(taken[s:e]):
            continue
        rects = _rects_for(pt, s, e)
        if not rects:
            continue
        for i in range(s, e):
            taken[i] = True
        text = re.sub(r"\s+", " ", pt.text[s:e]).strip()
        found.append(PIIFinding(id=f"p{page_index}-{s}-{e}-{typ}", type=typ, page=page_index, text=text, rects=rects))
    found.extend(_object_findings(page, page_index))
    found.sort(key=lambda f: (f.rects[0].y0, f.rects[0].x0))
    return found, True


_TEXT_WIDGETS = (fitz.PDF_WIDGET_TYPE_TEXT, fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX)
_TEXT_ANNOTS = (fitz.PDF_ANNOT_FREE_TEXT, fitz.PDF_ANNOT_SQUARE, fitz.PDF_ANNOT_TEXT)


def _object_findings(page: fitz.Page, page_index: int) -> list[PIIFinding]:
    """ข้อมูลส่วนบุคคลในค่าช่องกรอกฟอร์ม กล่องข้อความ กรอบสี่เหลี่ยม และบันทึกย่อ

    เดิมตรวจเฉพาะข้อความบนหน้า: แบบฟอร์มที่กรอกเลขบัตรประชาชน/เบอร์โทรไว้ หรือกล่องข้อความที่พิมพ์เพิ่มในแอป
    ไม่ถูกตรวจเลย (สิ่งเหล่านี้เป็น annotation ไม่ใช่เนื้อหน้า) ผู้ใช้เข้าใจว่าไฟล์สะอาดแล้วทั้งที่ข้อมูลยังเห็นชัด"""
    out: list[PIIFinding] = []
    items = []
    for w in page.widgets() or []:
        if w.field_type in _TEXT_WIDGETS and isinstance(w.field_value, str) and w.field_value.strip():
            items.append(("widget", w.xref, fitz.Rect(w.rect), w.field_value))
    for a in page.annots() or []:
        if a.type[0] in _TEXT_ANNOTS:
            content = (a.info or {}).get("content") or ""
            if content.strip():
                items.append(("annot", a.xref, fitz.Rect(a.rect), content))
    for kind, xref, rect, value in items:
        for typ, s, e in find_in_text(value):
            text = re.sub(r"\s+", " ", value[s:e]).strip()
            if text:
                out.append(PIIFinding(id=f"p{page_index}-{kind[0]}{xref}-{s}-{e}-{typ}", type=typ, page=page_index,
                                      text=text, rects=[rect], source=(kind, xref)))
    return out


def _mask_object_values(doc: fitz.Document, page_index: int, findings: list[PIIFinding], user_id=None) -> None:
    """ปิดค่าในช่องฟอร์ม/annotation ด้วย ███ เฉพาะส่วนที่เลือก (ไม่ใช้ redaction — จะลบเนื้อหน้าใต้ช่องไปด้วย)"""
    from app.services import annotation_service

    by_obj: dict[tuple, list[PIIFinding]] = {}
    for f in findings:
        by_obj.setdefault(f.source, []).append(f)
    for (kind, xref), fs in by_obj.items():
        page = doc[page_index]
        if kind == "widget":
            w = next((x for x in page.widgets() or [] if x.xref == xref), None)
            if w is None:
                continue
            w.field_value = _mask_spans(w.field_value or "", fs)
            w.update()
        else:
            a = page.load_annot(xref)
            if a is None:
                continue
            content = _mask_spans((a.info or {}).get("content") or "", fs)
            a.set_info(content=content)
            if annotation_service._is_app_text_annot(a):
                # กล่องข้อความ/กรอบของแอป: วาดภาพข้อความใหม่ด้วยค่าที่ปิดแล้ว
                fontname, fontsize, _ = annotation_service._get_annot_meta(a)
                t = annotation_service._get_annot_type_name(a)
                color = annotation_service._get_annot_color(a)
                if t == "rect":
                    annotation_service._set_text_appearance(page, a, content, (0, 0, 0), None, None,
                                                            border_color=color or (0.9, 0.3, 0.15), user_id=user_id)
                else:
                    annotation_service._set_text_appearance(page, a, content, color or (0, 0, 0), fontname,
                                                            fontsize or 12, user_id=user_id)
            else:
                a.update()


def _mask_spans(value: str, fs: list[PIIFinding]) -> str:
    """แทนช่วง [s:e] ของแต่ละรายการ (จาก id) ด้วย █"""
    spans = []
    for f in fs:
        _p, _o, s, e, _t = f.id.split("-", 4)
        spans.append((int(s), int(e)))
    out, last = [], 0
    for s, e in sorted(spans):
        if s < last:
            continue
        out.append(value[last:s])
        out.append("█" * max(3, len(value[s:e].strip())))
        last = e
    out.append(value[last:])
    return "".join(out)


def scan_pii(session: PDFSession) -> dict:
    """คืน {"findings": [...], "pages_without_text": [...], "page_count": n}
    rects ในผลลัพธ์เป็นพิกัด "หน้าที่แสดงผล" (หมุนตามหน้าแล้ว) ใช้วาดไฮไลต์บนหน้าจอ"""
    doc = require_unlocked(session)
    findings, no_text = [], []
    for i, page in enumerate(doc):
        page_found, has_text = _scan_page(page, i)
        if not has_text:
            no_text.append(i)
        mat = page.rotation_matrix
        for f in page_found:
            findings.append({
                "id": f.id,
                "type": f.type,
                "label": PII_TYPES[f.type]["label"],
                "confidence": f.confidence,
                "page": f.page,
                "text": f.text,
                "rects": [_rect_dict(fitz.Rect(r) * mat) for r in f.rects],
            })
    return {"findings": findings, "pages_without_text": no_text, "page_count": len(doc)}


def _rect_dict(r: fitz.Rect) -> dict:
    r.normalize()
    return {"x0": round(r.x0, 2), "y0": round(r.y0, 2), "x1": round(r.x1, 2), "y1": round(r.y1, 2)}


def mask_value(typ: str, text: str) -> str:
    """ค่าที่ปิดบางส่วนสำหรับรายงาน — เหลือตัวแรก/ท้ายพอให้จำได้ว่าคือรายการไหน"""
    if typ == "email" and "@" in text:
        local, domain = text.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if typ in ("person_name", "person_name_guess", "address"):
        words = text.split(" ")
        return " ".join(w[:1] + "***" if len(w) > 1 else w for w in words[:4]) + (" …" if len(words) > 4 else "")
    # ตัวเลข: เก็บหลักแรกและ 2 หลักท้าย ที่เหลือเป็น x (คงตัวคั่นไว้)
    digit_pos = [i for i, c in enumerate(text) if c.isdigit()]
    keep = set(digit_pos[:1] + digit_pos[-2:])
    return "".join(c if (not c.isdigit() or i in keep) else "x" for i, c in enumerate(text))


class PIIStaleError(Exception):
    """id ที่เลือกหาไม่พบแล้ว — เอกสารถูกแก้ไขหลังสแกน"""


def redact_pii(session: PDFSession, ids: list[str], clean_metadata: bool = False) -> dict:
    """ปิดทับถาวรเฉพาะรายการที่เลือก คืน {"redacted": n, "report": [{type,label,page,masked}], "metadata_cleaned": bool}
    ผู้เรียกต้องถือ session.lock"""
    doc = require_unlocked(session)
    wanted = set(ids)
    if not wanted and not clean_metadata:
        return {"redacted": 0, "report": [], "metadata_cleaned": False}
    by_page: dict[int, list[PIIFinding]] = {}
    for i, page in enumerate(doc):
        if not any(x.startswith(f"p{i}-") for x in wanted):
            continue
        page_found, _ = _scan_page(page, i)
        by_page[i] = [f for f in page_found if f.id in wanted]
    matched = {f.id for fs in by_page.values() for f in fs}
    missing = wanted - matched
    if missing:
        raise PIIStaleError(f"ไม่พบ {len(missing)} รายการ")

    report = []
    for i, fs in by_page.items():
        if not fs:
            continue
        page = doc[i]
        on_page = [f for f in fs if f.source is None]
        for f in fs:
            for r in (f.rects if f.source is None else []):
                page.add_redact_annot(r, fill=(0, 0, 0))
            report.append({"type": f.type, "label": PII_TYPES[f.type]["label"], "page": i + 1,
                           "masked": mask_value(f.type, f.text)})
        if on_page:
            # ภาพที่อยู่ใต้กรอบถูกลบเฉพาะ pixel ที่ทับ (กันกรณีข้อความซ้อนบนภาพสแกน)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
        objs = [f for f in fs if f.source is not None]
        if objs:
            _mask_object_values(doc, i, objs, user_id=getattr(session, "user_id", None))

    # ค่าเดียวกันที่ซ้ำอยู่ในบันทึกย่อ บุ๊กมาร์ก ข้อมูลเมตา ช่องฟอร์มอื่น — เดิมปิดบนหน้าแล้วยังเปิดดู/คัดลอกได้จากที่เหล่านี้
    from app.services.pdf_service import text_index
    from app.services.pdf_service.redact import scrub_hidden_text

    for text in {f.text for fs in by_page.values() for f in fs if len(f.text) >= 4}:
        try:
            scrub_hidden_text(doc, text_index.keyword_pattern(text, False, False))
        except Exception:  # noqa: BLE001 — ปิดบนหน้าสำเร็จแล้ว ส่วนนี้เป็นงานเสริม
            logger.warning("PDPA: ลบค่าซ้ำจากส่วนอื่นของไฟล์ไม่สำเร็จ", exc_info=True)

    if clean_metadata:
        doc.set_metadata({})
        doc.del_xml_metadata()
    if report or clean_metadata:
        session.mark_dirty()
        session.push_history()
    counts: dict[str, int] = {}
    for r in report:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    logger.info("PDPA redaction session=%s counts=%s metadata=%s", session.session_id, counts, clean_metadata)
    return {"redacted": len(report), "report": report, "metadata_cleaned": clean_metadata}
