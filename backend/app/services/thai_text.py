"""จัดรูปข้อความภาษาไทยที่ดึงออกมาจาก PDF ให้ถูกต้อง (ใช้ร่วมกันทุกจุดที่อ่านข้อความ)

ปัญหาที่พบในไฟล์จริง (ดู scripts/thai_eval.py และ claude/plan-thai-text.md):
1. ฟอนต์ไทยรุ่นเก่า/ฟอนต์ตระกูล TH Sarabun ใช้รหัส PUA (U+F700–F71D) แทนสระ/วรรณยุกต์ที่ขยับตำแหน่ง
   (เช่น ่ ตัวต่ำเมื่อไม่มีสระบน) → map กลับเป็นอักขระไทยปกติ (ยืนยันจากชื่อ glyph uni0E48.alt2 ฯลฯ ใน THSarabunNew)
2. สระอำแตกเป็น นิคหิต + สระอา (ํ า) หรือมีวรรณยุกต์คั่น (ํ ่ า / ่ ํ า) → รวมเป็น ำ
3. Word "บันทึกเป็น PDF" กับ TH SarabunPSK: วงกลมของสระอำ (นิคหิต) ถูกดึงออกมาเป็นช่องว่าง → "จ าเป็น" = จำเป็น
   (ช่องว่าง + สระอา ไม่มีในภาษาไทยจริง เพราะ า ขึ้นต้นพยางค์ไม่ได้)
4. ฟอนต์บางตัว (เช่น THSarabunNew ในหนังสือราชการ) ToUnicode ผิด: glyph สระอา ถูก map เป็น ำ
   → "ส ำนักงำน" = สำนักงาน (ำ ที่มีช่องว่างนำหน้า = สระอำจริง, ำ อื่นๆ = สระอา) — ตัดสินเป็นรายฟอนต์ต่อหน้า
   ด้วยพจนานุกรม (แก้แล้วข้อความเป็นคำที่มีอยู่จริงมากขึ้นชัดเจนเท่านั้น) ดู detect_misencoded_am_fonts
5. วงกลมของสระอำถูกวาดเป็นเส้น (vector) แยกจากตัวอักษร → ข้อความเหลือ "สาหรับ" — ตรวจหาวงกลมเล็กเหนือ-ซ้าย
   ของสระอา (ตำแหน่งนิคหิตใน glyph ำ ของ Sarabun/TH Sarabun/Kanit) จาก page.get_drawings() ดู vector_am_flags
   และนิคหิตที่ไม่มี Unicode (ดึงออกมาเป็น U+FFFD) ติดกับสระอา
6. สระ/วรรณยุกต์สลับลำดับ (่ ิ → ิ ่), ำ มาก่อนวรรณยุกต์ (ำ ้ → ้ ำ), สระเอสองตัว (เ เ → แ),
   เครื่องหมายซ้ำ, zero-width chars, ช่องว่างหน้าสระ/วรรณยุกต์

หลักการ: ทำงานบน "รายการอักขระ" แล้วคืนรายการยาวเท่าเดิม (ตัวที่ถูกรวม/ลบเป็นสตริงว่าง) เพื่อให้แต่ละตัว
ยังผูกกับกรอบ (bbox) เดิมได้ — ใช้กับ rawdict (ไฮไลท์/คัดลอก/PDPA) ได้โดยตำแหน่งไม่เพี้ยน
ห้ามใช้ NFKC กับข้อความไทย (แยก ำ เป็น ํ + า)
"""
from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Iterable, Optional, Sequence

# ---------------------------------------------------------------- ตารางอักขระ

# PUA ของฟอนต์ไทย (Mac/Adobe/WTT) → อักขระมาตรฐาน — ตรงกับชื่อ glyph ใน THSarabunNew (uni0E48.alt1 ฯลฯ)
PUA_MAP = {
    0xF700: "ฐ",  # ฐ ไม่มีเชิง
    0xF701: "ิ", 0xF702: "ี", 0xF703: "ึ", 0xF704: "ื",  # ิ ี ึ ื เยื้องซ้าย
    0xF705: "่", 0xF706: "้", 0xF707: "๊", 0xF708: "๋", 0xF709: "์",  # ่ ้ ๊ ๋ ์ ต่ำ-ซ้าย
    0xF70A: "่", 0xF70B: "้", 0xF70C: "๊", 0xF70D: "๋", 0xF70E: "์",  # ต่ำ
    0xF70F: "ญ",  # ญ ไม่มีเชิง
    0xF710: "ั", 0xF711: "ํ", 0xF712: "็",  # ั ํ ็ เยื้องซ้าย
    0xF713: "่", 0xF714: "้", 0xF715: "๊", 0xF716: "๋", 0xF717: "์",  # เยื้องซ้าย
    0xF718: "ุ", 0xF719: "ู", 0xF71A: "ฺ",  # ุ ู ฺ ต่ำลง
    0xF71B: "ฎ", 0xF71C: "ฏ", 0xF71D: "ฬ",  # ฎ ฏ ฬ ไม่มีเชิง
}
ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"}
_SPACES = {" ", "\u00a0", "\u2002", "\u2003", "\u2009", "\u202f"}

SARA_AA, SARA_AM, NIKHAHIT, SARA_E = "า", "ำ", "ํ", "เ"
TONES = set("่้๊๋")
# อันดับเครื่องหมายเหนือ/ใต้พยัญชนะตามลำดับการพิมพ์มาตรฐาน: สระบน/ล่าง → วรรณยุกต์ → ์ ํ ๎
_MARK_RANK = {c: 0 for c in "ัิีึืฺุู็"}
_MARK_RANK.update({c: 1 for c in TONES})
_MARK_RANK.update({c: 2 for c in "์ํ๎"})
MARKS = set(_MARK_RANK)


def is_thai_consonant(c: str) -> bool:
    return len(c) == 1 and "ก" <= c <= "ฮ"


def is_thai(c: str) -> bool:
    return len(c) == 1 and "ก" <= c <= "๛"


def has_thai(text: str) -> bool:
    return any("ก" <= c <= "๛" or 0xF700 <= ord(c) <= 0xF71D for c in text or "")


# ---------------------------------------------------------------- แกนหลัก


def _next(out: list[str], i: int) -> int:
    """index ของตัวถัดไปที่ยังไม่ว่าง (len(out) ถ้าไม่มี)"""
    j = i + 1
    while j < len(out) and out[j] == "":
        j += 1
    return j


def _prev(out: list[str], i: int) -> int:
    j = i - 1
    while j >= 0 and out[j] == "":
        j -= 1
    return j


def normalize_chars(chars: Sequence[str], misencoded_am: Optional[Sequence[bool]] = None,
                    vector_am: Optional[Sequence[bool]] = None) -> list[str]:
    """จัดรูปรายการอักขระ คืนรายการยาวเท่าเดิม (ตัวที่ถูกรวม/ลบเป็น "")

    misencoded_am[i] = True → อักขระตัวนั้นมาจากฟอนต์ที่ map สระอาเป็น ำ (ดู detect_misencoded_am_fonts)
    vector_am[i] = True → สระอาตัวนี้มีวงกลมนิคหิตวาดเป็นเส้นอยู่เหนือ (ดู vector_am_flags) = สระอำ
    """
    out = [c if c else "" for c in chars]
    n = len(out)

    # 0) วงกลมสระอำที่วาดเป็นเส้น / นิคหิตที่ไม่มี Unicode (U+FFFD ติดหน้าสระอา หลังพยัญชนะ)
    if vector_am is not None:
        for i, c in enumerate(out):
            if c == SARA_AA and vector_am[i]:
                out[i] = SARA_AM
    for i, c in enumerate(out):
        if c == "\ufffd" and _thai_before(out, i):
            j = _next(out, i)
            if j < n and out[j] == SARA_AA:
                out[i], out[j] = "", SARA_AM

    # 1) PUA และ zero-width
    for i, c in enumerate(out):
        if len(c) == 1:
            o = ord(c)
            if o in PUA_MAP:
                out[i] = PUA_MAP[o]
            elif c in ZERO_WIDTH or (o < 0x20 and c not in "\n\r\t"):
                # อักขระควบคุม: fpdf2 (shaping) ใส่ \x03 \x06 ต่อท้าย ำ ใน ToUnicode — PDF ที่แอปนี้เขียนเองก็เป็น
                out[i] = ""

    # 2) ฟอนต์ที่ map สระอาเป็น ำ: ำ หลังช่องว่าง (ช่องว่าง = นิคหิตที่หาย) คือสระอำจริง นอกนั้นคือสระอา
    if misencoded_am is not None:
        for i, c in enumerate(out):
            if c == SARA_AM and misencoded_am[i]:
                p = _prev(out, i)
                if not (p >= 0 and out[p] in _SPACES and _thai_before(out, p)):
                    out[i] = SARA_AA

    # 3) ช่องว่างแทนนิคหิต: พยัญชนะ (+วรรณยุกต์) + ช่องว่าง + า → ำ · ช่องว่างหน้า ำ/สระ/วรรณยุกต์ → ลบ
    for i, c in enumerate(out):
        if c not in _SPACES or not _thai_before(out, i):
            continue
        j = _next(out, i)
        if j >= n:
            continue
        if out[j] == SARA_AA:
            out[i], out[j] = "", SARA_AM
        elif out[j] == SARA_AM or out[j] in MARKS:
            out[i] = ""

    # 4) สระอำแตก: ํ (+วรรณยุกต์) + า → (วรรณยุกต์) ำ
    for i, c in enumerate(out):
        if c != NIKHAHIT:
            continue
        j = _next(out, i)
        while j < n and out[j] in TONES:
            j = _next(out, j)
        if j < n and out[j] == SARA_AA:
            out[i], out[j] = "", SARA_AM

    # 5) เ เ → แ
    for i, c in enumerate(out):
        if c == SARA_E:
            j = _next(out, i)
            if j < n and out[j] == SARA_E:
                out[i], out[j] = "แ", ""

    # 6) ำ ก่อนวรรณยุกต์ (ำ ้ → ้ ำ) — วรรณยุกต์เป็นของพยัญชนะก่อนหน้า
    for i, c in enumerate(out):
        if c == SARA_AM:
            j = _next(out, i)
            if j < n and out[j] in TONES:
                out[i], out[j] = out[j], SARA_AM

    # 7) เรียงเครื่องหมายบน/ล่างในแต่ละกลุ่ม + ลบตัวซ้ำ
    i = 0
    while i < n:
        if out[i] not in MARKS:
            i += 1
            continue
        idx = []
        j = i
        while j < n and (out[j] == "" or out[j] in MARKS):
            if out[j]:
                idx.append(j)
            j += 1
        marks = sorted((out[k] for k in idx), key=lambda m: _MARK_RANK[m])
        seen = set()
        for k, m in zip(idx, marks):
            out[k] = "" if m in seen else m
            seen.add(m)
        i = j
    return out


def _thai_before(out: list[str], i: int) -> bool:
    p = _prev(out, i)
    return p >= 0 and (is_thai_consonant(out[p]) or out[p] in MARKS)


def normalize(text: str, misencoded_am: bool = False) -> str:
    """จัดรูปข้อความทั้งก้อน (ไม่ต้องผูกกับตำแหน่งอักขระ)"""
    if not text or not has_thai(text):
        return text or ""
    chars = list(text)
    flags = [misencoded_am] * len(chars) if misencoded_am else None
    return "".join(normalize_chars(chars, flags))


# ---------------------------------------------------------------- ฟอนต์ที่ map สระอาเป็น ำ (ตัดสินด้วยพจนานุกรม)

MIN_AM_FOR_DETECTION = 3
MIN_COVERAGE_GAIN = 0.05


CUSTOM_WORDS_FILE = Path(__file__).resolve().parent.parent / "assets" / "thai_custom_words.txt"


@functools.lru_cache(maxsize=1)
def custom_words() -> frozenset:
    """คำเสริมจาก app/assets/thai_custom_words.txt (ตัวย่อหน่วยงาน คำทับศัพท์ ฯลฯ)"""
    try:
        lines = CUSTOM_WORDS_FILE.read_text("utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(w.strip() for w in lines if w.strip() and not w.lstrip().startswith("#"))


@functools.lru_cache(maxsize=1)
def _dictionary() -> frozenset:
    from pythainlp.corpus import thai_words

    return frozenset(thai_words()) | custom_words()


@functools.lru_cache(maxsize=1)
def _trie():
    from pythainlp.util import dict_trie

    return dict_trie(_dictionary())


_FALLBACK_TOKEN_RE = re.compile(r"\s+|\S+")


def tokenize(text: str, keep_whitespace: bool = True) -> list[str]:
    """ตัดคำ (newmm + พจนานุกรมมาตรฐาน + คำเสริม) — ไม่มี pythainlp ก็ยังตัดที่ช่องว่างได้"""
    if not text:
        return []
    try:
        from pythainlp import word_tokenize

        return word_tokenize(text, custom_dict=_trie(), engine="newmm", keep_whitespace=keep_whitespace)
    except ImportError:  # pragma: no cover
        tokens = _FALLBACK_TOKEN_RE.findall(text)
        return tokens if keep_whitespace else [t for t in tokens if not t.isspace()]


def unknown_words(text: str) -> list[str]:
    """คำไทยที่ไม่อยู่ในพจนานุกรม พร้อมคำข้างเคียง (newmm หั่นคำที่ไม่รู้จักเป็นชิ้น เช่น ทเวนตี้โฟร์ → ท|เวน|ตี้|โฟร์
    จึงคืน "ชิ้นที่ไม่รู้จัก + ชิ้นก่อน/หลัง" ให้คนดูแล้วเลือกคำไปเพิ่มใน thai_custom_words.txt)"""
    words = _dictionary()
    toks = tokenize(text)  # เก็บช่องว่างไว้เป็นตัวคั่น (ไม่รวมคำข้ามช่องว่าง)
    thai = [bool(t) and all("\u0E01" <= c <= "\u0E4E" for c in t) for t in toks]
    out = []
    for i, t in enumerate(toks):
        if not thai[i] or t in words or t in ("\u0E46", "\u0E2F"):
            continue
        lo = i - 1 if i and thai[i - 1] else i
        hi = i + 1 if i + 1 < len(toks) and thai[i + 1] else i
        out.append("".join(toks[lo:hi + 1]))
    return out


def with_break_opportunities(text: str) -> str:
    """แทรก zero-width space ระหว่างคำไทยที่ติดกัน — ให้โปรแกรมที่ตัดบรรทัดเฉพาะที่ช่องว่าง (fpdf2 multi_cell/
    table, Word) ขึ้นบรรทัดใหม่ตรงขอบคำ ไม่ใช่กลางคำ · ไม่แทรกระหว่างอังกฤษ/ตัวเลข หรือที่มีช่องว่างอยู่แล้ว"""
    if not text or not has_thai(text):
        return text or ""
    tokens = tokenize(text)
    out = []
    for i, tok in enumerate(tokens):
        if i and is_thai(tokens[i - 1][-1:]) and is_thai(tok[:1]) and tok[:1] not in MARKS | {"\u0E46", "\u0E2F"}:
            out.append("\u200b")
        out.append(tok)
    return "".join(out)


def dictionary_coverage(text: str) -> float:
    """สัดส่วนอักษรไทยที่อยู่ในคำที่มีในพจนานุกรม (คำยาว ≥2 ตัว) — ใช้วัด "อ่านออก" ของข้อความ"""
    thai = [c for c in text if is_thai(c)]
    if not thai:
        return 1.0
    words = _dictionary()
    good = sum(len(t) for t in tokenize(text, keep_whitespace=False) if len(t) > 1 and t in words)
    return min(1.0, good / len(thai))


def detect_misencoded_am_fonts(text_by_font: dict[str, str]) -> set[str]:
    """คืนชื่อฟอนต์ที่ดูเหมือน map สระอาเป็น ำ — แก้แล้วต้องอ่านออกดีขึ้นชัดเจน (≥5%) จึงนับ"""
    flagged = set()
    for font, text in text_by_font.items():
        if text.count(SARA_AM) < MIN_AM_FOR_DETECTION:
            continue
        before = dictionary_coverage(normalize(text))
        after = dictionary_coverage(normalize(text, misencoded_am=True))
        if after - before >= MIN_COVERAGE_GAIN:
            flagged.add(font)
    return flagged


# ---------------------------------------------------------------- ใช้กับผลลัพธ์ของ PyMuPDF


def _spans(page_dict: dict) -> Iterable[dict]:
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            yield from line.get("spans", [])


def _span_chars(span: dict) -> list[str]:
    if "chars" in span:  # rawdict
        return [ch.get("c", "") for ch in span["chars"]]
    return list(span.get("text", ""))


def _page_flags(page_dict: dict) -> set[str]:
    text_by_font: dict[str, list[str]] = {}
    for span in _spans(page_dict):
        chars = _span_chars(span)
        if SARA_AM in chars:
            text_by_font.setdefault(span.get("font", ""), []).append("".join(chars))
    return detect_misencoded_am_fonts({f: " ".join(t) for f, t in text_by_font.items()})


# ---------------------------------------------------------------- วงกลมสระอำที่วาดเป็นเส้น

# ตำแหน่งวงกลมนิคหิตเทียบกับจุดเริ่ม (origin) ของสระอา หน่วย = ขนาดฟอนต์ — วัดจาก glyph ำ ของ Sarabun,
# TH Sarabun New, Kanit: วงกลมอยู่ซ้ายของสระอา (x −0.24…0) และสูงกว่าเส้นฐาน 0.46–0.90 เท่าขนาดฟอนต์
_CIRCLE_X = (-0.32, 0.06)
_CIRCLE_Y = (0.35, 1.05)
_CIRCLE_SIZE = (0.07, 0.34)
_MAX_DRAWINGS = 20000


def _small_circles(page) -> list:
    """กรอบของรูปวาดขนาดเล็กเกือบจัตุรัสที่มีเส้นโค้ง (วงกลม/วงแหวน) ในหน้า"""
    try:
        drawings = page.get_drawings()
    except Exception:  # pragma: no cover — PDF เสียบางไฟล์
        return []
    if len(drawings) > _MAX_DRAWINGS:
        return []
    out = []
    for d in drawings:
        r = d.get("rect")
        if r is None or r.width <= 0 or r.height <= 0 or r.width > 40 or r.height > 40:
            continue
        if not 0.6 <= r.width / r.height <= 1.7:
            continue
        if not any(item[0] == "c" for item in d.get("items", [])):
            continue
        out.append(r)
    return out


def vector_am_flags(page, raw: dict) -> dict[tuple[int, int, int, int], bool]:
    """{(block, line, span, char): True} สำหรับสระอาที่มีวงกลมนิคหิตวาดเป็นเส้นอยู่เหนือ-ซ้าย (raw = rawdict)"""
    candidates = []
    for bi, block in enumerate(raw.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for li, line in enumerate(block.get("lines", [])):
            for si, span in enumerate(line.get("spans", [])):
                for ci, ch in enumerate(span.get("chars", [])):
                    if ch.get("c") == SARA_AA:
                        candidates.append(((bi, li, si, ci), ch, span.get("size", 0)))
    if not candidates:
        return {}
    circles = _small_circles(page)
    if not circles:
        return {}
    found = {}
    for key, ch, size in candidates:
        if size <= 0:
            continue
        ox, base = ch["origin"]
        for r in circles:
            cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            if not (_CIRCLE_SIZE[0] * size <= max(r.width, r.height) <= _CIRCLE_SIZE[1] * size):
                continue
            if not (ox + _CIRCLE_X[0] * size <= cx <= ox + _CIRCLE_X[1] * size):
                continue
            if not (base - _CIRCLE_Y[1] * size <= cy <= base - _CIRCLE_Y[0] * size):
                continue
            found[key] = True
            break
    return found


def _vector_flags_for(page, page_dict: dict) -> dict:
    """vector_am_flags สำหรับ dict หรือ rawdict (dict ไม่มีพิกัดรายตัว → อ่าน rawdict มาเทียบตามลำดับ)"""
    if page is None:
        return {}
    is_raw = any("chars" in s for s in _spans(page_dict))
    raw = page_dict if is_raw else page.get_text("rawdict")
    flags = vector_am_flags(page, raw)
    if is_raw or not flags:
        return flags
    # dict: ใช้ได้เฉพาะ span ที่จำนวนอักขระตรงกับ rawdict (โครงสร้างเดียวกันเมื่อ flags เดียวกัน)
    ok = {}
    rb = raw.get("blocks", [])
    for (bi, li, si, ci), v in flags.items():
        try:
            span = page_dict["blocks"][bi]["lines"][li]["spans"][si]
            rspan = rb[bi]["lines"][li]["spans"][si]
        except (IndexError, KeyError):
            continue
        if len(span.get("text", "")) == len(rspan.get("chars", [])):
            ok[(bi, li, si, ci)] = v
    return ok


def normalize_page_dict(page_dict: dict, page=None) -> dict:
    """แก้ข้อความใน page.get_text("dict"/"rawdict") ในที่ (ทีละบรรทัด ข้าม span ได้) แล้วคืน dict เดิม

    rawdict: ch["c"] ของตัวที่ถูกรวมจะเป็น "" (กรอบเดิมยังอยู่) · dict: span["text"] เป็นข้อความที่แก้แล้ว
    page: ส่งมาด้วยเพื่อตรวจวงกลมสระอำที่วาดเป็นเส้น (ไม่ส่ง = ข้ามขั้นนี้)
    """
    if not any(has_thai("".join(_span_chars(s))) for s in _spans(page_dict)):
        return page_dict
    flagged = _page_flags(page_dict)
    vector = _vector_flags_for(page, page_dict)
    for bi, block in enumerate(page_dict.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for li, line in enumerate(block.get("lines", [])):
            spans = line.get("spans", [])
            chars, flags, vflags = [], [], []
            for si, span in enumerate(spans):
                cs = _span_chars(span)
                chars.extend(cs)
                flags.extend([span.get("font", "") in flagged] * len(cs))
                vflags.extend(vector.get((bi, li, si, ci), False) for ci in range(len(cs)))
            if not has_thai("".join(chars)):
                continue
            fixed = normalize_chars(chars, flags if flagged else None, vflags if vector else None)
            pos = 0
            for si, span in enumerate(spans):
                if "chars" in span:
                    for ch in span["chars"]:
                        ch["c"] = fixed[pos]
                        pos += 1
                else:
                    k = len(span.get("text", ""))
                    span["text"] = "".join(fixed[pos:pos + k])
                    pos += k
            if any("chars" in sp for sp in spans):
                _widen_zero_width_spacing(spans)
    return page_dict


def _widen_zero_width_spacing(spans: list[dict]) -> None:
    """อักษรที่ควรมีความกว้าง (ำ า ะ พยัญชนะ) แต่ฟอนต์รายงานกว้าง 0 → ขยายกรอบถึงตัวถัดไป
    ฟอนต์บางตัว (เช่น Norasi จาก LibreOffice) ให้ ำ กว้าง 0 แต่ตัวถัดไปเริ่มห่างออกไปเท่าความกว้างจริงของ ำ —
    ระยะนั้นถูกตีความเป็นช่องว่างตอนคัดลอก/ค้นหา ("สำหรับ" → "สำ หรับ")"""
    chars = [ch for sp in spans for ch in sp.get("chars", []) if ch.get("c")]
    size = max((sp.get("size", 0) for sp in spans), default=0) or 10
    for i, ch in enumerate(chars[:-1]):
        c = ch["c"]
        if not is_thai(c) or c in MARKS or c in TONES or c in "\u0E4C\u0E4D\u0E47\u0E4E":
            continue
        x0, y0, x1, y1 = ch["bbox"]
        if x1 - x0 > 0.05 * size:
            continue
        nxt = next((n for n in chars[i + 1:] if n["c"] not in MARKS and n["c"] not in TONES), None)
        if nxt is None:
            continue
        gap = nxt["bbox"][0] - x0
        if 0 < gap <= 0.9 * size:
            ch["bbox"] = (x0, y0, nxt["bbox"][0], y1)


# ---------------------------------------------------------------- ค้นหา


_WS_RE = re.compile(r"\s+")


def normalize_for_search(text: str) -> str:
    """ข้อความสำหรับเทียบค้นหา: จัดรูปไทย + ยุบช่องว่าง"""
    return _WS_RE.sub(" ", normalize(text)).strip()
