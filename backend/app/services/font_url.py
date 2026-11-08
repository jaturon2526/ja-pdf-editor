"""ติดตั้งฟอนต์จากลิงก์ — เฉพาะแหล่งที่เชื่อถือได้ (ค่าเริ่มต้น Google Fonts) และ HTTPS เท่านั้น

ข้อตัดสินใจด้านความปลอดภัย (ผู้ใช้กำหนด 2026-10-25 — ดู Project doc claude/phase-font-from-url-plan.md):
- รับเฉพาะ https:// และโฮสต์ต้องอยู่ใน FONT_URL_ALLOWED_HOSTS แบบตรงตัว (ไม่ใช่ "ลงท้ายด้วย")
- ไฟล์ฟอนต์จริงดาวน์โหลดจาก fonts.gstatic.com เท่านั้น (ลิงก์อ่านจาก CSS ของ Google)
- redirect ที่ออกนอกโฮสต์ที่อนุญาต/ไม่ใช่ https = ปฏิเสธ · จำกัดขนาด เวลา และจำนวนครั้งต่อผู้ใช้
เซิร์ฟเวอร์จึงไม่เคยเรียกที่อยู่ที่ผู้ใช้กำหนดเองได้อิสระ (ไม่มีช่อง SSRF ไปเครื่องภายใน)

ลิงก์ที่รับ:
  https://fonts.google.com/specimen/Kanit[?...]
  https://fonts.googleapis.com/css2?family=Prompt:ital,wght@0,400;0,700&display=swap
  https://fonts.googleapis.com/css?family=Sarabun:400,700i
  Kanit                       (ชื่อฟอนต์เปล่าๆ)
"""
from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import fitz

from app.core.config import settings
from app.services import fonts

FONT_FILE_HOST = "fonts.gstatic.com"
CSS_HOST = "fonts.googleapis.com"
MAX_FONT_BYTES = 15 * 1024 * 1024
MAX_CSS_BYTES = 512 * 1024
TIMEOUT = 20.0
RATE_LIMIT = 20                 # ครั้ง / ผู้ใช้ / ชั่วโมง
RATE_WINDOW = 3600.0

STYLES = ("regular", "bold", "italic", "bold_italic")
_STYLE_AXES = {"regular": (0, 400), "bold": (0, 700), "italic": (1, 400), "bold_italic": (1, 700)}
_FAMILY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-]{0,79}$")


class FontUrlError(ValueError):
    """ข้อความภาษาไทยที่แสดงให้ผู้ใช้ได้ตรงๆ"""


@dataclass
class FontLink:
    family: str                                   # ชื่อ family ตามที่ Google Fonts ใช้ เช่น "Noto Sans Thai"
    styles: list[str] = field(default_factory=lambda: list(STYLES))  # สไตล์ที่ลิงก์ระบุ (ไม่ระบุ = ลองทั้ง 4)


@dataclass
class FetchedStyle:
    style: str
    data: bytes
    source_url: str
    has_thai: bool


def allowed_hosts() -> set[str]:
    raw = getattr(settings, "FONT_URL_ALLOWED_HOSTS", "") or "fonts.google.com,fonts.googleapis.com"
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


# ------------------------------------------------------------------ แยกลิงก์

def _clean_family(name: str) -> str:
    name = urllib.parse.unquote_plus(name).strip()
    if not _FAMILY_RE.fullmatch(name):
        raise FontUrlError("ชื่อฟอนต์ไม่ถูกต้อง — ใช้ได้เฉพาะตัวอักษรอังกฤษ ตัวเลข ช่องว่าง และขีด")
    return " ".join(name.split())


def _styles_from_css2_spec(spec: str) -> list[str]:
    """"ital,wght@0,400;1,700" / "wght@400;700" → ["regular", "bold_italic"] ..."""
    if "@" not in spec:
        return list(STYLES)
    axes, _, values = spec.partition("@")
    names = axes.split(",")
    found = []
    for tup in values.split(";"):
        parts = tup.split(",")
        if len(parts) != len(names):
            continue
        d = dict(zip(names, parts))
        try:
            ital = int(d.get("ital", "0"))
            weight = int(float(d.get("wght", "400").split("..")[0]))
        except ValueError:
            continue
        style = ("bold" if weight >= 600 else "regular") if not ital else ("bold_italic" if weight >= 600 else "italic")
        if style not in found:
            found.append(style)
    return found or list(STYLES)


def _styles_from_css1_spec(spec: str) -> list[str]:
    """"400,700i,italic,bold" → สไตล์"""
    found = []
    for v in spec.split(","):
        v = v.strip().lower()
        italic = v.endswith("i") or "italic" in v
        digits = re.sub(r"[^0-9]", "", v)
        weight = int(digits) if digits else (700 if "bold" in v else 400)
        style = ("bold_italic" if weight >= 600 else "italic") if italic else ("bold" if weight >= 600 else "regular")
        if style not in found:
            found.append(style)
    return found or list(STYLES)


def parse_font_link(text: str) -> FontLink:
    """ข้อความที่ผู้ใช้วาง → family + สไตล์ — ปฏิเสธทุกอย่างที่ไม่ใช่ https ของโฮสต์ที่อนุญาต"""
    text = (text or "").strip()
    if not text:
        raise FontUrlError("กรุณาใส่ลิงก์ Google Fonts หรือชื่อฟอนต์")
    if "://" not in text and "/" not in text and "." not in text:
        return FontLink(_clean_family(text))       # ชื่อฟอนต์เปล่าๆ

    url = urllib.parse.urlsplit(text if "://" in text else f"https://{text}")
    if url.scheme.lower() != "https":
        raise FontUrlError("รองรับเฉพาะลิงก์ https:// เท่านั้น")
    host = (url.hostname or "").lower()
    if host not in allowed_hosts() or url.port not in (None, 443) or url.username or url.password:
        raise FontUrlError("รองรับเฉพาะลิงก์จาก Google Fonts (fonts.google.com) — ฟอนต์จากแหล่งอื่นให้ดาวน์โหลด"
                           "ไฟล์ .ttf/.otf แล้วใช้แท็บ \"จากไฟล์\"")
    query = urllib.parse.parse_qs(url.query)

    if host == "fonts.google.com":
        # /specimen/Kanit และหน้าฟอนต์ตระกูล Noto: /noto/specimen/Noto+Sans+Thai
        m = re.match(r"^(?:/noto)?/specimen/([^/?#]+)", url.path)
        if not m:
            raise FontUrlError("ลิงก์นี้ไม่ใช่หน้าฟอนต์ — เปิดฟอนต์ที่ต้องการใน Google Fonts แล้วคัดลอกลิงก์จากแถบที่อยู่")
        return FontLink(_clean_family(m.group(1)))

    if host == CSS_HOST:
        families = query.get("family") or []
        if not families:
            raise FontUrlError("ลิงก์ CSS นี้ไม่มีชื่อฟอนต์ (family=...)")
        if len(families) > 1 or "|" in families[0]:
            raise FontUrlError("ลิงก์นี้มีหลายฟอนต์ — ติดตั้งได้ครั้งละ 1 ฟอนต์ ใช้ลิงก์ที่มีฟอนต์เดียว")
        name, _, spec = families[0].partition(":")
        if url.path.rstrip("/") == "/css2":
            return FontLink(_clean_family(name), _styles_from_css2_spec(spec))
        if url.path.rstrip("/") == "/css":
            return FontLink(_clean_family(name), _styles_from_css1_spec(spec) if spec else list(STYLES))
        raise FontUrlError("ลิงก์ fonts.googleapis.com ต้องเป็น /css2?family=... หรือ /css?family=...")

    # โฮสต์อื่นที่ผู้ดูแลระบบเพิ่มเองใน FONT_URL_ALLOWED_HOSTS — ต้องใช้รูปแบบ CSS เดียวกับ Google (css2/css)
    families = query.get("family") or []
    if not families:
        raise FontUrlError("ลิงก์นี้ไม่มีชื่อฟอนต์ (family=...)")
    name, _, spec = families[0].partition(":")
    return FontLink(_clean_family(name), _styles_from_css2_spec(spec))


# ------------------------------------------------------------------ ดาวน์โหลดอย่างปลอดภัย

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """ไม่ตาม redirect เอง — _get ตรวจปลายทางแล้วค่อยตามทีละขั้น"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _get(url: str, hosts: set[str], limit: int, user_agent: str, redirects: int = 3) -> bytes:
    """GET แบบปลอดภัย: https + โฮสต์ใน hosts เท่านั้น (ตรวจซ้ำทุก redirect) จำกัดขนาด/เวลา"""
    for _ in range(redirects + 1):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or (parts.hostname or "").lower() not in hosts or parts.port not in (None, 443):
            raise FontUrlError("ปลายทางของลิงก์ไม่ใช่แหล่งฟอนต์ที่อนุญาต")
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with _opener.open(req, timeout=TIMEOUT) as resp:
                length = resp.headers.get("Content-Length")
                if length and length.isdigit() and int(length) > limit:
                    raise FontUrlError("ไฟล์ฟอนต์ใหญ่เกินกำหนด (15 MB)")
                data = resp.read(limit + 1)
                if len(data) > limit:
                    raise FontUrlError("ไฟล์ฟอนต์ใหญ่เกินกำหนด (15 MB)")
                return data
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                continue
            raise
    raise FontUrlError("ลิงก์ redirect หลายต่อเกินไป")


def _css_url(family: str, style: str) -> str:
    """ลิงก์ CSS ของสไตล์เดียว — ตัวปกติไม่ใส่แกน (ฟอนต์ที่ไม่มีตัวเอียง/น้ำหนักเดียว ขอแบบมีแกนแล้ว Google ตอบ 400)"""
    fam = urllib.parse.quote_plus(family)
    ital, wght = _STYLE_AXES[style]
    spec = "" if style == "regular" else (f":wght@{wght}" if not ital else f":ital,wght@1,{wght}")
    return f"https://{CSS_HOST}/css2?family={fam}{spec}&display=swap"


def _has_thai(data: bytes) -> bool:
    try:
        font = fitz.Font(fontbuffer=data)
        return all(font.has_glyph(ord(c)) for c in "กขคาิ่")
    except Exception:
        return False


def fetch_google_font(link: FontLink) -> list[FetchedStyle]:
    """ดาวน์โหลดสไตล์ที่ลิงก์ระบุจาก Google Fonts (สไตล์ที่ฟอนต์ไม่มี เช่นตัวเอียง ข้ามไป)
    ใช้ User-Agent ที่ทำให้ Google ส่ง .ttf และเลือกไฟล์ชุดที่มีอักษรไทยก่อน (ดู fonts._extract_font_url)"""
    css_hosts = {CSS_HOST}
    out: list[FetchedStyle] = []
    not_found = 0
    for style in link.styles:
        css_text = None
        for ua in fonts._CANDIDATE_UAS:
            try:
                css = _get(_css_url(link.family, style), css_hosts, MAX_CSS_BYTES, ua).decode("utf-8", "ignore")
            except urllib.error.HTTPError as exc:
                if exc.code == 400:         # ฟอนต์ไม่มีสไตล์นี้ / ไม่มีฟอนต์ชื่อนี้
                    not_found += 1
                    break
                continue
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            if fonts._extract_font_url(css):
                css_text, css_ua = css, ua
                break
        if not css_text:
            continue
        font_url = fonts._extract_font_url(css_text)
        try:
            data = _get(font_url, {FONT_FILE_HOST}, MAX_FONT_BYTES, css_ua)
        except (urllib.error.URLError, TimeoutError, OSError):
            continue                            # ไฟล์สไตล์นี้โหลดไม่ได้ — ข้าม (FontUrlError ส่งต่อตามเดิม)
        try:
            fitz.Font(fontbuffer=data)
        except Exception:
            continue                            # ไม่ใช่ไฟล์ฟอนต์ที่ใช้ได้
        out.append(FetchedStyle(style, data, font_url, _has_thai(data)))
    if not out:
        if not_found == len(link.styles):
            raise FontUrlError(f"ไม่พบฟอนต์ \"{link.family}\" ใน Google Fonts — ตรวจตัวสะกด (เช่น Noto Sans Thai)")
        raise FontUrlError("ดาวน์โหลดฟอนต์จาก Google Fonts ไม่สำเร็จ — ลองใหม่อีกครั้ง")
    if not any(s.style == "regular" for s in out):
        raise FontUrlError("ฟอนต์นี้ไม่มีตัวปกติ (Regular) ที่ติดตั้งได้ — ใส่สไตล์ตัวปกติในลิงก์ด้วย หรือใช้ลิงก์หน้าฟอนต์")
    return out


# ------------------------------------------------------------------ จำกัดจำนวนครั้ง

_rate: dict[int, list[float]] = {}
_rate_lock = threading.Lock()


def check_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    with _rate_lock:
        hits = [t for t in _rate.get(user_id, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            raise FontUrlError("ติดตั้งฟอนต์จากลิงก์บ่อยเกินไป — ลองใหม่ในอีกสักครู่")
        hits.append(now)
        _rate[user_id] = hits


# ------------------------------------------------------------------ ตรวจ → ติดตั้ง (F2)
# ไฟล์ที่ดาวน์โหลดตอน "ตรวจลิงก์" เก็บชั่วคราวไว้ใน WORKING_DIR/font_url/<token>/ 30 นาที แล้วค่อยติดตั้งจริง
# เมื่อผู้ใช้กดยืนยัน (ไม่ต้องดาวน์โหลดซ้ำ) — token เป็นค่าสุ่ม 128 บิต ใช้ได้เฉพาะเจ้าของ (ตรวจ user_id ใน meta)

import json
import secrets
import shutil

PREVIEW_TTL = 30 * 60
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _preview_root():
    root = settings.WORKING_DIR / "font_url"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cleanup_expired() -> None:
    now = time.time()
    for d in _preview_root().iterdir():
        try:
            if now - d.stat().st_mtime > PREVIEW_TTL:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _existing_family(family: str, user_id: int) -> str | None:
    """"global" ถ้ามีฟอนต์ชื่อนี้มากับระบบ, "custom" ถ้าผู้ใช้เคยติดตั้งชื่อนี้แล้ว, None ถ้ายังไม่มี"""
    name = family.strip().lower()
    for f in fonts.list_font_families(user_id):
        if f["label"].strip().lower() == name:
            return "custom" if f["removable"] else "global"
    return None


def create_preview(text: str, user_id: int) -> dict:
    """ตรวจลิงก์ + ดาวน์โหลด แล้วเก็บชั่วคราว → ข้อมูลให้หน้าจอแสดงก่อนติดตั้ง"""
    link = parse_font_link(text)
    check_rate_limit(user_id)
    _cleanup_expired()
    fetched = fetch_google_font(link)
    token = secrets.token_hex(16)
    folder = _preview_root() / token
    folder.mkdir()
    for s in fetched:
        (folder / f"{s.style}.ttf").write_bytes(s.data)
    meta = {"user_id": user_id, "family": link.family, "created": time.time(),
            "styles": [{"style": s.style, "size": len(s.data), "has_thai": s.has_thai} for s in fetched]}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return {
        "token": token,
        "family": link.family,
        "styles": meta["styles"],
        "has_thai": all(s.has_thai for s in fetched),
        "exists": _existing_family(link.family, user_id),
        "missing_styles": [st for st in link.styles if st not in {s.style for s in fetched}],
    }


def _load_preview(token: str) -> tuple[dict, "Path"]:
    if not _TOKEN_RE.fullmatch(token or ""):
        raise FontUrlError("รายการตรวจลิงก์นี้หมดอายุแล้ว — กดตรวจลิงก์ใหม่อีกครั้ง")
    folder = _preview_root() / token
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise FontUrlError("รายการตรวจลิงก์นี้หมดอายุแล้ว — กดตรวจลิงก์ใหม่อีกครั้ง") from None
    if time.time() - meta.get("created", 0) > PREVIEW_TTL:
        shutil.rmtree(folder, ignore_errors=True)
        raise FontUrlError("รายการตรวจลิงก์นี้หมดอายุแล้ว — กดตรวจลิงก์ใหม่อีกครั้ง")
    return meta, folder


def preview_font_file(token: str, style: str) -> bytes:
    """ไฟล์ฟอนต์ชั่วคราวสำหรับ @font-face ตัวอย่างในหน้าต่าง (เบราว์เซอร์แนบ header ไม่ได้ — token สุ่มคือสิทธิ์)"""
    meta, folder = _load_preview(token)
    if style not in {s["style"] for s in meta["styles"]}:
        raise FontUrlError("ไม่มีสไตล์นี้")
    return (folder / f"{style}.ttf").read_bytes()


def install_preview(token: str, user_id: int, label: str | None = None) -> "fonts.FontOption":
    """ติดตั้งจากรายการที่ตรวจไว้: ตัวปกติก่อน (สร้าง family) แล้วสไตล์อื่นเข้า family เดียวกัน → ลบไฟล์ชั่วคราว"""
    meta, folder = _load_preview(token)
    if meta.get("user_id") != user_id:
        raise FontUrlError("รายการตรวจลิงก์นี้หมดอายุแล้ว — กดตรวจลิงก์ใหม่อีกครั้ง")
    family = meta["family"]
    name = (label or "").strip()[:80] or family
    order = [s["style"] for s in sorted(meta["styles"], key=lambda s: STYLES.index(s["style"]))]
    regular = fonts.install_custom_font((folder / "regular.ttf").read_bytes(), f"{family}-Regular.ttf", name, user_id)
    for style in order:
        if style == "regular":
            continue
        fonts.install_custom_font((folder / f"{style}.ttf").read_bytes(), f"{family}-{style}.ttf", None, user_id,
                                  family_key=regular.key, style=style)
    shutil.rmtree(folder, ignore_errors=True)
    return regular
