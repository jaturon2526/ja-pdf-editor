"""ติดตั้งฟอนต์จากไฟล์: ชนิดไฟล์, WOFF/WOFF2, TTC, ไฟล์ซ้ำ, ชื่อยาว, คำเตือน (ไม่มีไทย/ห้ามฝัง), ข้อความที่ฟอนต์ไม่มีตัวอักษร"""
import io
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from tests.conftest import make_pdf_bytes

FONTS = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts"
SARABUN = (FONTS / "Sarabun-Regular.ttf").read_bytes()


def _variant(src: bytes, flavor=None, fs_type=None, drop_thai=False) -> bytes:
    f = TTFont(io.BytesIO(src))
    if fs_type is not None:
        f["OS/2"].fsType = fs_type
    if drop_thai:
        for t in f["cmap"].tables:
            t.cmap = {k: v for k, v in t.cmap.items() if not 0x0E00 <= k <= 0x0E7F}
    name = f["name"]
    for rec in name.names:   # ไฟล์ต่างกัน → sha256 ต่างกัน (ไม่ชนกับการตรวจไฟล์ซ้ำ)
        if rec.nameID == 5:
            rec.string = f"Version test {flavor}{fs_type}{drop_thai}"
    f.flavor = flavor
    buf = io.BytesIO()
    f.save(buf)
    return buf.getvalue()


def _install(client, h, name, data, label="ทดสอบ", **extra):
    return client.post("/edit/fonts/install", headers=h, files={"file": (name, data, "font/ttf")},
                       data={"label": label, **extra})


@pytest.mark.parametrize("flavor,name", [("woff", "web.woff"), ("woff2", "web.woff2"), ("woff", "renamed.ttf")])
def test_web_fonts_are_converted(client, make_user, flavor, name):
    _, h = make_user()
    r = _install(client, h, name, _variant(SARABUN, flavor=flavor), label=f"Web {flavor} {name}")
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []
    data = client.get(r.json()["installed"]["file_url"].replace("/api", "", 1)).content
    assert data[:4] == b"\x00\x01\x00\x00"   # เก็บเป็น TrueType ธรรมดา


@pytest.mark.parametrize("name,data,msg", [
    ("a.ttc", b"ttcf" + b"\x00" * 200, ".ttc"),
    ("a.otf", b"ttcf" + b"\x00" * 200, ".ttc"),
    ("a.ttf", b"\x00\x01\x00\x00" + b"x" * 200, "ไม่ใช่ไฟล์ฟอนต์"),
    ("a.pdf", SARABUN, "รองรับเฉพาะ"),
])
def test_bad_files_rejected(client, make_user, name, data, msg):
    _, h = make_user()
    r = _install(client, h, name, data)
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_duplicate_and_long_label(client, make_user):
    _, h = make_user()
    r = _install(client, h, "a.ttf", SARABUN, label="x" * 3000)   # เดิม 500: ชื่อไฟล์ยาวเกินระบบไฟล์
    assert r.status_code == 200, r.text
    assert len(r.json()["installed"]["label"]) <= 80
    r = _install(client, h, "a.ttf", SARABUN, label="อีกครั้ง")
    assert r.status_code == 400 and "ติดตั้งไฟล์ฟอนต์นี้ไว้แล้ว" in r.json()["detail"]


def test_oversized_file(client, make_user, monkeypatch):
    from app.services import fonts

    monkeypatch.setattr(fonts, "MAX_FONT_FILE_BYTES", 1000)
    _, h = make_user()
    r = _install(client, h, "a.ttf", SARABUN)
    assert r.status_code == 400 and "ใหญ่เกิน" in r.json()["detail"]


def test_warnings_for_latin_only_and_restricted(client, make_user):
    _, h = make_user()
    r = _install(client, h, "latin.ttf", _variant(SARABUN, drop_thai=True, fs_type=2), label="Latin")
    assert r.status_code == 200, r.text
    w = " ".join(r.json()["warnings"])
    assert "ไม่มีตัวอักษรไทย" in w and "ห้ามฝัง" in w


def test_text_with_glyphs_missing_from_font_is_refused_without_touching_page(client, make_user, upload):
    _, h = make_user()
    key = _install(client, h, "latin.ttf", _variant(SARABUN, drop_thai=True), label="Latin").json()["installed"]["key"]
    sid = upload(h, make_pdf_bytes(pages=1, text="Hello"))
    body = {"page_number": 0, "rect": {"x0": 72, "y0": 200, "x1": 400, "y1": 240}, "new_text": "ทดสอบ Test",
            "fontname": key, "fontsize": 14}
    r = client.post(f"/edit/{sid}/text", headers=h, json=body)
    assert r.status_code == 400 and "ไม่มีตัวอักษร" in r.json()["detail"] and "ท" in r.json()["detail"]
    assert client.post(f"/edit/{sid}/text", headers=h, json={**body, "new_text": "Only English 123"}).status_code == 200
    r = client.post(f"/edit/{sid}/text", headers=h, json={**body, "new_text": "ภาษาไทย", "fontname": "sarabun"})
    assert r.status_code == 200
