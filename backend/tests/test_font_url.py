"""ติดตั้งฟอนต์จากลิงก์ (F1): แยกลิงก์, รับเฉพาะ https ของ Google Fonts, ดาวน์โหลดจาก fonts.gstatic.com เท่านั้น
ไม่ออกอินเทอร์เน็ตจริง — แทน opener ด้วยเว็บจำลอง"""
import io
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from app.services import font_url
from app.services.font_url import FontLink, FontUrlError, fetch_google_font, parse_font_link

FONTS = Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts"


def _latin_only_font() -> bytes:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    f = TTFont(str(FONTS / "Sarabun-Regular.ttf"))
    s = subset.Subsetter()
    s.populate(text="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ")
    s.subset(f)
    buf = io.BytesIO()
    f.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- parse_font_link

@pytest.mark.parametrize("text, family, styles", [
    ("https://fonts.google.com/specimen/Kanit", "Kanit", list(font_url.STYLES)),
    ("https://fonts.google.com/specimen/Noto+Sans+Thai?query=thai", "Noto Sans Thai", list(font_url.STYLES)),
    ("fonts.google.com/specimen/Sarabun", "Sarabun", list(font_url.STYLES)),
    ("https://fonts.google.com/noto/specimen/Noto+Sans+Thai", "Noto Sans Thai", list(font_url.STYLES)),
    ("https://fonts.googleapis.com/css2?family=Prompt:ital,wght@0,400;0,700;1,400&display=swap",
     "Prompt", ["regular", "bold", "italic"]),
    ("https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;700&display=swap", "Noto Sans Thai", ["regular", "bold"]),
    ("https://fonts.googleapis.com/css?family=Sarabun:400,700i", "Sarabun", ["regular", "bold_italic"]),
    ("  Kanit  ", "Kanit", list(font_url.STYLES)),
])
def test_parse_accepts_google_fonts(text, family, styles):
    link = parse_font_link(text)
    assert link.family == family and link.styles == styles


@pytest.mark.parametrize("text, msg", [
    ("http://fonts.google.com/specimen/Kanit", "https"),
    ("https://evil.example.com/specimen/Kanit", "Google Fonts"),
    ("https://fonts.google.com.evil.com/specimen/Kanit", "Google Fonts"),
    ("https://evilfonts.google.com/specimen/Kanit", "Google Fonts"),
    ("https://fonts.gstatic.com/s/kanit/v1/x.ttf", "Google Fonts"),
    ("https://127.0.0.1/specimen/Kanit", "Google Fonts"),
    ("https://fonts.google.com:8443/specimen/Kanit", "Google Fonts"),
    ("https://user:pw@fonts.google.com/specimen/Kanit", "Google Fonts"),
    ("https://raw.githubusercontent.com/x/y/main/font.ttf", "Google Fonts"),
    ("file:///etc/passwd", "https"),
    ("https://fonts.google.com/about", "หน้าฟอนต์"),
    ("https://fonts.googleapis.com/css2?family=Kanit|Prompt", "หลายฟอนต์"),
    ("Kanit<script>", "ชื่อฟอนต์"),
    ("", "กรุณาใส่"),
])
def test_parse_rejects_everything_else(text, msg):
    with pytest.raises(FontUrlError, match=msg):
        parse_font_link(text)


# ---------------------------------------------------------------- เว็บจำลอง

class _Resp:
    def __init__(self, body: bytes, headers=None):
        self._buf = io.BytesIO(body)
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _css(url: str, thai: bool = True) -> bytes:
    rng = "unicode-range: U+0E01-0E5B, U+200C-200D;" if thai else "unicode-range: U+0000-00FF;"
    return (f"@font-face {{ font-family: 'X'; src: url(https://fonts.gstatic.com/s/latin/a.ttf) format('truetype'); "
            f"unicode-range: U+0000-00FF; }}\n@font-face {{ font-family: 'X'; src: url({url}) format('truetype'); {rng} }}").encode()


@pytest.fixture
def web(monkeypatch):
    """routes: url (ไม่สนลำดับ query) → bytes | ("redirect", ใหม่) | ("status", code)"""
    routes, seen = {}, []

    def fake_open(req, timeout=None):
        url = req.full_url
        seen.append(url)
        r = routes.get(url)
        if r is None:
            raise urllib.error.HTTPError(url, 404, "nf", Message(), None)
        if isinstance(r, tuple) and r[0] == "redirect":
            h = Message()
            h["Location"] = r[1]
            raise urllib.error.HTTPError(url, 302, "moved", h, None)
        if isinstance(r, tuple) and r[0] == "status":
            raise urllib.error.HTTPError(url, r[1], "x", Message(), None)
        return _Resp(r)

    monkeypatch.setattr(font_url._opener, "open", fake_open)
    return routes, seen


def _register_family(routes, family="Sarabun", styles=("regular", "bold", "italic", "bold_italic")):
    files = {"regular": "Sarabun-Regular.ttf", "bold": "Sarabun-Bold.ttf", "italic": "Sarabun-Italic.ttf",
             "bold_italic": "Sarabun-BoldItalic.ttf"}
    for st in font_url.STYLES:
        css_url = font_url._css_url(family, st)
        if st in styles:
            ttf = f"https://fonts.gstatic.com/s/{family.lower()}/{st}.ttf"
            routes[css_url] = _css(ttf)
            routes[ttf] = (FONTS / files[st]).read_bytes()
        else:
            routes[css_url] = ("status", 400)


def test_fetch_all_four_styles_with_thai(web):
    routes, seen = web
    _register_family(routes)
    got = fetch_google_font(FontLink("Sarabun"))
    assert [s.style for s in got] == ["regular", "bold", "italic", "bold_italic"]
    assert all(s.has_thai for s in got)
    assert all(s.source_url.endswith(f"/{s.style}.ttf") for s in got)       # เลือกไฟล์ชุดไทย ไม่ใช่ latin
    assert not any("/latin/" in u for u in seen)


def test_font_without_italic_installs_available_styles(web):
    routes, _ = web
    _register_family(routes, "Kanit", styles=("regular", "bold"))
    assert [s.style for s in fetch_google_font(FontLink("Kanit"))] == ["regular", "bold"]


def test_unknown_family(web):
    routes, _ = web
    _register_family(routes, "Nope", styles=())
    with pytest.raises(FontUrlError, match="ไม่พบฟอนต์"):
        fetch_google_font(FontLink("Nope"))


def test_latin_only_font_is_flagged(web):
    routes, _ = web
    css_url = font_url._css_url("Roboto", "regular")
    routes[css_url] = b"@font-face { src: url(https://fonts.gstatic.com/s/roboto/r.ttf) format('truetype'); }"
    routes["https://fonts.gstatic.com/s/roboto/r.ttf"] = _latin_only_font()
    got = fetch_google_font(FontLink("Roboto", ["regular"]))
    assert got[0].has_thai is False


def test_font_file_must_come_from_gstatic(web):
    routes, seen = web
    css_url = font_url._css_url("Evil", "regular")
    routes[css_url] = (b"@font-face { src: url(https://evil.example.com/x.ttf) format('truetype'); }")
    with pytest.raises(FontUrlError):
        fetch_google_font(FontLink("Evil", ["regular"]))
    assert not any("evil.example.com" in u for u in seen)


def test_redirect_outside_allowed_hosts_is_refused(web):
    routes, seen = web
    css_url = font_url._css_url("Sarabun", "regular")
    ttf = "https://fonts.gstatic.com/s/sarabun/regular.ttf"
    routes[css_url] = _css(ttf)
    routes[ttf] = ("redirect", "http://169.254.169.254/latest/meta-data")
    with pytest.raises(FontUrlError, match="ไม่ใช่แหล่งฟอนต์ที่อนุญาต"):
        fetch_google_font(FontLink("Sarabun", ["regular"]))
    assert not any("169.254" in u for u in seen)


def test_redirect_inside_gstatic_is_followed(web):
    routes, _ = web
    css_url = font_url._css_url("Sarabun", "regular")
    ttf = "https://fonts.gstatic.com/s/sarabun/regular.ttf"
    routes[css_url] = _css(ttf)
    routes[ttf] = ("redirect", "https://fonts.gstatic.com/s/sarabun/v2/regular.ttf")
    routes["https://fonts.gstatic.com/s/sarabun/v2/regular.ttf"] = (FONTS / "Sarabun-Regular.ttf").read_bytes()
    assert fetch_google_font(FontLink("Sarabun", ["regular"]))[0].has_thai


def test_oversized_file_is_refused(web, monkeypatch):
    routes, _ = web
    monkeypatch.setattr(font_url, "MAX_FONT_BYTES", 1000)
    _register_family(routes, styles=("regular",))
    with pytest.raises(FontUrlError, match="ใหญ่เกิน"):
        fetch_google_font(FontLink("Sarabun", ["regular"]))


def test_not_a_font_is_skipped(web):
    routes, _ = web
    css_url = font_url._css_url("Junk", "regular")
    routes[css_url] = _css("https://fonts.gstatic.com/s/junk/r.ttf")
    routes["https://fonts.gstatic.com/s/junk/r.ttf"] = b"<html>not a font</html>"
    with pytest.raises(FontUrlError):
        fetch_google_font(FontLink("Junk", ["regular"]))


def test_extra_trusted_host_from_settings(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FONT_URL_ALLOWED_HOSTS", "fonts.google.com,fonts.googleapis.com,fonts.bunny.net")
    assert parse_font_link("https://fonts.bunny.net/css?family=kanit:400").family == "kanit"
    with pytest.raises(FontUrlError):
        parse_font_link("https://cdn.example.com/css?family=kanit")


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(font_url, "_rate", {})
    monkeypatch.setattr(font_url, "RATE_LIMIT", 3)
    for _ in range(3):
        font_url.check_rate_limit(42)
    with pytest.raises(FontUrlError, match="บ่อยเกินไป"):
        font_url.check_rate_limit(42)
    font_url.check_rate_limit(43)       # คนละผู้ใช้ไม่เกี่ยวกัน


# ---------------------------------------------------------------- F2: ตรวจ → ติดตั้ง ผ่าน API

@pytest.fixture
def no_rate(monkeypatch):
    monkeypatch.setattr(font_url, "_rate", {})


def test_preview_then_install_four_styles(client, make_user, web, no_rate):
    routes, _ = web
    _register_family(routes, "Sarabun")
    _, headers = make_user()
    r = client.post("/edit/fonts/url/preview", headers=headers, json={"url": "https://fonts.google.com/specimen/Sarabun"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["family"] == "Sarabun" and p["has_thai"] is True and p["exists"] == "global"
    assert [s["style"] for s in p["styles"]] == ["regular", "bold", "italic", "bold_italic"]
    # ไฟล์ตัวอย่างสำหรับ @font-face
    f = client.get(p["styles"][1]["file_url"].removeprefix("/api"))
    assert f.status_code == 200 and f.headers["content-type"] == "font/ttf" and len(f.content) > 1000

    r = client.post("/edit/fonts/url/install", headers=headers, json={"token": p["token"], "label": "Sarabun เว็บ"})
    assert r.status_code == 200, r.text
    fam = next(x for x in client.get("/edit/font-families", headers=headers).json() if x["label"] == "Sarabun เว็บ")
    assert fam["removable"] and all(fam["styles"][s] for s in ("regular", "bold", "italic", "bold_italic"))
    # token ใช้ครั้งเดียว
    assert client.post("/edit/fonts/url/install", headers=headers, json={"token": p["token"]}).status_code == 400


def test_font_without_italic_reports_missing_styles(client, make_user, web, no_rate):
    routes, _ = web
    _register_family(routes, "Kanit", styles=("regular", "bold"))
    _, headers = make_user()
    p = client.post("/edit/fonts/url/preview", headers=headers, json={"url": "Kanit"}).json()
    assert [s["style"] for s in p["styles"]] == ["regular", "bold"]
    assert p["missing_styles"] == ["italic", "bold_italic"]
    r = client.post("/edit/fonts/url/install", headers=headers, json={"token": p["token"]})
    assert r.status_code == 200 and r.json()["installed"]["label"] == "Kanit"


def test_other_user_cannot_use_token(client, make_user, web, no_rate):
    routes, _ = web
    _register_family(routes, "Sarabun", styles=("regular",))
    _, owner = make_user()
    _, other = make_user()
    p = client.post("/edit/fonts/url/preview", headers=owner, json={"url": "Sarabun"}).json()
    assert client.post("/edit/fonts/url/install", headers=other, json={"token": p["token"]}).status_code == 400
    assert client.post("/edit/fonts/url/install", headers=owner, json={"token": p["token"]}).status_code == 200


def test_expired_or_bad_token(client, make_user, web, no_rate, monkeypatch):
    routes, _ = web
    _register_family(routes, "Sarabun", styles=("regular",))
    _, headers = make_user()
    p = client.post("/edit/fonts/url/preview", headers=headers, json={"url": "Sarabun"}).json()
    monkeypatch.setattr(font_url, "PREVIEW_TTL", -1)
    r = client.post("/edit/fonts/url/install", headers=headers, json={"token": p["token"]})
    assert r.status_code == 400 and "หมดอายุ" in r.json()["detail"]
    assert client.post("/edit/fonts/url/install", headers=headers, json={"token": "../../etc"}).status_code == 400
    assert client.get("/edit/fonts/url/preview/../../x/regular").status_code == 404


def test_preview_rejects_untrusted_link(client, make_user, no_rate):
    _, headers = make_user()
    r = client.post("/edit/fonts/url/preview", headers=headers, json={"url": "https://evil.example.com/font.ttf"})
    assert r.status_code == 400 and "Google Fonts" in r.json()["detail"]


def test_preview_requires_login(client):
    assert client.post("/edit/fonts/url/preview", json={"url": "Kanit"}).status_code == 401
