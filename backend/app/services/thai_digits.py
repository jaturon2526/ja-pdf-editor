"""อ่านเลขไทย (๐–๙) จากภาพด้วยการเทียบรูปร่าง — ใช้แทนผลของ Tesseract ซึ่งอ่านเลขไทยพลาดบ่อยมาก

วัดแล้ว (ภาพสังเคราะห์ เลขไทย 2–4 หลัก 5 ฟอนต์ × 3 ความละเอียด × เบลอ/noise/JPEG): Tesseract tha อ่านถูกทั้งชุด 16%
(๖→๐/๒, ๗→ข, ๙→« — จำกัดตัวอักษรให้เป็นเลขไทยก็ไม่ช่วย) ส่วนการเทียบรูปร่างตัวต่อตัว ~90%

วิธี: แยกตัวอักษรด้วย connected components → ปรับขนาดเป็นภาพจัตุรัสเล็ก → เทียบกับแม่แบบที่เรนเดอร์จากฟอนต์ไทยในระบบ
(หลายขนาด/ความหนา/ความเบลอ) แบบเพื่อนบ้านใกล้สุด — เลือกได้เฉพาะเลขไทย จึงใช้กับคำที่รู้แล้วว่าเป็นตัวเลข
(ส่วนหน้าที่เป็นตัวอักษร เช่น "พ.ศ." ที่ติดมากับปี ข้ามตามจำนวนตัวอักษรที่ Tesseract อ่านได้)
"""
from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙"
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_FILES = ("Sarabun-Regular.ttf", "Sarabun-Bold.ttf", "Sarabun-Italic.ttf",
               "Kanit-Regular.ttf", "Kanit-Bold.ttf",
               "google_cache/noto-sans-thai.ttf", "google_cache/prompt.ttf", "google_cache/mitr.ttf")
SIDE = 24
MIN_SIM = 0.80          # ความคล้ายต่ำกว่านี้ = ไม่แน่ใจ
MIN_MARGIN = 0.015      # ห่างจากตัวเลือกอันดับสอง (คนละตัว) อย่างน้อยเท่านี้

_lock = threading.Lock()
_model: tuple[np.ndarray, list[str]] | None = None


def _feature(mask: np.ndarray) -> np.ndarray:
    """ภาพขาวดำของตัวอักษร 1 ตัว (หมึก = 255) → เวกเตอร์รูปร่าง (ภาพจัตุรัสย่อ + สัดส่วนกว้าง/สูง)"""
    h, w = mask.shape
    s = max(w, h)
    pad = np.zeros((s, s), np.uint8)
    pad[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = mask
    f = cv2.resize(pad, (SIDE, SIDE), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    f /= np.linalg.norm(f) + 1e-6
    v = np.concatenate([f, [0.5 * min(w / h, 2.0)]]).astype(np.float32)
    return v / np.linalg.norm(v)


def _binarize(gray: np.ndarray) -> np.ndarray:
    _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return b


def _glyph_masks(ch: str, font: ImageFont.FreeTypeFont) -> list[np.ndarray]:
    img = Image.new("L", (font.size * 3, font.size * 3), 255)
    ImageDraw.Draw(img).text((font.size, font.size // 2), ch, font=font, fill=0)
    out = []
    for variant in (img, img.filter(ImageFilter.GaussianBlur(font.size / 40)),
                    img.filter(ImageFilter.MinFilter(3)), img.filter(ImageFilter.MaxFilter(3))):
        b = _binarize(np.asarray(variant))
        n, _lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
        if n < 2:
            continue
        i = 1 + int(np.argmax(st[1:, 4]))           # ชิ้นใหญ่สุด (เลขไทยเป็นชิ้นเดียว)
        x, y, w, h = st[i, :4]
        if w and h:
            out.append(b[y:y + h, x:x + w])
    return out


def _build() -> tuple[np.ndarray, list[str]]:
    feats, labels = [], []
    for name in _FONT_FILES:
        path = FONTS_DIR / name
        if not path.exists():
            continue
        for px in (22, 34, 50):
            font = ImageFont.truetype(str(path), px)
            for ch in THAI_DIGITS:
                for m in _glyph_masks(ch, font):
                    feats.append(_feature(m))
                    labels.append(ch)
    return np.stack(feats), labels


def _get_model() -> tuple[np.ndarray, list[str]]:
    global _model
    with _lock:
        if _model is None:
            _model = _build()
        return _model


def components(gray: Image.Image) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """ภาพเทาของคำ → (ภาพขาวดำ, กรอบตัวอักษรเรียงซ้ายไปขวา) — ตัดจุด/สระ/วรรณยุกต์ที่เตี้ยกว่าตัวหลัก
    และชิ้นที่ติดขอบซ้าย/ขวาของภาพ (เศษตัวอักษรของคำข้างเคียง) ทิ้ง"""
    b = _binarize(np.asarray(gray.convert("L")))
    n, _lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
    if n < 2:
        return b, []
    W = b.shape[1]
    keep = [i for i in range(1, n) if st[i, 4] >= 8 and st[i, 0] > 0 and st[i, 0] + st[i, 2] < W]
    if not keep:
        return b, []
    hmax = int(max(st[i, 3] for i in keep))
    boxes = [tuple(int(v) for v in st[i, :4]) for i in keep if st[i, 3] >= 0.4 * hmax]
    boxes.sort()
    return b, boxes


def classify(mask: np.ndarray) -> tuple[str, float, float]:
    """ตัวอักษร 1 ชิ้น → (เลขไทยที่ใกล้สุด, ความคล้าย, ระยะห่างจากเลขอันดับสองที่เป็นคนละตัว)"""
    X, labels = _get_model()
    sims = X @ _feature(mask)
    order = np.argsort(-sims)
    best = labels[int(order[0])]
    second = next((float(sims[j]) for j in order[1:] if labels[int(j)] != best), 0.0)
    return best, float(sims[int(order[0])]), float(sims[int(order[0])]) - second


def read_digits(gray: Image.Image, skip: int = 0) -> list[tuple[str, bool, tuple[int, int, int, int]]]:
    """ภาพเทาของคำที่เป็นตัวเลข → [(เลขไทย, มั่นใจ, กรอบ)] ทีละตัวจากซ้ายไปขวา (ข้าม skip ตัวแรก — ตัวอักษรนำหน้า)"""
    b, boxes = components(gray)
    boxes = _split_wide(b, boxes)
    out = []
    for x, y, w, h in boxes[skip:]:
        ch, sim, margin = classify(b[y:y + h, x:x + w])
        out.append((ch, sim >= MIN_SIM and margin >= MIN_MARGIN, (x, y, w, h)))
    return out


def _split_wide(b: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """เลขที่พิมพ์ชิดกันจนติดเป็นชิ้นเดียว ("๕๖") → แบ่งตามความกว้างปกติของเลขหนึ่งตัว ตรงคอลัมน์ที่หมึกน้อยสุด"""
    if not boxes:
        return boxes
    hmed = float(np.median([h for *_xy, _w, h in boxes]))
    out = []
    for x, y, w, h in boxes:
        k = int(round(w / (0.95 * hmed))) if w > 1.45 * hmed else 1
        if k < 2:
            out.append((x, y, w, h))
            continue
        cols = (b[y:y + h, x:x + w] > 0).sum(axis=0)
        cuts, step = [0], w / k
        for j in range(1, k):
            lo, hi = int(j * step - 0.25 * step), int(j * step + 0.25 * step)
            cuts.append(lo + int(np.argmin(cols[lo:hi + 1])))
        cuts.append(w)
        for a, c in zip(cuts, cuts[1:]):
            if c - a < 2:
                continue
            ys = np.where((b[y:y + h, x + a:x + c] > 0).any(axis=1))[0]
            if len(ys):
                out.append((x + a, y + int(ys[0]), c - a, int(ys[-1] - ys[0] + 1)))
    return out


def read_digits_at(img: Image.Image, box: tuple[int, int, int, int], skip: int = 0):
    """เลขไทยในกรอบคำบนภาพ — กรอบจาก Tesseract มักแคบกว่าตัวอักษรจริง (ตัดครึ่งตัวแรก/ตัวสุดท้าย) จึงตัดภาพกว้างกว่า
    แล้วเลือกเฉพาะตัวอักษรที่ทับกรอบเดิม (ชิ้นที่ทับเพียงเล็กน้อยก็นับ) — คืนแบบเดียวกับ read_digits"""
    x0, y0, x1, y1 = (int(v) for v in box)
    h = max(1, y1 - y0)
    ox, oy = max(0, x0 - h), max(0, y0 - int(0.3 * h))
    crop = img.crop((ox, oy, x1 + h, y1 + int(0.3 * h)))
    b = _binarize(np.asarray(crop.convert("L")))
    n, _lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
    picked = [i for i in range(1, n) if st[i, 4] >= 8
              and st[i, 0] + st[i, 2] > x0 - ox and st[i, 0] < x1 - ox]
    if not picked:
        return []
    hmax = int(max(st[i, 3] for i in picked))
    boxes = _split_wide(b, sorted(tuple(int(v) for v in st[i, :4]) for i in picked if st[i, 3] >= 0.4 * hmax))
    out = []
    for x, y, w, hh in boxes[skip:]:
        ch, sim, margin = classify(b[y:y + hh, x:x + w])
        out.append((ch, sim >= MIN_SIM and margin >= MIN_MARGIN, (x + ox, y + oy, w, hh)))
    return out
