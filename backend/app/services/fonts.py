"""
fonts — รายชื่อ font ที่ใช้ตอน "วาดข้อความใหม่" ในฟีเจอร์แก้ไขข้อความ (edit_service.replace_text) และ
ตอนวาดข้อความจริงของ annotation (annotation_service._draw_annotation_text_as_pdf) มาจาก 2 แหล่ง: (1) font ที่
bundle มากับแอปเองตั้งแต่แรก (Sarabun/Kanit) กับ (2) font ไทยเพิ่มเติมจาก Google Fonts ที่ดาวน์โหลดมา
cache ไว้ในเครื่อง แบบ best-effort ตอนแอปเริ่มทำงาน (ดู sync_google_fonts ด้านล่าง — ข้อ "การแก้ไข
ข้อความ" ที่ผู้ใช้แจ้งเพิ่ม: "หากสามารถออก Internet ได้ ให้เลือกฟอนต์ที่เป็นภาษาไทยจาก google fonts ได้
หรือหากสามารถเก็บไว้ที่ local ได้ก็ใช้วิธีเก็บที่ local แทน")

ทำไมต้อง bundle/ดาวน์โหลดเอง: PyMuPDF วาดข้อความใหม่ด้วย base-14 font (helv, times, cour, ...) ได้เท่านั้น
โดย default ซึ่งเป็น font ละตินล้วน "ไม่มี glyph ภาษาไทยเลย" — ถ้าใช้ font พวกนี้กับข้อความไทย
จะได้กล่องว่าง/ไม่แสดงผลอะไรเลย (นี่คือสาเหตุหลักที่ "แก้ไขข้อความ" ใช้ไม่ได้กับไฟล์ภาษาไทย)

ทางแก้: bundle font TrueType ที่รองรับภาษาไทยจริง (Sarabun, Kanit — ใบอนุญาต SIL Open Font License,
ใช้/แจกจ่ายต่อได้ฟรี) มากับตัวแอป แล้วฝัง (embed) เข้าไปในหน้าตอน insert_text() ผ่านพารามิเตอร์
fontfile — วิธีนี้ใช้ได้กับไฟล์ PDF อะไรก็ได้ ไม่ต้องพึ่ง font ที่ฝังอยู่ในไฟล์ต้นฉบับ (ซึ่งมักเป็น
subset font ที่มี glyph ไม่ครบทุกตัวอักษรที่ผู้ใช้อาจพิมพ์ใหม่)

เรื่อง Google Fonts (เพิ่มใหม่): sync_google_fonts() ถูกเรียกครั้งเดียวตอนแอปเริ่มทำงาน (background
thread แยก — ดู app/main.py on_startup กันบล็อกการ start แอปถ้าไม่มีเน็ต/เน็ตช้า) ไล่ดาวน์โหลด font
ไทยยอดนิยมจาก Google Fonts (Noto Sans Thai, Prompt, Mitr) มา cache เป็นไฟล์ .ttf/.otf ไว้ในเครื่องที่
app/assets/fonts/google_cache/ — ถ้าเคยดาวน์โหลดสำเร็จแล้ว (ไฟล์ cache มีอยู่แล้ว) จะ "ใช้ของในเครื่อง
เลย ไม่ออกเน็ตซ้ำ" ตามที่ผู้ใช้แจ้งไว้ ถ้าออกอินเทอร์เน็ตไม่ได้ (timeout/error ใดๆ) จะข้ามเงียบๆ ไม่ทำ
ให้แอปพัง เหลือแค่ font ที่ bundle มากับแอปให้เลือกใช้ตามปกติ

หมายเหตุ "user-agent เก่า" (แก้ไขหลัง deploy รอบแรก — ผู้ใช้แจ้งว่า log ขึ้น "ไม่พบลิงก์ไฟล์ .ttf" ทุก
ฟอนต์ ทั้งที่ไม่มี network error เลย แปลว่าติดต่อ Google Fonts ได้ปกติ แค่ตัว User-Agent ที่ปลอมไปเดิม
("MSIE 8.0; Trident/4.0") ใช้ไม่ได้ผลแล้ว — Google อาจเลิก map UA ของ IE8 ไปเป็น .ttf แล้ว (มักจะ map
ไปเป็น .eot ซึ่งไม่มีใน response ปกติ หรือไม่รู้จัก UA นี้แล้วเลย)):

Google Fonts CSS API (fonts.googleapis.com/css2) จะเลือกส่ง URL ของไฟล์ font ตาม User-Agent ของ
request — เบราว์เซอร์สมัยใหม่ที่รู้จักได้ .woff2 ส่วน User-Agent ที่ "จำแนกไม่ได้ว่าเป็นเบราว์เซอร์อะไร"
(เช่นเบราว์เซอร์เก่ามากๆ, บอท, สคริปต์) มักได้ฟอร์แมตที่ปลอดภัย/เข้ากันได้กว้างที่สุดกลับมาแทน คือ .ttf
หรือ .otf ตรงๆ (ยืนยันด้วยการทดสอบจริงแล้ว) — เราต้องการ .ttf/.otf ไปใช้กับ PyMuPDF insert_text ผ่าน
fontfile ซึ่งต้องการ TrueType/OpenType โดยตรง (จะฝัง .woff2 ไม่ได้) แทนที่จะพึ่ง UA ตัวเดียวตายตัว
(ซึ่งพังได้ถ้า Google เปลี่ยนตารางจำแนก UA อีกในอนาคต) จึงลองหลาย UA เรียงตามลำดับ (ดู _CANDIDATE_UAS)
ใช้ตัวแรกที่ได้ผล — และ log ตัวอย่าง response ไว้ตอนล้มเหลวทั้งหมด เผื่อ format เปลี่ยนอีกจะได้ debug
ได้ทันทีจาก log โดยไม่ต้องรอผู้ใช้ทดสอบซ้ำ

หมายเหตุอีกเรื่อง: font บางตัว (โดยเฉพาะที่รองรับหลายภาษา) Google Fonts จะแยก response เป็นหลาย
@font-face block ตาม unicode-range ของแต่ละสคริปต์ (เช่น thai/latin/vietnamese คนละไฟล์กัน) — ถ้าหยิบ
url แรกที่เจอในสตริงเฉยๆ อาจได้ไฟล์ของสคริปต์อื่นที่ไม่มี glyph ไทยเลยมาใช้แทน (ดาวน์โหลด "สำเร็จ" แต่ยัง
วาดภาษาไทยไม่ได้อยู่ดี) จึงต้องแยก parse ทีละ block แล้วเลือก block ที่ unicode-range ครอบคลุมอักษรไทย
(U+0E00-0E7F) ก่อนเสมอ (ดู _extract_font_url)
"""
from __future__ import annotations

import json
import os
import logging
import re
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF — ใช้ fitz.Font(fontbuffer=...) validate ไฟล์ฟอนต์ที่ผู้ใช้อัปโหลดเอง (ดู
# install_custom_font ด้านล่าง — ข้อ "ติดตั้งฟอนต์ใหม่" ที่ผู้ใช้แจ้งเพิ่ม กรณีมีฟอนต์ที่ซื้อมาเอง)

logger = logging.getLogger("fonts")

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_GOOGLE_CACHE_DIR = _FONTS_DIR / "google_cache"
# โฟลเดอร์เก็บไฟล์ฟอนต์ที่ผู้ใช้ติดตั้งเอง จะถูกแยกตาม user_id
from app.core.config import settings

def _get_user_fonts_dir(user_id: int) -> Path:
    d = settings.UPLOAD_DIR / "users" / str(user_id) / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _get_user_manifest_path(user_id: int) -> Path:
    return _get_user_fonts_dir(user_id) / "manifest.json"

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# User-Agent ที่ลองเรียงตามลำดับ (ดูหมายเหตุหัวไฟล์ "user-agent เก่า") — เบราว์เซอร์เก่ามากๆ ที่เคยรองรับ
# แค่ .ttf (ไม่มี .woff/.woff2 เลย) กับ UA ที่ไม่มีข้อมูลเบราว์เซอร์ชัดเจน (คล้าย bot/สคริปต์) ซึ่ง Google
# มักตอบกลับด้วยฟอร์แมตที่ปลอดภัยที่สุดเมื่อจำแนกไม่ได้ — ลองหลายตัวเผื่อ Google เปลี่ยนตาราง mapping อีก
_CANDIDATE_UAS = [
    "Mozilla/5.0 (Linux; U; Android 2.3.6; en-us; Nexus S Build/GRK39F) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1",
    "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/534.34 (KHTML, like Gecko)",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0)",
    "Mozilla/5.0",
]

_FONT_FACE_BLOCK_RE = re.compile(r"@font-face\s*\{([^}]*)\}", re.IGNORECASE | re.DOTALL)
_URL_IN_BLOCK_RE = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+?\.(?:ttf|otf))\)")
_UNICODE_RANGE_RE = re.compile(r"unicode-range:\s*([^;]+);", re.IGNORECASE)


@dataclass(frozen=True)
class FontOption:
    key: str            # ใช้อ้างอิงจาก frontend (TextEditRequest.fontname) — คือค่า "flat key" ตัวจริงที่
                         # resolve_font_path ใช้เรนเดอร์ ไม่เปลี่ยนความหมายแม้จะมีแนวคิด "font family"
                         # เพิ่มมาแล้ว (ดูหมายเหตุ FontOption/FONT_OPTIONS ด้านบน — ผู้ใช้แจ้งขอเพิ่ม
                         # "ติดตั้งฟอนต์ใหม่ให้เลือกได้หลายสไตล์ต่อ 1 family เหมือน Bold/Italic/Bold
                         # Italic บน toolbar" การจัดกลุ่มเป็น family เป็นแค่ชั้นข้อมูลเพิ่มเติมสำหรับ UI
                         # เท่านั้น ไม่แตะ pipeline การเรนเดอร์เดิมเลย เพื่อไม่ให้เอกสารที่เคยแก้ไข/เซ็น
                         # ไปแล้วด้วย fontname (flat key) เดิม เปิดมาแก้ไขต่อไม่ได้)
    label: str           # ชื่อที่โชว์ใน dropdown ฝั่ง UI (แบบ flat เดิม เช่น "Sarabun Bold")
    filename: str        # ชื่อไฟล์ font relative กับ app/assets/fonts/ (รวม google_cache/... ได้ด้วย) สำหรับ global fonts หรือ absolute path สำหรับ user fonts
    is_absolute: bool = False # True ถ้า filename เป็น absolute path ของ user custom font


# สไตล์ของฟอนต์ 1 family ที่รองรับ — ตรงกับปุ่ม Bold/Italic/Bold Italic บน toolbar ที่ผู้ใช้อ้างถึง
# (Underline ไม่ใช่ font variant จึงไม่อยู่ในนี้ — ดูหมายเหตุใน claude/pending-requests.md ข้อ Underline)
_VALID_STYLES = ("regular", "bold", "italic", "bold_italic")
_STYLE_LABEL_SUFFIX = {"regular": "", "bold": " Bold", "italic": " Italic", "bold_italic": " Bold Italic"}
_STYLE_KEY_SUFFIX = {"regular": "", "bold": "-bold", "italic": "-italic", "bold_italic": "-bolditalic"}

import re

def _parse_bundled_font_filename(filename: str) -> tuple[str, str, str]:
    """Parse font filename to (Family Name, Style, slugified family)"""
    stem = Path(filename).stem
    if "-" in stem:
        family, style_raw = stem.rsplit("-", 1)
    else:
        family = stem
        style_raw = "Regular"
        if " Bold Italic" in family or "BoldItalic" in family:
            style_raw = "BoldItalic"
            family = family.replace(" Bold Italic", "").replace("BoldItalic", "").strip()
        elif " Bold" in family:
            style_raw = "Bold"
            family = family.replace(" Bold", "").strip()
        elif " Italic" in family:
            style_raw = "Italic"
            family = family.replace(" Italic", "").strip()

    style_raw = style_raw.lower().replace(" ", "")
    if style_raw in ("regular", "normal", ""):
        style = "regular"
    elif style_raw == "bold":
        style = "bold"
    elif style_raw == "italic":
        style = "italic"
    elif style_raw in ("bolditalic", "italicbold"):
        style = "bold_italic"
    else:
        style = "regular"
        family = stem
        
    family_slug = re.sub(r'[^a-z0-9]+', '', family.lower())
    
    return family, style, family_slug

_BUNDLED_FAMILY_STYLES: dict[str, dict[str, str]] = {}
GLOBAL_FONT_OPTIONS: list[FontOption] = []
_DEFAULT_KEY = "sarabun"

# Auto-scan bundled fonts in app/assets/fonts
for _f in _FONTS_DIR.iterdir():
    if _f.is_file() and _f.suffix.lower() in ('.ttf', '.otf'):
        _fam_label, _sty, _fam_slug = _parse_bundled_font_filename(_f.name)
        
        if _fam_slug not in _BUNDLED_FAMILY_STYLES:
            _BUNDLED_FAMILY_STYLES[_fam_slug] = {}
            
        _key = _fam_slug if _sty == "regular" else f"{_fam_slug}-{_sty.replace('_', '')}"
        _label = _fam_label if _sty == "regular" else f"{_fam_label} {_sty.replace('_', ' ').title()}"
        
        _BUNDLED_FAMILY_STYLES[_fam_slug][_sty] = _key
        GLOBAL_FONT_OPTIONS.append(FontOption(_key, _label, _f.name))

# Ensure fallback default exists even if folder is empty
if not any(opt.key == _DEFAULT_KEY for opt in GLOBAL_FONT_OPTIONS):
    _DEFAULT_KEY = GLOBAL_FONT_OPTIONS[0].key if GLOBAL_FONT_OPTIONS else "sarabun"
    
GLOBAL_BY_KEY: dict[str, FontOption] = {f.key: f for f in GLOBAL_FONT_OPTIONS}
_lock = threading.Lock()

# font ไทยยอดนิยมจาก Google Fonts ที่จะลองดาวน์โหลดมาเพิ่ม (key, label, ชื่อ family ตามที่ Google Fonts ใช้ใน query string)
_GOOGLE_FONTS = [
    ("noto-sans-thai", "Noto Sans Thai (Google Fonts)", "Noto+Sans+Thai"),
    ("prompt", "Prompt (Google Fonts)", "Prompt"),
    ("mitr", "Mitr (Google Fonts)", "Mitr"),
]


def _register_font(opt: FontOption) -> None:
    with _lock:
        if opt.key in GLOBAL_BY_KEY:
            return
        GLOBAL_FONT_OPTIONS.append(opt)
        GLOBAL_BY_KEY[opt.key] = opt


def is_global_font(key: str | None) -> bool:
    """ฟอนต์ที่มากับระบบหรือดาวน์โหลดจาก Google Fonts (ไม่ใช่ของผู้ใช้คนใดคนหนึ่ง)"""
    with _lock:
        return (key or "").lower() in GLOBAL_BY_KEY


def resolve_font_path(key: str | None, user_id: int | None = None) -> tuple[str, str]:
    """คืน (key ที่ resolve แล้ว, path เต็มของไฟล์ font)"""
    search_key = (key or "").lower()
    with _lock:
        opt = GLOBAL_BY_KEY.get(search_key)

    if not opt and user_id is not None:
        user_fonts = _load_user_fonts_by_key(user_id)
        opt = user_fonts.get(search_key)

    if not opt:
        opt = GLOBAL_BY_KEY[_DEFAULT_KEY]

    if opt.is_absolute:
        path = Path(opt.filename)
    else:
        path = _FONTS_DIR / opt.filename

    if not path.exists():
        # กันพังตอน deploy ที่ยังไม่ได้ก็อปปี้ font ลงไป — fallback กลับไป base-14 latin
        # (จะไม่มี glyph ไทย แต่ดีกว่า error 500 ทั้งฟีเจอร์)
        return "helv", ""
    return opt.key, str(path)


# แผนที่ keyword → font key สำหรับ match_pdf_font_name
# ลำดับสำคัญ: ชื่อเฉพาะเจาะจงก่อน keyword กว้างทีหลัง
_PDF_FONT_KEYWORD_MAP: list[tuple[str, str]] = [
    # TH Sarabun New / PSK / IT๙ (ฟอนต์ราชการไทย) → Sarabun (Google Fonts, OFL) ซึ่งออกแบบมาจากตระกูลเดียวกัน
    # (ไม่ได้แนบไฟล์ TH Sarabun New มากับระบบ — ผู้ใช้ติดตั้งเองได้ที่เมนู ติดตั้งฟอนต์ ถ้ามีสิทธิ์ใช้)
    ("thsarabun",  "sarabun"),
    ("sarabunpsk", "sarabun"),
    # Google Fonts ไทย
    ("notosansthai", "noto-sans-thai"),
    ("notosans",     "noto-sans-thai"),
    ("kanit",        "kanit"),
    ("prompt",       "prompt"),
    ("mitr",         "mitr"),
    # Sarabun (ต้องอยู่หลัง sarabunpsk และ thsarabun)
    ("sarabun",      "sarabun"),
    # Latin fonts ทั่วไป → fallback ไทย (เพราะ PDF มักมีข้อความไทยด้วย)
    ("arial",        "sarabun"),
    ("helvetica",    "sarabun"),
    ("times",        "sarabun"),
    ("courier",      "sarabun"),
    ("tahoma",       "sarabun"),
    ("verdana",      "sarabun"),
    ("calibri",      "sarabun"),
    ("corbel",       "sarabun"),
    # ชื่อขึ้นต้นด้วย TH หรือมี Thai → fallback Sarabun
    ("thai",         "sarabun"),
]

# คำบอกน้ำหนัก/ตัวเอียงในชื่อฟอนต์ของ PDF — ตรวจเป็น "คำ" ในส่วน style เท่านั้น (ไม่ใช่ substring ทั้งชื่อ):
# เดิมหา "it"/"bd" ทั้งชื่อ → "Kanit", "Mitr", "TH SarabunIT๙" ถูกมองเป็นตัวเอียง (Kanit Bold เลยเสียตัวหนา)
_BOLD_WORDS = frozenset(("bold", "demi", "demibold", "semibold", "heavy", "black", "extrabold", "ultrabold"))
_ITALIC_WORDS = frozenset(("italic", "oblique", "slanted", "slant"))
_ABBREV_BOLD, _ABBREV_ITALIC = "Bd", "It"   # ตัวย่อ ต้องเป็น "Bd"/"It" ตัวพิมพ์ตามนี้ ("IT" ใน SarabunIT๙ ไม่ใช่)
_CAMEL = re.compile(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?![a-z])|\d+")


def _style_words(name: str) -> tuple[str, list[str]]:
    """แยกชื่อฟอนต์ (ตัด subset prefix แล้ว) เป็น (ชื่อตระกูล, คำในส่วน style)
    'Arial-BoldItalicMT' → ('Arial', ['Bold','Italic','MT']) · 'KanitBold' → ('Kanit', ['Bold']) ·
    'THSarabunNew,Bold' → ('THSarabunNew', ['Bold']) · 'THSarabunIT9' → ('THSarabunIT9', [])"""
    parts = re.split(r"[-,]", name)
    if len(parts) > 1:
        return "".join(parts[:-1]), _CAMEL.findall(parts[-1])
    words = _CAMEL.findall(name)
    tail = []
    while len(words) > 1 and (words[-1].lower() in _BOLD_WORDS | _ITALIC_WORDS or words[-1] in (_ABBREV_BOLD, _ABBREV_ITALIC)):
        tail.insert(0, words.pop())
    return ("".join(words) if tail else name), tail


def _detect_style_from_name(name: str) -> tuple[bool, bool]:
    """ตรวจ bold/italic จากคำในส่วน style ของชื่อฟอนต์ (ชื่อจริง ไม่ normalize)"""
    _family, words = _style_words(name)
    is_bold = any(w.lower() in _BOLD_WORDS or w == _ABBREV_BOLD for w in words)
    is_italic = any(w.lower() in _ITALIC_WORDS or w == _ABBREV_ITALIC for w in words)
    return is_bold, is_italic


def _apply_style_suffix(base_key: str, is_bold: bool, is_italic: bool) -> str:
    """เพิ่ม style suffix เข้าไปใน key ถ้ามี variant นั้นอยู่ในระบบ ถ้าไม่มีคืน base_key"""
    if is_bold and is_italic:
        candidate = f"{base_key}-bolditalic"
    elif is_bold:
        candidate = f"{base_key}-bold"
    elif is_italic:
        candidate = f"{base_key}-italic"
    else:
        return base_key
    with _lock:
        return candidate if candidate in GLOBAL_BY_KEY else base_key


def match_pdf_font_name(
    pdf_font_name: str,
    flag_bold: bool = False,
    flag_italic: bool = False,
) -> str:
    """รับชื่อ font จาก PDF (เช่น 'ABCDEF+SarabunPSK-Bold', 'ArialMT', 'KanitRegular')
    แล้วคืน key ของ font ที่ใกล้เคียงที่สุดที่มีอยู่ในระบบ (GLOBAL_BY_KEY หรือ Google cache)

    ลำดับการ match:
      1. Strip subset prefix (XXXXXX+) และ normalize
      2. Exact key match กับ GLOBAL_BY_KEY
      3. Substring match กับ _PDF_FONT_KEYWORD_MAP (เรียงจากเฉพาะเจาะจง → กว้าง)
      4. Style-aware: ตรวจ bold/italic จากชื่อ + span flags แล้วเพิ่ม suffix
      5. Fallback → _DEFAULT_KEY (sarabun)
    """
    if not pdf_font_name:
        return _apply_style_suffix(_DEFAULT_KEY, flag_bold, flag_italic)

    # 1) Strip subset prefix "ABCDEF+"
    name = pdf_font_name
    if "+" in name:
        name = name.split("+", 1)[1]

    # 2) Normalize: lowercase, ลบอักขระที่ไม่ใช่ตัวอักษร/ตัวเลข
    norm = re.sub(r"[^a-z0-9]", "", name.lower())

    # 3) Exact key match (กรณีชื่อ font ตรงกับ key ในระบบพอดี)
    #    ⚠️ ต้อง release _lock ก่อนเรียก _apply_style_suffix เพราะ Lock ไม่ reentrant
    with _lock:
        exact_hit = norm in GLOBAL_BY_KEY
    if exact_hit:
        return _apply_style_suffix(norm, flag_bold, flag_italic)

    # 4) ตรวจ bold/italic จากชื่อ PDF ด้วย (เพิ่มเติมจาก span flags)
    name_bold, name_italic = _detect_style_from_name(name)
    is_bold = flag_bold or name_bold
    is_italic = flag_italic or name_italic

    # ใช้เฉพาะชื่อตระกูล (ตัดส่วน style ออก) ตอน match keyword
    norm_family = re.sub(r"[^a-z0-9]", "", _style_words(name)[0].lower())

    # 5) Keyword substring match
    for keyword, base_key in _PDF_FONT_KEYWORD_MAP:
        if keyword in norm_family or keyword in norm:
            with _lock:
                key_exists = base_key in GLOBAL_BY_KEY
            if key_exists:
                return _apply_style_suffix(base_key, is_bold, is_italic)
            # base_key ไม่มีในระบบ (เช่น noto-sans-thai ยังไม่ได้ดาวน์โหลด) → ลอง sarabun
            break

    # 6) Fallback
    return _apply_style_suffix(_DEFAULT_KEY, is_bold, is_italic)


def _cache_relative_path(key: str) -> str:
    return f"google_cache/{key}.ttf"


def _looks_like_thai_range(range_str: str) -> bool:
    """เช็คว่า unicode-range (รูปแบบของ Google Fonts เช่น "U+0E01-0E5B, U+200C-200D, U+25CC") มีช่วง
    ที่ครอบคลุมบล็อกอักษรไทย (U+0E00-0E7F) หรือเปล่า — ใช้เลือก @font-face block ที่ถูกต้องตอนมีหลาย
    subset ปนกัน (ดูหมายเหตุหัวไฟล์)
    """
    for part in range_str.split(","):
        part = part.strip().upper().replace("U+", "")
        start_hex, _, end_hex = part.partition("-")
        end_hex = end_hex or start_hex
        try:
            start, end = int(start_hex, 16), int(end_hex, 16)
        except ValueError:
            continue
        if start <= 0x0E7F and end >= 0x0E00:
            return True
    return False


def _extract_font_url(css_text: str) -> str | None:
    """ดึงลิงก์ไฟล์ font (.ttf/.otf) จาก CSS ที่ Google Fonts ส่งกลับ — ถ้ามีหลาย @font-face block
    (แยกตาม unicode-range ของแต่ละสคริปต์) เลือก block ที่ unicode-range ครอบคลุมอักษรไทยก่อนเสมอ
    (หรือ block ที่ไม่ระบุ unicode-range เลย = font เดียวครอบคลุมทุกตัวอักษร) ไม่งั้นอาจได้ไฟล์ font
    ของสคริปต์อื่นที่ไม่มี glyph ไทยมาใช้แทน คืน None ถ้าไม่เจอ url ของ .ttf/.otf เลยสักอัน (เช่น
    ได้ .woff2 กลับมาแทนทั้งหมด — UA นี้ใช้ไม่ได้ผล ลอง UA ถัดไป)
    """
    blocks = _FONT_FACE_BLOCK_RE.findall(css_text)
    if not blocks:
        match = _URL_IN_BLOCK_RE.search(css_text)
        return match.group(1) if match else None

    fallback_url: str | None = None
    for block in blocks:
        url_match = _URL_IN_BLOCK_RE.search(block)
        if not url_match:
            continue
        if fallback_url is None:
            fallback_url = url_match.group(1)
        range_match = _UNICODE_RANGE_RE.search(block)
        if range_match and _looks_like_thai_range(range_match.group(1)):
            return url_match.group(1)
        if not range_match:
            return url_match.group(1)
    return fallback_url


def _download_google_font(key: str, family_param: str, timeout: float) -> bool:
    """ดาวน์โหลด font หนึ่งตัวจาก Google Fonts มาเก็บที่ app/assets/fonts/google_cache/<key>.ttf
    ถ้าเคย cache ไว้แล้ว (ไฟล์มีอยู่และไม่ว่างเปล่า) จะไม่ออกเน็ตซ้ำเลย (ตามที่ผู้ใช้แจ้ง — เก็บ local
    ได้ก็ใช้ local แทน) คืน True ถ้ามีไฟล์ที่ใช้งานได้แล้ว (ไม่ว่าจะ cache เดิมหรือดาวน์โหลดสำเร็จใหม่)

    ลองหลาย User-Agent เรียงตามลำดับ (ดูหมายเหตุหัวไฟล์) ใช้ตัวแรกที่ได้ url ไฟล์ .ttf/.otf กลับมาจริง —
    ถ้าล้มเหลวหมดทุกตัว log ตัวอย่าง response/error ล่าสุดไว้ (debug ได้จาก log โดยตรงถ้า format เปลี่ยน
    อีกในอนาคต โดยไม่ต้องรอผู้ใช้ทดสอบซ้ำอีกรอบ)
    """
    cache_path = _FONTS_DIR / _cache_relative_path(key)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return True

    css_url = f"https://fonts.googleapis.com/css2?family={family_param}&display=swap"
    last_detail = ""

    for ua in _CANDIDATE_UAS:
        try:
            req = urllib.request.Request(css_url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                css_text = resp.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            last_detail = f"ขอ CSS ไม่สำเร็จ ({exc})"
            continue

        font_url = _extract_font_url(css_text)
        if not font_url:
            last_detail = f"ไม่พบ .ttf/.otf ใน response (ตัวอย่าง: {css_text[:200]!r})"
            continue

        try:
            req2 = urllib.request.Request(font_url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                data = resp2.read()
        except Exception as exc:
            last_detail = f"ดาวน์โหลดไฟล์ font ไม่สำเร็จ ({exc})"
            continue

        if not data:
            last_detail = "ดาวน์โหลดไฟล์ font ได้ข้อมูลว่างเปล่า"
            continue

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # เขียนไฟล์ชั่วคราวแล้วสลับทีเดียว — หลาย worker เริ่มพร้อมกันจะไม่อ่านเจอไฟล์ที่เขียนไม่เสร็จ
        tmp = cache_path.with_name(f".{cache_path.name}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, cache_path)
        return True

    logger.info(
        "Google Fonts: ดาวน์โหลด %s ไม่สำเร็จหลังลองทุก User-Agent (%d แบบ) — ใช้ font ที่ bundle มากับ"
        "แอปแทน (รายละเอียดล่าสุด: %s)",
        family_param,
        len(_CANDIDATE_UAS),
        last_detail,
    )
    return False


def sync_google_fonts(timeout: float = 3.0) -> None:
    """เรียกครั้งเดียวตอนแอปเริ่มทำงาน (best-effort, non-blocking — ดู app/main.py) ไล่ดาวน์โหลด/
    ตรวจ cache ของ font ไทยจาก Google Fonts (ดู _GOOGLE_FONTS) แล้วเพิ่มเข้า FONT_OPTIONS ให้เลือกใช้
    ได้ทันทีถ้าสำเร็จ — ล้มเหลว (ไม่มีเน็ต ฯลฯ) ก็แค่ไม่มี option เพิ่ม ไม่กระทบฟีเจอร์เดิม"""
    for key, label, family_param in _GOOGLE_FONTS:
        if key in GLOBAL_BY_KEY:
            continue
        if _download_google_font(key, family_param, timeout):
            _register_font(FontOption(key=key, label=label, filename=_cache_relative_path(key)))
            logger.info("Google Fonts: พร้อมใช้งาน %s (%s)", label, key)


# ---------- ติดตั้งฟอนต์ใหม่เอง (เมนู File > ติดตั้งฟอนต์ใหม่... — ผู้ใช้แจ้งขอ กรณีมีฟอนต์ที่ซื้อมาเอง
# ต้องการใช้เพิ่มจากที่ bundle มากับแอป และลบออกได้ถ้าไม่ต้องการแล้ว) ----------


def _slugify(text: str) -> str:
    """แปลงชื่อฟอนต์เป็น key ที่ใช้ในระบบ (a-z0-9 กับขีดกลางเท่านั้น) — รองรับชื่อภาษาไทย/มีอักขระพิเศษ
    โดยถ้าแปลงแล้วไม่เหลืออะไรเลย (เช่น ชื่อเป็นภาษาไทยล้วน ไม่มี a-z/0-9 ปน) จะได้ "font" เป็นค่าเริ่มต้น
    แทน — คนละ key กันด้วย _dedupe suffix ที่ install_custom_font ต่อท้ายให้อยู่แล้ว"""
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "font"


def _read_custom_manifest(user_id: int) -> list[dict]:
    manifest_path = _get_user_manifest_path(user_id)
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        logger.warning(f"fonts: อ่าน manifest.json ของฟอนต์ที่ติดตั้งเองไม่สำเร็จของ user {user_id} (ไฟล์เสีย?) — ถือว่าไม่มีฟอนต์ที่ติดตั้งเองเลย")
        return []


def _write_custom_manifest(user_id: int, entries: list[dict]) -> None:
    manifest_path = _get_user_manifest_path(user_id)
    manifest_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry_family_key(entry: dict) -> str:
    """คืน family key ของ manifest entry หนึ่งรายการ — รองรับของเก่าก่อนรอบนี้ที่ manifest ยังไม่มี
    ฟิลด์ "family" เลย (ตอนนั้นติดตั้งได้ทีละไฟล์ ไม่มีแนวคิด family) ถือว่าฟอนต์เหล่านั้นเป็น family
    เดี่ยวๆ ของตัวเอง (family key = key ของตัวเอง มีแค่สไตล์ regular) กันฟอนต์เก่าหายไปจากรายการหลัง
    อัปเดตรอบนี้"""
    return entry.get("family") or entry.get("key") or ""


def _family_entries(family_key: str, user_id: int) -> list[dict]:
    return [e for e in _read_custom_manifest(user_id) if _entry_family_key(e) == family_key]


def _family_label(family_key: str, user_id: int, entries: list[dict] | None = None) -> str:
    entries = entries if entries is not None else _family_entries(family_key, user_id)
    for e in entries:
        if (e.get("style") or "regular") == "regular":
            return e.get("label") or family_key
    if entries:
        return entries[0].get("label") or family_key
    return family_key


def list_custom_families(user_id: int) -> list[dict]:
    """คืนรายชื่อฟอนต์ที่ผู้ใช้ติดตั้งเอง จัดกลุ่มเป็น family: [{"key", "label", "styles": {สไตล์: font
    option key}}, ...] ใช้ทั้งตอนแสดงรายการ "ฟอนต์ที่ติดตั้งเองไว้แล้ว" และตอนเลือก family เดิมจะเพิ่ม
    สไตล์ใหม่เข้าไปใน InstallFontModal.jsx"""
    groups: dict[str, dict] = {}
    for entry in _read_custom_manifest(user_id):
        key = entry.get("key")
        if not key:
            continue
        family_key = _entry_family_key(entry)
        style = entry.get("style") or "regular"
        if style not in _VALID_STYLES:
            style = "regular"
        group = groups.setdefault(family_key, {"key": family_key, "label": family_key, "styles": {}})
        group["styles"][style] = key
    for family_key, group in groups.items():
        group["label"] = _family_label(family_key, user_id, entries=None)
    return sorted(groups.values(), key=lambda g: g["label"].lower())


def _load_user_fonts_by_key(user_id: int) -> dict[str, FontOption]:
    user_fonts = {}
    fonts_dir = _get_user_fonts_dir(user_id)
    for entry in _read_custom_manifest(user_id):
        key, label, filename = entry.get("key"), entry.get("label"), entry.get("filename")
        if not (key and label and filename):
            continue
        font_path = fonts_dir / filename
        if not font_path.exists():
            continue
        user_fonts[key] = FontOption(key=key, label=label, filename=str(font_path), is_absolute=True)
    return user_fonts


def is_removable(key: str, user_id: int) -> bool:
    """True เฉพาะฟอนต์ที่ผู้ใช้ติดตั้งเอง — ฟอนต์ที่ bundle มากับแอปหรือมาจาก Google Fonts ลบไม่ได้"""
    return key in _load_user_fonts_by_key(user_id)

def get_font_options(user_id: int) -> list[FontOption]:
    user_fonts = _load_user_fonts_by_key(user_id)
    return GLOBAL_FONT_OPTIONS + list(user_fonts.values())


def list_font_families(user_id: int) -> list[dict]:
    """คืนรายชื่อฟอนต์จัดกลุ่มเป็น "1 family เลือกสไตล์ได้" ..."""
    families: list[dict] = []

    for family_key, styles in _BUNDLED_FAMILY_STYLES.items():
        available = {style: key for style, key in styles.items() if key in GLOBAL_BY_KEY}
        if "regular" not in available:
            continue
        base_label = GLOBAL_BY_KEY[available["regular"]].label
        families.append({
            "key": family_key,
            "label": base_label,
            "removable": False,
            "styles": {s: available.get(s) for s in _VALID_STYLES},
        })

    for key, label, _param in _GOOGLE_FONTS:
        if key in GLOBAL_BY_KEY:
            families.append({
                "key": key,
                "label": label,
                "removable": False,
                "styles": {"regular": key, "bold": None, "italic": None, "bold_italic": None},
            })

    for group in list_custom_families(user_id):
        families.append({
            "key": group["key"],
            "label": group["label"],
            "removable": True,
            "styles": {s: group["styles"].get(s) for s in _VALID_STYLES},
        })

    return families


_glyph_cache: dict[str, fitz.Font] = {}


def missing_core_glyphs(font_path: str, text: str) -> list[str]:
    """ตัวอักษรไทย/อังกฤษ/ตัวเลข/เครื่องหมายพื้นฐานใน text ที่ฟอนต์ไม่มี (ไม่ซ้ำ ตามลำดับที่พบ)
    — ไม่นับสัญลักษณ์อื่น (อีโมจิ ✓ ฯลฯ) ซึ่งฟอนต์ส่วนใหญ่ไม่มีอยู่แล้ว"""
    try:
        font = _glyph_cache.get(font_path)
        if font is None:
            font = _glyph_cache[font_path] = fitz.Font(fontfile=font_path)
    except Exception:
        return []
    out = []
    for ch in dict.fromkeys(text):
        cp = ord(ch)
        core = 0x21 <= cp <= 0x7E or 0x0E01 <= cp <= 0x0E5B
        if core and not font.has_glyph(cp):
            out.append(ch)
    return out


def font_label(key: str, user_id: int | None = None) -> str:
    try:
        for opt in get_font_options(user_id):
            if opt.key == key:
                return opt.label
    except Exception:
        pass
    return key


MAX_FONT_FILE_BYTES = 20 * 1024 * 1024   # ฟอนต์ไทยทั่วไป < 1 MB · ฟอนต์จีน/ญี่ปุ่นใหญ่สุดราว 15–20 MB
MAX_CUSTOM_FONT_FILES = 100              # ต่อผู้ใช้ (ทุกสไตล์รวมกัน)
MAX_FONT_LABEL = 80
_FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2")


@dataclass
class FontFileInfo:
    data: bytes          # ไบต์ที่จะเก็บ (WOFF/WOFF2 แปลงเป็น TTF/OTF แล้ว)
    ext: str             # ".ttf" | ".otf"
    has_thai: bool
    restricted: bool     # ผู้ออกแบบตั้งว่าห้ามฝังลงเอกสาร (OS/2 fsType = Restricted License)
    name: str


def inspect_font_file(file_bytes: bytes, original_filename: str) -> FontFileInfo:
    """ตรวจไฟล์ฟอนต์ที่ผู้ใช้อัปโหลด — โยน ValueError (ข้อความไทย) ถ้าใช้ไม่ได้

    - .ttf / .otf และ .woff / .woff2 (ฟอนต์สำหรับเว็บ — แปลงเป็น .ttf/.otf ให้)
    - ไม่รับ .ttc (หลายฟอนต์ในไฟล์เดียว — เดิมรับถ้าตั้งนามสกุล .otf แล้วใช้ได้แค่ฟอนต์แรก หน้าตัวอย่างในเบราว์เซอร์ไม่แสดง)
    - บอกว่ามีตัวอักษรไทยไหม และผู้ออกแบบห้ามฝังลงเอกสารหรือเปล่า (ให้หน้าจอเตือน)"""
    import io

    from fontTools.ttLib import TTFont, TTLibError

    ext = Path(original_filename or "").suffix.lower()
    if ext == ".ttc" or file_bytes[:4] == b"ttcf":
        raise ValueError("ไฟล์นี้เป็นชุดฟอนต์หลายตัวในไฟล์เดียว (.ttc) ซึ่งยังไม่รองรับ — ใช้ไฟล์ .ttf หรือ .otf ของแต่ละสไตล์แทน")
    if ext not in _FONT_EXTS:
        raise ValueError("รองรับเฉพาะไฟล์ฟอนต์ .ttf, .otf, .woff หรือ .woff2")
    if not file_bytes:
        raise ValueError("ไฟล์ฟอนต์ว่างเปล่า")
    if len(file_bytes) > MAX_FONT_FILE_BYTES:
        raise ValueError(f"ไฟล์ฟอนต์ใหญ่เกิน {MAX_FONT_FILE_BYTES // (1024 * 1024)} MB")
    if file_bytes[:4] == b"ttcf":
        raise ValueError("ไฟล์นี้เป็นชุดฟอนต์หลายตัวในไฟล์เดียว (.ttc) ซึ่งยังไม่รองรับ — ใช้ไฟล์ .ttf หรือ .otf ของแต่ละสไตล์แทน")
    try:
        font = TTFont(io.BytesIO(file_bytes), lazy=False)
    except (TTLibError, Exception) as exc:  # noqa: BLE001 — ไฟล์เสียมีได้หลายแบบ
        if file_bytes[:4] == b"wOF2":
            raise ValueError("เปิดไฟล์ .woff2 ไม่สำเร็จ — ลองใช้ไฟล์ .ttf หรือ .otf แทน") from exc
        raise ValueError("ไฟล์นี้ไม่ใช่ไฟล์ฟอนต์ที่ใช้งานได้ (อาจเสียหาย หรือเปลี่ยนนามสกุลมาจากไฟล์ชนิดอื่น)") from exc
    try:
        if font.sfntVersion not in ("\x00\x01\x00\x00", "OTTO", "true"):
            raise ValueError("ไฟล์นี้ไม่ใช่ฟอนต์ TrueType/OpenType")
        cmap = font.getBestCmap() or {}
        if not cmap:
            raise ValueError("ฟอนต์นี้ไม่มีตารางตัวอักษร Unicode (ฟอนต์สัญลักษณ์/ฟอนต์เก่า) ใช้พิมพ์ข้อความไม่ได้")
        has_thai = all(cp in cmap for cp in (0x0E01, 0x0E32, 0x0E48))   # ก  า  ่
        fs_type = int(getattr(font["OS/2"], "fsType", 0)) if "OS/2" in font else 0
        restricted = (fs_type & 0x000F) == 0x0002
        name = ""
        if "name" in font:
            name = (font["name"].getBestFamilyName() or "").strip()
        if font.flavor:   # WOFF/WOFF2 → sfnt ธรรมดา (PyMuPDF/fpdf2/LibreOffice/เบราว์เซอร์ใช้ได้หมด)
            font.flavor = None
            buf = io.BytesIO()
            font.save(buf)
            file_bytes = buf.getvalue()
        out_ext = ".otf" if font.sfntVersion == "OTTO" else ".ttf"
    finally:
        font.close()
    try:
        fitz.Font(fontbuffer=file_bytes)
    except Exception as exc:
        raise ValueError(f"ไฟล์นี้ไม่ใช่ไฟล์ฟอนต์ที่ใช้งานได้ (เปิดไม่สำเร็จ: {exc})") from exc
    return FontFileInfo(file_bytes, out_ext, has_thai, restricted, name)


def install_custom_font(
    file_bytes: bytes,
    original_filename: str,
    label: str | None,
    user_id: int,
    family_key: str | None = None,
    style: str = "regular",
) -> FontOption:
    """ติดตั้งฟอนต์ใหม่จากไฟล์ที่ผู้ใช้อัปโหลด (.ttf/.otf/.woff/.woff2 — ดู inspect_font_file)
    คืน FontOption ที่มี .info (FontFileInfo) ให้ route ส่งคำเตือน (ไม่มีภาษาไทย/ห้ามฝัง) กลับไป"""
    style = (style or "regular").lower()
    if style not in _VALID_STYLES:
        raise ValueError("สไตล์ฟอนต์ไม่ถูกต้อง (ต้องเป็นตัวปกติ/ตัวหนา/ตัวเอียง/ตัวหนาเอียงเท่านั้น)")
    info = inspect_font_file(file_bytes, original_filename)
    file_bytes, ext = info.data, info.ext
    loaded = fitz.Font(fontbuffer=file_bytes)
    label = (label or "").strip()[:MAX_FONT_LABEL] or None
    digest = __import__("hashlib").sha256(file_bytes).hexdigest()

    with _lock:
        user_fonts = _load_user_fonts_by_key(user_id)
        manifest_now = _read_custom_manifest(user_id)
        if len(manifest_now) >= MAX_CUSTOM_FONT_FILES:
            raise ValueError(f"ติดตั้งฟอนต์ได้สูงสุด {MAX_CUSTOM_FONT_FILES} ไฟล์ — ลบฟอนต์ที่ไม่ใช้ก่อน")
        same = next((e for e in manifest_now if e.get("sha256") == digest), None)
        if same is not None:   # ติดตั้งไฟล์เดิมซ้ำ (เดิมได้ "ชื่อ-2" ซ้ำกันในรายการ)
            raise ValueError(f"ติดตั้งไฟล์ฟอนต์นี้ไว้แล้ว ({same.get('label') or same.get('key')})")
        if family_key:
            entries = _family_entries(family_key, user_id)
            if not entries:
                raise ValueError("ไม่พบฟอนต์ family นี้ที่ติดตั้งเองไว้ก่อนหน้า")
            if any((e.get("style") or "regular") == style for e in entries):
                raise ValueError("ฟอนต์นี้มีไฟล์สไตล์นี้อยู่แล้ว — ลบฟอนต์ทิ้งแล้วติดตั้งใหม่ถ้าต้องการเปลี่ยนไฟล์")
            fam_label = _family_label(family_key, user_id, entries)
            key = f"{family_key}{_STYLE_KEY_SUFFIX[style]}"
            if key in GLOBAL_BY_KEY or key in user_fonts:
                raise ValueError("เกิดข้อผิดพลาดในการตั้งชื่อฟอนต์ภายใน กรุณาลองใหม่อีกครั้ง")
            display_label = f"{fam_label}{_STYLE_LABEL_SUFFIX[style]}"
        else:
            if style != "regular":
                raise ValueError("ต้องอัปโหลดไฟล์ตัวปกติ (Regular) ก่อนเสมอตอนติดตั้งฟอนต์ใหม่")
            fam_label = (label or info.name or (loaded.name or "").strip() or Path(original_filename).stem)[:MAX_FONT_LABEL]
            base_slug = _slugify(fam_label)[:48].strip("-") or "font"   # ชื่อไฟล์ยาวเกินระบบไฟล์รับได้ → 500
            family_key = base_slug
            suffix = 1
            while family_key in GLOBAL_BY_KEY or family_key in user_fonts or _family_entries(family_key, user_id):
                suffix += 1
                family_key = f"{base_slug}-{suffix}"
            key = family_key
            display_label = fam_label

        filename = f"{key}{ext}"
        target_path = _get_user_fonts_dir(user_id) / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(file_bytes)

        opt = FontOption(key=key, label=display_label, filename=str(target_path), is_absolute=True)

        manifest = _read_custom_manifest(user_id)
        manifest.append({
            "key": key,
            "label": display_label,
            "filename": filename,
            "family": family_key,
            "style": style,
            "sha256": digest,
        })
        _write_custom_manifest(user_id, manifest)

    logger.info("fonts: ติดตั้งฟอนต์ใหม่สำเร็จ %s (family=%s, style=%s) for user %s", display_label, family_key, style, user_id)
    object.__setattr__(opt, "info", info)  # FontOption เป็น frozen dataclass — แนบผลตรวจไฟล์ไว้ให้ route
    return opt


def remove_custom_font_family(family_key: str, user_id: int) -> None:
    """ลบฟอนต์ที่เคยติดตั้งเองทั้ง family เดียว (ทุกสไตล์ regular/bold/italic/bold_italic ที่มีไฟล์อยู่
    จริง) ทีเดียว — เมนู File > ติดตั้งฟอนต์ใหม่... > ลบ ลบทั้ง family ไม่ใช่ทีละสไตล์ (เก็บ family ที่
    ไม่มีไฟล์ regular ไว้จะสร้างความสับสนตอนเลือกใช้ในหน้าแก้ไขข้อความ) โยน ValueError ถ้าไม่ใช่ฟอนต์ที่
    ติดตั้งเองหรือไม่พบ family นี้เลย (ฟอนต์ bundle/Google Fonts ลบไม่ได้เสมอ)"""
    with _lock:
        user_fonts = _load_user_fonts_by_key(user_id)
        entries = _family_entries(family_key, user_id)
        keys_to_remove = {e["key"] for e in entries if e.get("key")}
        if not keys_to_remove or not keys_to_remove.issubset(user_fonts.keys()):
            raise ValueError("ลบได้เฉพาะฟอนต์ที่ติดตั้งเองเท่านั้น (ฟอนต์นี้ไม่ใช่ฟอนต์ที่ติดตั้งเอง หรือไม่พบฟอนต์นี้)")

        remaining = [e for e in _read_custom_manifest(user_id) if e.get("key") not in keys_to_remove]
        _write_custom_manifest(user_id, remaining)

        fonts_dir = _get_user_fonts_dir(user_id)
        for entry in entries:
            font_path = fonts_dir / entry["filename"]
            try:
                if font_path.exists():
                    font_path.unlink()
            except Exception as exc:
                logger.warning(
                    "fonts: ลบไฟล์ฟอนต์ไม่สำเร็จ %s: %s",
                    font_path,
                    exc,
                )

    logger.info("fonts: ลบฟอนต์ family %s แล้ว (%d ไฟล์)", family_key, len(keys_to_remove))
