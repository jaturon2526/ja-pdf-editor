"""ocr_thai — อ่านข้อความไทยในภาพด้วย Tesseract ให้แม่นขึ้นโดยไม่ใช้ AI (เฟส 5b)

ใช้ทั้งปุ่มคัดลอก/OCR และชั้นข้อความ OCR (pdf_service/ocr.py) — วัดผลด้วย scripts/ocr_eval.py

ปัญหาของการส่งทั้งภาพให้ Tesseract (--psm 6) ตรง ๆ กับภาษาไทย และสิ่งที่ทำแทน:
1. ตัวแบ่งบรรทัดของ Tesseract แยก "แถววรรณยุกต์/สระบน" (่ ้ ิ ี ั ที่ซ้อนกันสูง) ออกไปเป็นบรรทัดของมันเอง →
   วรรณยุกต์หาย ("ที่" → "ที") และได้บรรทัดขยะ ("๑ / ส 0 ๐ ๕") → ตัดบรรทัดเองด้วย horizontal projection
   แล้วรวมแถบบาง (สระบน/ล่าง วรรณยุกต์) เข้ากับบรรทัดหลักที่ใกล้ที่สุด จากนั้นอ่านทีละบรรทัด (--psm 7)
   โดยส่งทุกบรรทัดใน tesseract ครั้งเดียว (ไฟล์รายการภาพ — โหลดโมเดลครั้งเดียว)
2. ภาพเอียงเล็กน้อย (สแกน/ถ่ายรูป) ทำให้ตัดบรรทัดไม่ได้ → หามุมเอียงก่อน (deskew ±3°)
3. เส้นตาราง/กรอบ/เส้นใต้ ปนกับตัวอักษร → ลบเส้นยาวแนวนอน/แนวตั้งก่อนอ่าน
4. ภาพพื้นเทา/มี noise → บรรทัดที่ความมั่นใจต่ำ อ่านซ้ำจากภาพขาวดำ (Otsu) แล้วเลือกผลที่มั่นใจกว่า
5. บรรทัดที่สูงผิดปกติ (สองบรรทัดติดกันเพราะหางตัวอักษรแตะกัน) → ให้ Tesseract แบ่งเอง (--psm 6)
   แล้วตัดบรรทัดขยะแบบข้อ 1 ทิ้ง (เตี้ยกว่าบรรทัดอื่นมาก + มั่นใจต่ำหรือเว้นวรรคเยอะ)
6. คำสั้นในบรรทัดภาษาไทยที่โมเดล tha+eng อ่านเป็นอังกฤษ ("โทร" → "Ins", "ณ วันที่" → "cu JUN")
   → อ่านเฉพาะคำนั้นซ้ำด้วยโมเดลไทยอย่างเดียว
7. หลังอ่าน: thai_text.normalize (ลำดับสระ/วรรณยุกต์ ํา → ำ) · รวมช่องว่างที่ Tesseract แทรกกลางคำ
   (ถ้ารวมแล้วเป็นคำในพจนานุกรม) · แก้ตัวอักษรที่ OCR สับสนบ่อยด้วยพจนานุกรม (correct_word)

ผลวัด (scripts/ocr_eval.py 180 ภาพ 5 ฟอนต์ × 150/200/300 dpi × 6 แบบความเสื่อม) อยู่ใน docstring ของสคริปต์นั้น
"""
from __future__ import annotations

import csv
import logging
import os
import re
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

from app.core.heavy import heavy_slot
from app.services import thai_text

logger = logging.getLogger("pdf_service")

LANG = "tha+eng"
LANG_THAI = "tha"
TIMEOUT = 180                 # วินาทีต่อการเรียก tesseract หนึ่งครั้ง (ทั้งชุดบรรทัด)
RETRY_BINARY_BELOW = 90       # บรรทัดที่ความมั่นใจเฉลี่ยต่ำกว่านี้ อ่านซ้ำจากภาพขาวดำ
THIN_BAND = 0.45              # แถบที่เตี้ยกว่า 45% ของความสูงบรรทัดอ้างอิง = แถวสระบน/ล่าง/วรรณยุกต์ → รวมเข้าบรรทัดหลัก
TALL_BAND = 1.8               # แถบที่สูงกว่า 1.8 เท่าของค่ามัธยฐาน = หลายบรรทัดติดกัน
DESKEW_RANGE = 3.0
DESKEW_STEP = 0.25            # ความละเอียดของมุมในรอบละเอียด
DESKEW_MIN = 0.2


@dataclass
class OcrWord:
    text: str
    box: tuple[float, float, float, float]   # x0, y0, x1, y1 ในพิกัดพิกเซลของภาพต้นฉบับ
    conf: float


@dataclass
class OcrLine:
    words: list[OcrWord] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


# ---------------------------------------------------------------- ภาพ

def otsu_threshold(a: np.ndarray) -> int:
    hist = np.bincount(a.ravel(), minlength=256).astype(np.float64)
    total = a.size
    levels = np.arange(256)
    w_b = np.cumsum(hist)
    w_f = total - w_b
    sum_b = np.cumsum(hist * levels)
    m_b = np.divide(sum_b, w_b, out=np.zeros(256), where=w_b > 0)
    m_f = np.divide(sum_b[-1] - sum_b, w_f, out=np.zeros(256), where=w_f > 0)
    between = w_b * w_f * (m_b - m_f) ** 2
    return int(np.argmax(between))


def binarize(img: Image.Image) -> Image.Image:
    a = np.asarray(img)
    return Image.fromarray(np.where(a > otsu_threshold(a), 255, 0).astype(np.uint8))


def _ink(img: Image.Image) -> np.ndarray:
    a = np.asarray(img)
    return a <= otsu_threshold(a)


def _long_runs(mask: np.ndarray, min_len: int) -> np.ndarray:
    """ตำแหน่งพิกเซลที่อยู่ในแนวหมึกต่อเนื่องตามแถว (axis=1) ยาวอย่างน้อย min_len"""
    out = np.zeros_like(mask)
    padded = np.zeros((mask.shape[0], mask.shape[1] + 2), dtype=np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    rows_s, cols_s = np.nonzero(d == 1)
    _rows_e, cols_e = np.nonzero(d == -1)   # เรียงตามแถวแล้วคอลัมน์ทั้งคู่ → จับคู่กันตามลำดับได้
    long = np.nonzero(cols_e - cols_s >= min_len)[0]
    for k in long:
        out[rows_s[k], cols_s[k]:cols_e[k]] = True
    return out


def remove_rules(img: Image.Image, mask: np.ndarray, line_height: float | None = None) -> tuple[Image.Image, np.ndarray]:
    """ลบเส้นตาราง/กรอบ/เส้นใต้ ออกจากภาพและ mask
    - ยังไม่รู้ความสูงบรรทัด (กรอบล้อมทั้งบล็อกทำให้ตัดบรรทัดไม่ได้): เฉพาะเส้นแนวนอนยาว ≥ 50% ความกว้าง และ
      แนวตั้งยาว ≥ 75% ความสูงภาพ (ตัวอักษรไม่มีทางยาวขนาดนั้น)
    - รู้ความสูงบรรทัดแล้ว: แนวนอน ≥ 6 เท่าความสูงบรรทัด (และ ≥ 15% ความกว้าง) · แนวตั้ง ≥ 1.6 เท่า"""
    h, w = mask.shape
    if line_height is None:
        horiz = _long_runs(mask, int(max(0.5 * w, 40)))
        vert = _long_runs(mask.T, int(max(0.75 * h, 40))).T
    else:
        lh = max(8.0, line_height)
        horiz = _long_runs(mask, int(max(6 * lh, 0.15 * w)))
        vert = _long_runs(mask.T, int(max(1.6 * lh, 20))).T
    rules = horiz | vert
    if not rules.any():
        return img, mask
    # ขยายขอบเส้น 1 px กันขอบจาง ๆ ที่ anti-alias เหลือเป็นจุด
    grown = rules.copy()
    grown[1:, :] |= rules[:-1, :]
    grown[:-1, :] |= rules[1:, :]
    grown[:, 1:] |= rules[:, :-1]
    grown[:, :-1] |= rules[:, 1:]
    a = np.asarray(img).copy()
    a[grown] = 255
    return Image.fromarray(a), mask & ~grown


def remove_dot_leaders(img: Image.Image, mask: np.ndarray) -> tuple[Image.Image, np.ndarray]:
    """ลบเส้นจุดไข่ปลา ("ลงชื่อ ............") — Tesseract อ่านเป็นตัวเลขขยะ ("2222๑๑๓๓")
    จุด = ก้อนหมึกเล็ก (ไม่เกิน 30% ของความสูงตัวอักษร) เกือบจัตุรัส เรียงแนวนอนระดับเดียวกันห่างเท่า ๆ กันอย่างน้อย 6 จุด
    ความสูงตัวอักษร = เปอร์เซ็นไทล์ที่ 75 ของความสูงก้อนหมึกทั้งหมด (ไม่พึ่งการตัดบรรทัดที่อาจผิดเมื่อภาพเอียง)
    ต้องมี OpenCV (ติดมากับ pdf2docx) — ไม่มีก็ข้ามขั้นนี้"""
    try:
        import cv2
    except ImportError:  # pragma: no cover
        return img, mask
    n, _labels, stats, cent = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n < 8:
        return img, mask
    char_h = float(np.percentile(stats[1:, cv2.CC_STAT_HEIGHT], 75))
    lim = max(3.0, 0.3 * char_h)
    dots = [i for i in range(1, n)
            if stats[i, cv2.CC_STAT_WIDTH] <= lim and stats[i, cv2.CC_STAT_HEIGHT] <= lim
            and 0.4 <= stats[i, cv2.CC_STAT_WIDTH] / max(1, stats[i, cv2.CC_STAT_HEIGHT]) <= 2.5]
    if len(dots) < 6:
        return img, mask
    dots.sort(key=lambda i: (round(cent[i][1] / max(2.0, lim)), cent[i][0]))
    erase: list[int] = []
    run = [dots[0]]

    def flush(r):
        if len(r) >= 6:
            gaps = np.diff([cent[i][0] for i in r])
            if gaps.max() <= 3 * np.median(gaps):
                erase.extend(r)

    for i in dots[1:]:
        j = run[-1]
        if abs(cent[i][1] - cent[j][1]) <= lim * 0.6 and 0 < cent[i][0] - cent[j][0] <= 4 * lim:
            run.append(i)
        else:
            flush(run)
            run = [i]
    flush(run)
    if not erase:
        return img, mask
    a = np.asarray(img).copy()
    m = mask.copy()
    for i in erase:
        x, y, w, h = (int(v) for v in stats[i, :4])
        a[max(0, y - 1):y + h + 1, max(0, x - 1):x + w + 1] = 255
        m[max(0, y - 1):y + h + 1, max(0, x - 1):x + w + 1] = False
    return Image.fromarray(a), m


def deskew_angle(mask: np.ndarray) -> float:
    """มุม (องศา) ที่หมุนแล้วบรรทัดตรงที่สุด — วัดความคมของ horizontal projection; ไม่ชัดเจน → 0"""
    m = Image.fromarray((mask * 255).astype(np.uint8))
    scale = min(1.0, 1600 / max(m.size))
    if scale < 1:
        m = m.resize((max(1, int(m.width * scale)), max(1, int(m.height * scale))), Image.BOX)

    def sharpness(angle: float) -> float:
        r = np.asarray(m.rotate(angle, resample=Image.BILINEAR, fillcolor=0), dtype=np.float64) / 255
        return float((np.diff(r.sum(axis=1)) ** 2).sum())

    # หยาบ (ทีละ 1°) แล้วละเอียด (ทีละ DESKEW_STEP รอบมุมที่ดีที่สุด) — 13 ครั้งแทน 25
    base = sharpness(0.0)
    scores = {0.0: base}
    for angle in np.arange(-DESKEW_RANGE, DESKEW_RANGE + 1e-9, 1.0):
        scores.setdefault(round(float(angle), 2), sharpness(float(angle)))
    center = max(scores, key=scores.get)
    for k in (-3, -2, -1, 1, 2, 3):
        angle = round(center + k * DESKEW_STEP, 2)
        if abs(angle) <= DESKEW_RANGE and angle not in scores:
            scores[angle] = sharpness(angle)
    best_angle = max(scores, key=scores.get)
    return best_angle if scores[best_angle] > base * 1.03 and abs(best_angle) >= DESKEW_MIN else 0.0


def segment_lines(mask: np.ndarray) -> list[tuple[int, int]]:
    """แถบบรรทัด (y0, y1) จาก horizontal projection — แถบบาง (สระบน/ล่าง วรรณยุกต์) รวมเข้าแถบหลักที่ใกล้สุด"""
    prof = mask.sum(axis=1)
    rows = prof > max(1, mask.shape[1] * 0.002)
    bands, y, n = [], 0, len(rows)
    while y < n:
        if rows[y]:
            y0 = y
            while y < n and rows[y]:
                y += 1
            bands.append([y0, y])
        else:
            y += 1
    if not bands:
        return []
    # ความสูงบรรทัดอ้างอิง: เปอร์เซ็นไทล์ที่ 80 ไม่ใช่ค่าสูงสุด — โลโก้/รูปใหญ่แถบเดียวจะทำให้ทุกบรรทัดดูเป็น "แถบบาง"
    # แล้วถูกรวมเป็นแถบเดียวทั้งหน้า
    big = float(np.percentile([b[1] - b[0] for b in bands], 80))

    def is_thin(i: int) -> bool:
        h = bands[i][1] - bands[i][0]
        if h < THIN_BAND * big:
            return True
        # แถวสระ/วรรณยุกต์ที่สูงเกือบครึ่งบรรทัด (ตัวเล็ก/ความละเอียดต่ำ) แต่ห่างจากบรรทัดหลักแค่ 1–2 px
        if h < 0.7 * big:
            for j in (i - 1, i + 1):
                if 0 <= j < len(bands) and bands[j][1] - bands[j][0] > h:
                    gap = bands[i][0] - bands[j][1] if j < i else bands[j][0] - bands[i][1]
                    if gap <= 0.15 * big:
                        return True
        return False

    thin = [is_thin(i) for i in range(len(bands))]
    main = [b for b, t in zip(bands, thin) if not t]
    if not main:
        return [(bands[0][0], bands[-1][1])]
    for t in (b for b, is_t in zip(bands, thin) if is_t):
        def dist(m):
            return t[0] - m[1] if t[0] >= m[1] else m[0] - t[1]
        # ระยะเท่ากัน → รวมกับบรรทัดด้านล่าง (สระบน/วรรณยุกต์พบบ่อยกว่าสระล่าง)
        d, _, i = min((dist(m), 0 if m[0] >= t[1] else 1, i) for i, m in enumerate(main))
        if d <= 0.8 * big:
            main[i] = [min(main[i][0], t[0]), max(main[i][1], t[1])]
        else:
            main.append(t)
    main.sort()
    return [(a, b) for a, b in main]


# ---------------------------------------------------------------- tesseract แบบส่งหลายภาพครั้งเดียว

@dataclass
class _Page:
    text: str                         # ข้อความทั้งหน้า (หลายบรรทัดได้ ถ้า psm 6)
    tokens: list[dict]                # แถว tsv ระดับคำที่มีข้อความ (left/top/width/height/conf/line key)

    @property
    def conf(self) -> float:
        return statistics.mean(float(t["conf"]) for t in self.tokens) if self.tokens else -1.0


def _tesseract_batch(images: list[Image.Image], psm: int, lang: str = LANG, whitelist: str = "") -> list[_Page]:
    """อ่านหลายภาพใน tesseract ครั้งเดียว (ไฟล์รายการภาพ) — คืนผลตามลำดับภาพ"""
    if not images:
        return []
    import pytesseract

    cmd = pytesseract.pytesseract.tesseract_cmd
    with tempfile.TemporaryDirectory(prefix="ocr_") as d:
        paths = []
        for i, im in enumerate(images):
            p = os.path.join(d, f"{i:04d}.png")
            im.save(p)
            paths.append(p)
        listfile = os.path.join(d, "list.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            f.write("\n".join(paths) + "\n")
        out = os.path.join(d, "out")
        # OMP_THREAD_LIMIT=1: OpenMP ของ tesseract แย่งกันเองบนเครื่องไม่กี่คอร์ — วัดแล้วช้ากว่าเธรดเดียว 3–4 เท่า
        extra = ["-c", f"tessedit_char_whitelist={whitelist}"] if whitelist else []
        with heavy_slot("tesseract"):
            subprocess.run([cmd, listfile, out, "-l", lang, "--psm", str(psm),
                            "-c", "preserve_interword_spaces=1", *extra, "txt", "tsv"],
                           capture_output=True, check=True, timeout=TIMEOUT,
                           env={**os.environ, "OMP_THREAD_LIMIT": "1"})
        with open(out + ".txt", encoding="utf-8") as f:
            texts = f.read().split("\f")
        with open(out + ".tsv", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    tokens: dict[int, list[dict]] = {}
    for r in rows:
        if r.get("level") == "5" and (r.get("text") or "").strip():
            tokens.setdefault(int(r["page_num"]), []).append(r)
    return [_Page(texts[i].strip("\n") if i < len(texts) else "", tokens.get(i + 1, [])) for i in range(len(images))]


# ---------------------------------------------------------------- จับคู่ข้อความกับกรอบของ token

def _words_from_line(text: str, tokens: list[dict], dx: float, dy: float) -> list[OcrWord]:
    """แยกบรรทัดเป็นคำตามช่องว่างในผล txt ของ tesseract แล้วหากรอบคำจาก token ใน tsv
    (ภาษาไทย tsv แบ่ง token เป็นกลุ่มอักษรเล็ก ๆ และไม่บอกว่าตรงไหนมีช่องว่าง — txt บอก)"""
    words_txt = [w for w in text.split(" ") if w]
    if not words_txt or not tokens:
        return []
    joined = "".join(t["text"].strip() for t in tokens)
    boxes = [(float(t["left"]) + dx, float(t["top"]) + dy,
              float(t["left"]) + float(t["width"]) + dx, float(t["top"]) + float(t["height"]) + dy) for t in tokens]
    confs = [float(t["conf"]) for t in tokens]
    if joined != "".join(words_txt):
        # จับคู่ไม่ได้ (เกิดน้อย) → ทั้งบรรทัดเป็นคำเดียวกรอบเดียว
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        return [OcrWord(" ".join(words_txt), box, statistics.mean(confs))]
    owner = []  # อักขระลำดับที่ i อยู่ใน token ไหน
    for k, t in enumerate(tokens):
        owner.extend([k] * len(t["text"].strip()))
    out, pos = [], 0
    for w in words_txt:
        ks = sorted(set(owner[pos:pos + len(w)]))
        pos += len(w)
        bs = [boxes[k] for k in ks]
        out.append(OcrWord(w, (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)),
                           statistics.mean(confs[k] for k in ks)))
    return out


def _psm6_lines(page: _Page, dx: float, dy: float) -> list[OcrLine]:
    """ผล --psm 6 → บรรทัด โดยตัดบรรทัดขยะ (แถววรรณยุกต์ที่ tesseract แยกเป็นบรรทัดเอง) ทิ้ง"""
    groups: dict[tuple, list[dict]] = {}
    for t in page.tokens:
        groups.setdefault((t["block_num"], t["par_num"], t["line_num"]), []).append(t)
    texts = [ln for ln in page.text.splitlines() if ln.strip()]
    toks = list(groups.values())
    if not toks:
        return []
    if len(texts) != len(toks):
        return [OcrLine([OcrWord(" ".join(texts), (dx, dy, dx, dy), page.conf)])] if texts else []
    heights = [max(int(t["top"]) + int(t["height"]) for t in g) - min(int(t["top"]) for t in g) for g in toks]
    med = statistics.median(heights)
    lines = []
    for text, g, h in zip(texts, toks, heights):
        conf = statistics.mean(float(t["conf"]) for t in g)
        if h < 0.7 * med and (conf < 85 or text.count(" ") / max(1, len(text)) > 0.4):
            continue
        lines.append(OcrLine(_words_from_line(text.strip(), g, dx, dy)))
    return lines


# ---------------------------------------------------------------- แก้คำหลังอ่าน

_THAI_LETTER = re.compile(r"[\u0E01-\u0E4E]")
_THAI_ONLY = re.compile(r"[\u0E01-\u0E4E]+")
_NUMLIKE = re.compile(r"[\u0E50-\u0E59\d.,/:()%\-]+")
_LATIN_SHORT = re.compile(r"[A-Za-z|!%.]{1,5}")
_THAI_RESULT = re.compile(r"[\u0E01-\u0E59.]+")
_STRAY = re.compile(r"[|_~¦]+")
_ASCII_RESULT = re.compile(r"[A-Za-z0-9\-/.:,()#&+%]+")
_ASCII_IN_THAI = re.compile(r"[A-Za-z|!]")

# ตัวอักษรที่ OCR สับสนบ่อย (หน้าตาคล้ายกัน) — ใช้แก้คำที่ไม่อยู่ในพจนานุกรม
CONFUSABLE_GROUPS = ("กคถ", "ชซข", "บปษ", "ญณ", "ดค", "ผฝ", "พฟ", "ถภ", "ุู", "่้", "ิีึื", "ฎฏ", "ใไ")
CONFUSABLE: dict[str, set[str]] = {}
for _grp in CONFUSABLE_GROUPS:
    for _c in _grp:
        CONFUSABLE.setdefault(_c, set()).update(x for x in _grp if x != _c)
CONFUSABLE.setdefault("า", set()).add("ำ")   # นิคหิตของ ำ หายเมื่อซ้อนกับวรรณยุกต์ ("น้ำ" → "น้า")
CONFUSABLE.setdefault("ำ", set()).add("า")


def _analyze(word: str) -> tuple[int, list[tuple[int, int]], int]:
    """(จำนวนอักษรไทยที่ไม่อยู่ในพจนานุกรม, ช่วงตำแหน่งของส่วนที่ไม่รู้จัก, จำนวนคำที่ตัดได้)"""
    toks = thai_text.tokenize(word, keep_whitespace=False)
    dictionary = thai_text._dictionary()
    unknown, spans, pos = 0, [], 0
    for t in toks:
        i = word.find(t, pos)
        pos = i + len(t)
        if _THAI_LETTER.search(t) and t not in dictionary and not _NUMLIKE.fullmatch(t):
            unknown += len(t)
            spans.append((i, i + len(t)))
    return unknown, spans, len(toks)


def correct_word(word: str) -> str:
    """แก้อักษรที่ OCR สับสนหนึ่งตัว เฉพาะเมื่อผลลัพธ์มีทางเดียวที่ทำให้ทั้งคำอยู่ในพจนานุกรม
    - คำที่มีส่วนไม่รู้จัก: ลองเปลี่ยนเฉพาะอักษรในส่วนที่ไม่รู้จัก ("ผู้รัปมอบ" → "ผู้รับมอบ", "ปากเคร็ด" → "ปากเกร็ด")
    - คำที่รู้จักครบแล้ว: แก้เฉพาะ า ที่ตามหลังวรรณยุกต์ → ำ เมื่อทำให้ตัดคำได้น้อยลง ("น้าหนัก" น้า|หนัก →
      "น้ำหนัก") — นิคหิตหายเฉพาะตอนซ้อนกับวรรณยุกต์ ที่อื่น OCR อ่าน ำ ได้ปกติ (กัน "คานาดา" → "คานาดำ")
    ไม่แตะชื่อเฉพาะที่ไม่มีทางแก้ทางเดียว ตัวเลข และภาษาอังกฤษ"""
    if not _THAI_LETTER.search(word) or len(word) > 40:
        return word
    u0, spans, n0 = _analyze(word)
    found: dict[str, int] = {}
    for i, c in enumerate(word):
        alts = CONFUSABLE.get(c)
        if not alts:
            continue
        inside = any(a <= i < b for a, b in spans)
        for alt in alts:
            if u0 > 0 and not inside:
                continue
            if u0 == 0 and not (c == "า" and alt == "ำ" and i > 0 and word[i - 1] in thai_text.TONES):
                continue
            cand = thai_text.normalize(word[:i] + alt + word[i + 1:])
            u, _, n = _analyze(cand)
            if u == 0 and (u0 > 0 or n < n0):
                found[cand] = n
    if not found:
        return word
    best = min(found.values())
    winners = [k for k, v in found.items() if v == best]
    return winners[0] if len(winners) == 1 else word


def _merge_split_words(words: list[OcrWord]) -> list[OcrWord]:
    """รวมคำไทยสองคำติดกันที่ tesseract แทรกช่องว่างกลางคำ ถ้าแยกแล้วไม่รู้จักแต่รวมแล้วอยู่ในพจนานุกรม
    ("สมคว รอนุญาต" → "สมควรอนุญาต")"""
    out: list[OcrWord] = []
    for w in words:
        if out and _THAI_ONLY.fullmatch(w.text) and _THAI_LETTER.match(out[-1].text[-1]):
            a = out[-1]
            if _analyze(a.text)[0] + _analyze(w.text)[0] > 0 and _analyze(a.text + w.text)[0] == 0:
                out[-1] = OcrWord(a.text + w.text, (min(a.box[0], w.box[0]), min(a.box[1], w.box[1]),
                                                    max(a.box[2], w.box[2]), max(a.box[3], w.box[3])),
                                  min(a.conf, w.conf))
                continue
        out.append(w)
    return out


def _postprocess(line: OcrLine) -> OcrLine:
    words = [OcrWord(thai_text.normalize(w.text), w.box, w.conf) for w in line.words]
    # ขีดเดี่ยว ๆ ที่เหลือจากขอบตาราง/เส้นที่ลบไม่หมด
    words = [w for w in words if w.text and not _STRAY.fullmatch(w.text)]
    words = _merge_split_words(words)
    return OcrLine([OcrWord(correct_word(w.text), w.box, w.conf) for w in words])


# ---------------------------------------------------------------- ขั้นตอนหลัก

@dataclass(eq=False)
class _Band:
    box: tuple[int, int, int, int]      # กรอบที่ตัดจากภาพที่หมุนแล้ว (x0, y0, x1, y1)
    height: int
    page: _Page | None = None
    image: Image.Image | None = None    # ภาพที่ให้ผล page (เทา หรือ ขาวดำ)
    lines: list[OcrLine] = field(default_factory=list)


_BORDER = 10


_LATIN_WORD = re.compile(r"[A-Za-z]{1,4}")


def reread_thai_lines(img: Image.Image, lines: list[OcrLine]) -> list[OcrLine]:
    """บรรทัด/คำไทยที่โมเดลไทย+อังกฤษอ่านเป็นอังกฤษ ("ที่ ธท 1017/2568" → "iis 6n 1017/2568", "เลขที่" → "Tawi")
    → อ่านซ้ำด้วยโมเดลไทยอย่างเดียว ใช้ผลใหม่เมื่อมั่นใจกว่าและเป็นคำที่มีในพจนานุกรม (≥ 60%)
    รอบ 1 ทั้งบรรทัดที่มีคำอังกฤษสั้นมั่นใจต่ำ · รอบ 2 ทีละคำ (คำไทยกลางบรรทัดที่มีรหัส/อังกฤษปน)
    กรอบคำอยู่ในพิกัดของ img"""
    jobs = []
    for i, ln in enumerate(lines):
        words = ln.words
        if not words or not any(_LATIN_WORD.fullmatch(w.text) and w.conf < 88 for w in words):
            continue
        x0, y0 = min(w.box[0] for w in words), min(w.box[1] for w in words)
        x1, y1 = max(w.box[2] for w in words), max(w.box[3] for w in words)
        m = 0.35 * (y1 - y0)
        box = (int(max(0, x0 - m)), int(max(0, y0 - m)), int(x1 + m), int(y1 + m))
        jobs.append((i, box, _crop(img, box)))
    for (i, box, _img), page in zip(jobs, _tesseract_batch([j[2] for j in jobs], 7, LANG_THAI)):
        text = " ".join(page.text.split()).strip()
        old_conf = statistics.mean(w.conf for w in lines[i].words)
        thai = [t for t in text.split() if _THAI_LETTER.search(t)]
        if not thai or page.conf <= old_conf or thai_text.dictionary_coverage("".join(thai)) < 0.6:
            continue
        words = _words_from_line(text, page.tokens, box[0] - _BORDER, box[1] - _BORDER)
        if words:
            lines[i] = OcrLine([OcrWord(thai_text.normalize(w.text), w.box, w.conf) for w in words])
    wjobs = []
    for i, ln in enumerate(lines):
        for k, w in enumerate(ln.words):
            if _LATIN_WORD.fullmatch(w.text) and w.conf < 88:
                x0, y0, x1, y1 = w.box
                m = 0.35 * (y1 - y0)
                wjobs.append((i, k, _crop(img, (int(max(0, x0 - m)), int(max(0, y0 - m)), int(x1 + m), int(y1 + m)))))
    for (i, k, _img), page in zip(wjobs, _tesseract_batch([j[2] for j in wjobs], 7, LANG_THAI)):
        alt = thai_text.normalize("".join(page.text.split()))
        w = lines[i].words[k]
        if alt and _THAI_LETTER.search(alt) and page.conf > w.conf and thai_text.dictionary_coverage(alt) >= 0.6:
            lines[i].words[k] = OcrWord(alt, w.box, page.conf)
    return lines


THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙"
# อักษรที่ Tesseract มักอ่านผิดแทนเลขไทย (๗→ข, ๙→«, ๖→ว/ง, ๘→ฆ ...)
_THAI_DIGIT_LOOKALIKE = set(THAI_DIGITS) | set("ขฃวงฆฒฐฯ«»๏๛ซรดคตณo0123456789")
_MONTHS = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
           "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
           "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
_NUMBER_BEFORE = ("พ.ศ.", "ที่", "มาตรา", "ข้อ", "หมู่", "ครั้งที่", "จำนวน", "ฉบับที่", "ชั้น", "ห้อง")


def _number_context(words: list[OcrWord], k: int) -> str:
    """ตำแหน่งที่ควรเป็นตัวเลข: "year" (หลัง พ.ศ.), "day" (ก่อนชื่อเดือน), "num" (หลังคำนำหน้าเลข) หรือ """""
    prev = words[k - 1].text if k > 0 else ""
    nxt = words[k + 1].text if k + 1 < len(words) else ""
    if prev.endswith("พ.ศ.") or prev.endswith("พ.ศ"):
        return "year"
    if any(nxt.startswith(m) for m in _MONTHS):
        return "day"
    if any(prev.endswith(t) for t in _NUMBER_BEFORE):
        return "num"
    return ""


def _plausible_number(value: int, ctx: str) -> bool:
    if ctx == "year":
        return 2400 <= value <= 2699
    if ctx == "day":
        return 1 <= value <= 31
    return True


def reread_thai_numbers(img: Image.Image, lines: list[OcrLine]) -> list[OcrLine]:
    """เลขไทย (๑๒๓) ที่ Tesseract อ่านพลาดบ่อยมาก (๖→๐, ๗→ข, ๙→«) — คำที่มีเลขไทย หรืออยู่ตำแหน่งที่ควรเป็นตัวเลข
    (หลัง "พ.ศ." ก่อนชื่อเดือน หลัง "มาตรา"/"ที่") → อ่านเลขใหม่ด้วยการเทียบรูปร่างทีละตัว (app/services/thai_digits.py)
    ใช้ผลใหม่เมื่อมั่นใจทุกตัว และสมเหตุสมผลตามตำแหน่ง (ปี พ.ศ. 2400–2699 · วันที่ 1–31)"""
    from app.services import thai_digits

    for ln in lines:
        for k, w in enumerate(ln.words):
            t = w.text.strip()
            if not t or len(t) > 12:
                continue
            first = next((j for j, c in enumerate(t) if c in THAI_DIGITS), None)
            ctx = _number_context(ln.words, k)
            if first is not None and any(t[:first].endswith(p) for p in ("พ.ศ.", "พ.ศ") + _NUMBER_BEFORE):
                prefix, body = t[:first], t[first:]           # คำนำหน้าติดกับตัวเลข ("พ.ศ.๒๕๖๙", "ที่๒")
            elif (first is not None or ctx) and len(t) <= 6 and all(c in _THAI_DIGIT_LOOKALIKE for c in t) \
                    and not t.isascii():
                prefix, body = "", t
            else:
                continue
            if not all(c in _THAI_DIGIT_LOOKALIKE or c in ",." for c in body):
                continue          # เลขไทยปนคำ ("๑ฉบับ") — ไม่แตะ
            if prefix.endswith("พ.ศ.") or prefix.endswith("พ.ศ"):
                ctx = "year"
            skip = sum(1 for c in prefix if "\u0e01" <= c <= "\u0e2e")      # พยัญชนะนำหน้า ("พ.ศ." = 2 ชิ้น)
            run = thai_digits.read_digits_at(img, w.box, skip)
            if not run:
                continue
            # ค่าที่ Tesseract อ่านได้ผิดรูปแบบชัดเจน (ปี ๒๕๐๒๐, วันที่ «) → ยอมรับผลเทียบรูปร่างที่สมเหตุสมผลแม้ไม่มั่นใจทุกตัว
            old_bad = bool(ctx) and not (all(c in THAI_DIGITS for c in body)
                                         and _plausible_number(int(body.translate(_TH2AR)), ctx))
            if not old_bad and not all(sure for _ch, sure, _b in run):
                continue
            digits = "".join(ch for ch, _s, _b in run)
            if not ctx and abs(len(digits) - len(body)) > 2:
                continue          # จำนวนตัวต่างจากที่ Tesseract เห็นมาก (และไม่มีตำแหน่งช่วยยืนยัน) — แยกตัวอักษรไม่สำเร็จ
            if ctx and not _plausible_number(int(digits.translate(_TH2AR)), ctx):
                continue
            if "," in body or "." in body:
                continue          # จำนวนเงินเลขไทยที่มีจุลภาค/จุด — ยังไม่แตะ (ตำแหน่งเครื่องหมายต้องคงไว้)
            ln.words[k] = OcrWord(prefix + digits, w.box, max(w.conf, 90.0))
    return lines


_TH2AR = str.maketrans(THAI_DIGITS, "0123456789")
_DIGIT_GROUP = re.compile(r"[0-9][0-9,.\-/]*")


def _fix_digit_lookalikes(line: OcrLine) -> OcrLine:
    """ตัวอักษรที่หน้าตาเหมือนเลขในกลุ่มตัวเลข: "O 2123 4567" → "0 2123 4567" (เบอร์โทร), "1O5" → "105"
    แก้เฉพาะ O/o/I/l ที่อยู่ติดหรือข้างคำที่เป็นตัวเลขล้วน"""
    words = list(line.words)
    for k, w in enumerate(words):
        t = w.text
        nxt = words[k + 1].text if k + 1 < len(words) else ""
        if t in ("O", "o") and _DIGIT_GROUP.fullmatch(nxt):
            words[k] = OcrWord("0", w.box, w.conf)
        elif len(t) >= 3 and any(c.isdigit() for c in t) and sum(c.isdigit() for c in t) >= len(t) - 1 \
                and re.fullmatch(r"[0-9OoIl]+", t):
            words[k] = OcrWord(t.translate(str.maketrans("OoIl", "0011")), w.box, w.conf)
    return OcrLine(words)


def _crop(img: Image.Image, box) -> Image.Image:
    return ImageOps.expand(img.crop(box), border=_BORDER, fill=255)


def recognize(img: Image.Image) -> list[OcrLine]:
    """อ่านข้อความในภาพ → บรรทัด/คำ พร้อมกรอบคำในพิกัดพิกเซลของภาพที่ส่งเข้ามา และความมั่นใจ (0–100)"""
    gray = img.convert("L")
    mask = _ink(gray)
    if not mask.any():
        return []
    gray, mask = remove_rules(gray, mask)
    gray, mask = remove_dot_leaders(gray, mask)

    angle = deskew_angle(mask)
    if angle:
        work = gray.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
        mask = _ink(work)
    else:
        work = gray
    segs = segment_lines(mask)
    if len(segs) > 1:
        # รู้ความสูงบรรทัดแล้ว (หลังหมุนภาพตรง) → ลบเส้นตาราง/เส้นใต้ที่สั้นกว่าครึ่งภาพได้ด้วย
        work, mask = remove_rules(work, mask, statistics.median(b - a for a, b in segs))
        segs = segment_lines(mask)
    binary = binarize(work)

    if not segs:
        return []
    med_h = statistics.median(b - a for a, b in segs)
    min_h = min(b - a for a, b in segs)
    bands = []
    for y0, y1 in segs:
        h = y1 - y0
        pad = max(4, int(h * 0.25))
        bands.append(_Band((0, max(0, y0 - pad), work.width, min(work.height, y1 + pad)), h))

    tall = [b for b in bands if b.height > TALL_BAND * med_h]
    single = [b for b in bands if b.height <= TALL_BAND * med_h]

    # 1) ทีละบรรทัด (psm 7) จากภาพเทา
    for b, page in zip(single, _tesseract_batch([_crop(work, b.box) for b in single], 7)):
        b.page, b.image = page, work
    # 2) บรรทัดที่อาจเป็นสองบรรทัดติดกันหรือมั่นใจต่ำมาก → ลอง psm 6 ด้วย
    maybe_multi = [b for b in single if b.height > 1.5 * min_h or b.page.conf < 70]
    multi_pages = _tesseract_batch([_crop(work, b.box) for b in tall + maybe_multi], 6)
    for b, page in zip(tall + maybe_multi, multi_pages):
        if b in tall or (page.conf > b.page.conf and len([t for t in page.text.splitlines() if t.strip()]) > 1):
            b.lines = _psm6_lines(page, b.box[0] - _BORDER, b.box[1] - _BORDER)
    # 3) บรรทัดที่มั่นใจไม่สูง → อ่านซ้ำจากภาพขาวดำ เลือกผลที่มั่นใจกว่า
    retry = [b for b in single if not b.lines and b.page.conf < RETRY_BINARY_BELOW]
    for b, page in zip(retry, _tesseract_batch([_crop(binary, b.box) for b in retry], 7)):
        if page.conf > b.page.conf:
            b.page, b.image = page, binary
    for b in single:
        if not b.lines:
            line = OcrLine(_words_from_line(" ".join(b.page.text.split("\n")).strip(), b.page.tokens,
                                            b.box[0] - _BORDER, b.box[1] - _BORDER))
            b.lines = [line] if line.words else []

    # 4) คำสั้นที่อ่านเป็นอังกฤษในบรรทัดภาษาไทย → อ่านซ้ำด้วยโมเดลไทยอย่างเดียว
    #    คำที่ปนอักษรไทยกับอังกฤษ ("|พง-2026" แทน "INV-2026") → อ่านซ้ำด้วยโมเดลอังกฤษ
    jobs, eng_jobs = [], []
    for b in bands:
        for line in b.lines:
            text = line.text
            thai = sum(1 for c in text if "\u0E01" <= c <= "\u0E4E")
            latin = sum(1 for c in text if c.isascii() and c.isalpha())
            src = b.image if b.image is not None else work
            for k, w in enumerate(line.words):
                m = max(6, (w.box[3] - w.box[1]) / 3)
                box = (int(max(0, w.box[0] - m)), b.box[1], int(min(src.width, w.box[2] + m)), b.box[3])
                if (thai >= 3 * max(1, latin) and _LATIN_SHORT.fullmatch(w.text)
                        and any(c.isalpha() for c in w.text) and w.conf < 90):
                    jobs.append((line, k, _crop(src, box)))
                elif _THAI_LETTER.search(w.text) and _ASCII_IN_THAI.search(w.text):
                    eng_jobs.append((line, k, _crop(src, box)))
    for (line, k, _), page in zip(jobs, _tesseract_batch([j[2] for j in jobs], 7, LANG_THAI)):
        alt = thai_text.normalize(" ".join(page.text.split()).strip())
        if alt and _THAI_RESULT.fullmatch(alt):
            w = line.words[k]
            line.words[k] = OcrWord(alt, w.box, page.conf)

    for (line, k, _), page in zip(eng_jobs, _tesseract_batch([j[2] for j in eng_jobs], 7, "eng")):
        alt = " ".join(page.text.split()).strip()
        if alt and _ASCII_RESULT.fullmatch(alt) and page.conf >= 60:
            w = line.words[k]
            line.words[k] = OcrWord(alt, w.box, page.conf)

    lines = [_postprocess(line) for b in bands for line in b.lines]
    lines = reread_thai_lines(work, [ln for ln in lines if ln.words])
    lines = reread_thai_numbers(work, lines)
    lines = [_fix_digit_lookalikes(ln) for ln in lines]

    if angle:
        # กรอบคำอยู่ในภาพที่หมุนแล้ว (expand) → หมุนจุดศูนย์กลางกลับเข้าพิกัดภาพเดิม คงขนาดกรอบ
        import math

        cx, cy = work.width / 2, work.height / 2
        ox, oy = gray.width / 2, gray.height / 2
        rad = math.radians(angle)
        cos, sin = math.cos(rad), math.sin(rad)
        for ln in lines:
            for i, w in enumerate(ln.words):
                mx, my = (w.box[0] + w.box[2]) / 2 - cx, (w.box[1] + w.box[3]) / 2 - cy
                # PIL rotate(angle) หมุนทวนเข็ม (แกน y ชี้ลง) → ย้อนกลับ
                x = mx * cos - my * sin + ox
                y = mx * sin + my * cos + oy
                hw, hh = (w.box[2] - w.box[0]) / 2, (w.box[3] - w.box[1]) / 2
                ln.words[i] = OcrWord(w.text, (x - hw, y - hh, x + hw, y + hh), w.conf)
    return lines


def recognize_text(img: Image.Image) -> str:
    return "\n".join(ln.text for ln in recognize(img))
