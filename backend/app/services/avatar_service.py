"""รูปโปรไฟล์: อีโมจิที่วาดเองด้วย Pillow (ไม่ใช้ฟอนต์อีโมจิ — ไม่มีเรื่องสิทธิ์การใช้ และไม่ต้องออกอินเทอร์เน็ต)

render_emoji(face, face_color, bg_color, size) → PNG bytes · วาดที่ขนาด 4 เท่าแล้วย่อ (ขอบเรียบ)
สีของเส้น (ตา/ปาก) เลือกขาว/เข้มอัตโนมัติตามความสว่างของสีหน้า"""
from __future__ import annotations

import io
import math
import re

from PIL import Image, ImageDraw

FACES: dict[str, str] = {
    "smile": "ยิ้ม",
    "grin": "ยิ้มกว้าง",
    "laugh": "หัวเราะ",
    "wink": "ขยิบตา",
    "cool": "แว่นดำ",
    "nerd": "แว่นตา",
    "heart": "ตาหัวใจ",
    "star": "ตาดาว",
    "tongue": "แลบลิ้น",
    "blush": "เขิน",
    "kiss": "จุ๊บ",
    "calm": "สบายใจ",
    "surprised": "ตกใจ",
    "sleepy": "ง่วง",
    "neutral": "เฉยๆ",
    "smirk": "ยิ้มมุมปาก",
    "cat": "แมว",
    "robot": "หุ่นยนต์",
}

DEFAULT_FACE_COLOR = "#FFC83D"
DEFAULT_BG_COLOR = "#DBEAFE"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def valid_color(value: str) -> bool:
    return bool(value and _HEX.match(value))


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _ink(face_rgb) -> tuple[int, int, int]:
    r, g, b = face_rgb
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (55, 41, 30) if lum > 110 else (255, 255, 255)


def _star(d: ImageDraw.ImageDraw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=fill)


def _heart(d: ImageDraw.ImageDraw, cx, cy, r, fill):
    d.ellipse((cx - r, cy - r * 0.9, cx, cy + r * 0.1), fill=fill)
    d.ellipse((cx, cy - r * 0.9, cx + r, cy + r * 0.1), fill=fill)
    d.polygon([(cx - r * 0.97, cy - r * 0.25), (cx + r * 0.97, cy - r * 0.25), (cx, cy + r * 1.05)], fill=fill)


def render_emoji(face: str, face_color: str = DEFAULT_FACE_COLOR, bg_color: str = DEFAULT_BG_COLOR, size: int = 256) -> bytes:
    if face not in FACES:
        raise ValueError("ไม่รู้จักแบบอีโมจินี้")
    if not (valid_color(face_color) and valid_color(bg_color)):
        raise ValueError("สีต้องอยู่ในรูปแบบ #RRGGBB")
    size = max(32, min(int(size), 512))
    S = size * 4
    img = Image.new("RGB", (S, S), _rgb(bg_color))
    d = ImageDraw.Draw(img)
    fc = _rgb(face_color)
    ink = _ink(fc)
    w = S / 100  # หน่วย: 1 = 1% ของภาพ
    lw = int(3.2 * w)
    cx, cy = 50 * w, 52 * w

    def P(x, y):
        return (x * w, y * w)

    def box(x0, y0, x1, y1):
        return (x0 * w, y0 * w, x1 * w, y1 * w)

    # ---- หัว ----
    if face == "cat":
        d.polygon([P(22, 40), P(26, 12), P(44, 28)], fill=fc)
        d.polygon([P(78, 40), P(74, 12), P(56, 28)], fill=fc)
    if face == "robot":
        d.line([P(50, 20), P(50, 11)], fill=ink, width=lw)
        d.ellipse(box(46, 6, 54, 14), fill=(239, 68, 68))
        d.rounded_rectangle(box(18, 20, 82, 84), radius=12 * w, fill=fc)
    else:
        d.ellipse(box(16, 18, 84, 86), fill=fc)

    blush = tuple(min(255, int(c * 0.55 + 255 * 0.45)) for c in (244, 114, 182))
    if face in ("blush", "kiss", "laugh", "heart", "cat"):
        d.ellipse(box(22, 58, 33, 65), fill=blush)
        d.ellipse(box(67, 58, 78, 65), fill=blush)

    def dot_eyes(y=44, r=4.2):
        d.ellipse(box(36 - r, y - r * 1.25, 36 + r, y + r * 1.25), fill=ink)
        d.ellipse(box(64 - r, y - r * 1.25, 64 + r, y + r * 1.25), fill=ink)

    def arc_eyes(up=True, y=45):  # ^ ^ (up) หรือ ปิดตาโค้งลง
        for x in (36, 64):
            if up:
                d.arc(box(x - 7, y - 4, x + 7, y + 8), 200, 340, fill=ink, width=lw)
            else:
                d.arc(box(x - 7, y - 8, x + 7, y + 4), 20, 160, fill=ink, width=lw)

    def smile(y0=54, y1=74, x0=33, x1=67, a0=20, a1=160):
        d.arc(box(x0, y0, x1, y1), a0, a1, fill=ink, width=lw)

    def open_mouth(y0=58, y1=76, tongue=False):
        d.chord(box(32, y0 - 8, 68, y1), 0, 180, fill=ink)
        if tongue:
            d.ellipse(box(43, y1 - 9, 57, y1 + 1), fill=(239, 98, 98))

    if face == "smile":
        dot_eyes(); smile()
    elif face == "grin":
        dot_eyes(); open_mouth()
    elif face == "laugh":
        arc_eyes(True); open_mouth(tongue=True)
    elif face == "wink":
        d.ellipse(box(31.8, 38.8, 40.2, 49.2), fill=ink)
        d.arc(box(57, 41, 71, 53), 200, 340, fill=ink, width=lw)
        smile()
    elif face == "cool":
        d.rounded_rectangle(box(24, 36, 47, 50), radius=5 * w, fill=(30, 30, 35))
        d.rounded_rectangle(box(53, 36, 76, 50), radius=5 * w, fill=(30, 30, 35))
        d.line([P(46, 40), P(54, 40)], fill=(30, 30, 35), width=lw)
        d.line([P(17, 39), P(24, 40)], fill=(30, 30, 35), width=lw)
        d.line([P(76, 40), P(83, 39)], fill=(30, 30, 35), width=lw)
        d.arc(box(38, 56, 66, 72), 20, 140, fill=ink, width=lw)
    elif face == "nerd":
        for x in (36, 64):
            d.ellipse(box(x - 10, 34, x + 10, 54), outline=ink, width=lw)
            d.ellipse(box(x - 3.5, 40, x + 3.5, 48), fill=ink)
        d.line([P(46, 43), P(54, 43)], fill=ink, width=lw)
        smile(58, 72, 38, 62)
        d.rectangle(box(45, 63, 50, 69), fill=(255, 255, 255))
        d.rectangle(box(50, 63, 55, 69), fill=(255, 255, 255))
    elif face == "heart":
        _heart(d, 36 * w, 44 * w, 9 * w, (239, 68, 68))
        _heart(d, 64 * w, 44 * w, 9 * w, (239, 68, 68))
        open_mouth(60, 74)
    elif face == "star":
        _star(d, 36 * w, 44 * w, 10 * w, (250, 204, 21) if fc != (250, 204, 21) else (234, 88, 12))
        _star(d, 64 * w, 44 * w, 10 * w, (250, 204, 21) if fc != (250, 204, 21) else (234, 88, 12))
        open_mouth()
    elif face == "tongue":
        dot_eyes()
        smile(52, 70)
        d.rounded_rectangle(box(44, 62, 58, 78), radius=6 * w, fill=(239, 98, 98))
        d.line([P(51, 64), P(51, 72)], fill=(200, 60, 70), width=int(1.5 * w))
    elif face == "blush":
        arc_eyes(True, 46); smile(56, 70, 40, 60)
    elif face == "kiss":
        arc_eyes(False, 44)
        d.arc(box(46, 58, 56, 66), 270, 90, fill=ink, width=lw)
        d.arc(box(46, 64, 56, 72), 270, 90, fill=ink, width=lw)
        _heart(d, 72 * w, 70 * w, 4.5 * w, (239, 68, 68))
    elif face == "calm":
        arc_eyes(False, 44); smile(54, 70, 38, 62)
    elif face == "surprised":
        for x in (36, 64):
            d.ellipse(box(x - 6, 36, x + 6, 50), fill=(255, 255, 255))
            d.ellipse(box(x - 3, 40, x + 3, 48), fill=ink)
        d.ellipse(box(43, 60, 57, 76), fill=ink)
    elif face == "sleepy":
        arc_eyes(False, 46)
        d.ellipse(box(46, 64, 54, 70), outline=ink, width=lw)
        for i, (x, y, s) in enumerate(((70, 26, 7), (79, 17, 5))):
            pts = [P(x, y), P(x + s, y), P(x, y + s), P(x + s, y + s)]
            d.line(pts, fill=ink, width=int(2.2 * w))
    elif face == "neutral":
        dot_eyes(); d.line([P(38, 66), P(62, 66)], fill=ink, width=lw)
    elif face == "smirk":
        d.line([P(30, 44), P(42, 44)], fill=ink, width=lw)
        d.line([P(58, 44), P(70, 44)], fill=ink, width=lw)
        d.arc(box(44, 56, 68, 70), 10, 120, fill=ink, width=lw)
    elif face == "cat":
        dot_eyes(46, 3.8)
        d.polygon([P(47, 56), P(53, 56), P(50, 60)], fill=(239, 98, 128))
        d.arc(box(40, 56, 50, 66), 0, 150, fill=ink, width=lw)
        d.arc(box(50, 56, 60, 66), 30, 180, fill=ink, width=lw)
        for s in (-1, 1):
            for dy in (-3, 3):
                d.line([P(50 + s * 14, 60 + dy * 0.6), P(50 + s * 30, 58 + dy * 1.6)], fill=ink, width=int(1.6 * w))
    elif face == "robot":
        for x in (36, 64):
            d.rounded_rectangle(box(x - 8, 37, x + 8, 51), radius=3 * w, fill=(255, 255, 255))
            d.ellipse(box(x - 3.5, 40.5, x + 3.5, 47.5), fill=(59, 130, 246))
        d.rounded_rectangle(box(34, 62, 66, 72), radius=3 * w, fill=(255, 255, 255))
        for x in (42, 50, 58):
            d.line([P(x, 62), P(x, 72)], fill=ink, width=int(1.6 * w))

    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


MAX_UPLOAD_BYTES = 8 * 1024 * 1024
AVATAR_SIZE = 256


def process_upload(data: bytes) -> bytes:
    """รูปที่ผู้ใช้อัปโหลด → PNG สี่เหลี่ยมจัตุรัส 256px (ครอปตรงกลาง) — เขียนไฟล์ใหม่ทั้งหมด จึงไม่มีข้อมูลแฝง
    (EXIF/ตำแหน่ง GPS) ติดไปด้วย · หมุนตาม EXIF ก่อน (รูปจากมือถือไม่ตะแคง) · ไม่ใช่รูป/ใหญ่เกิน → ValueError"""
    from PIL import ImageOps, UnidentifiedImageError

    if not data:
        raise ValueError("ไม่พบไฟล์รูป")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("ไฟล์รูปใหญ่เกิน 8MB")
    try:
        probe = Image.open(io.BytesIO(data))
        if probe.width * probe.height > 40_000_000:
            raise ValueError("รูปมีความละเอียดสูงเกินไป")
        probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("ไฟล์นี้ไม่ใช่รูปภาพที่รองรับ (ใช้ JPG, PNG, WebP หรือ GIF)") from None
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGBA") if "A" in img.getbands() or img.mode == "P" else img.convert("RGB")
    side = min(img.width, img.height)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
