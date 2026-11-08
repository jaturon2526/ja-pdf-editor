"""ไฟล์ฟอนต์ที่ผู้ใช้ติดตั้งเอง โหลดได้เฉพาะเจ้าของ (token ใน file_url)"""
from pathlib import Path

FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Kanit-Regular.ttf"


def _install(client, headers):
    r = client.post("/edit/fonts/install", headers=headers,
                    files={"file": ("MyFont.ttf", FONT.read_bytes(), "font/ttf")}, data={"label": "My Font"})
    assert r.status_code == 200, r.text
    return r.json()["installed"]


def _path(url):
    return url.replace("/api", "", 1)


def test_private_font_needs_owner_token(client, make_user):
    _, owner = make_user()
    _, other = make_user()
    font = _install(client, owner)
    assert "?t=" in font["file_url"]

    ok = client.get(_path(font["file_url"]))
    assert ok.status_code == 200 and ok.content == FONT.read_bytes()
    assert ok.headers["cache-control"].startswith("private")

    assert client.get(f"/edit/fonts/{font['key']}/file").status_code == 404
    assert client.get(f"/edit/fonts/{font['key']}/file?user_id=1").status_code == 404
    assert client.get(f"/edit/fonts/{font['key']}/file?t=1.9999999999.forged").status_code == 404

    # token ของผู้ใช้อื่นไม่ได้ฟอนต์ของเจ้าของ (ได้ฟอนต์ตั้งต้นของระบบแทน)
    from app.core.security import make_resource_token

    other_id = client.get("/auth/me", headers=other).json()["id"]
    r = client.get(f"/edit/fonts/{font['key']}/file?t={make_resource_token('font-file', other_id)}")
    assert r.content != FONT.read_bytes()


def test_global_fonts_are_public(client, make_user):
    _, headers = make_user()
    fonts = client.get("/edit/fonts", headers=headers).json()
    builtin = next(f for f in fonts if not f["removable"])
    assert "?t=" not in builtin["file_url"]
    r = client.get(_path(builtin["file_url"]))
    assert r.status_code == 200 and r.headers["cache-control"].startswith("public")
