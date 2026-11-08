"""รูปโปรไฟล์ (services/avatar_service.py + /auth/avatar/*): อีโมจิ 18 แบบที่วาดด้วย Pillow เปลี่ยนสีได้,
อัปโหลดรูป (ครอปสี่เหลี่ยม 256px, หมุนตาม EXIF, ไม่มี EXIF/GPS ติดไป), สิทธิ์ดูรูปด้วย token, ลบรูป"""
import io

import pytest
from PIL import Image

from app.services import avatar_service


def test_all_faces_render_with_colors():
    assert len(avatar_service.FACES) >= 15
    for face in avatar_service.FACES:
        img = Image.open(io.BytesIO(avatar_service.render_emoji(face, "#60A5FA", "#FEF3C7", 64)))
        assert img.size == (64, 64)
        assert img.getpixel((2, 2)) == (254, 243, 199)  # มุมเป็นสีพื้นหลัง
    with pytest.raises(ValueError):
        avatar_service.render_emoji("nope")
    with pytest.raises(ValueError):
        avatar_service.render_emoji("smile", "red", "#FFFFFF")


def _jpeg_with_exif(w=400, h=200, orientation=6):
    img = Image.new("RGB", (w, h), (200, 30, 30))
    img.paste((30, 30, 200), (0, 0, w // 4, h))  # แถบน้ำเงินด้านซ้าย
    exif = Image.Exif()
    exif[0x0112] = orientation          # หมุน 90°
    exif[0x8825] = {2: (13.0, 45.0, 0.0)}  # GPS
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_upload_is_cropped_square_without_metadata():
    out = Image.open(io.BytesIO(avatar_service.process_upload(_jpeg_with_exif())))
    assert out.size == (256, 256) and out.format == "PNG"
    assert not out.info.get("exif") and not out.getexif()
    with pytest.raises(ValueError, match="ไม่ใช่รูปภาพ"):
        avatar_service.process_upload(b"%PDF-1.4 not an image")


def test_avatar_api_flow(client, make_user):
    uid, h = make_user()
    assert client.get("/auth/me", headers=h).json()["avatar_url"] is None
    faces = client.get("/auth/avatar/emojis", headers=h).json()["faces"]
    assert {"key": "smile", "label": "ยิ้ม"} in faces
    prev = client.get("/auth/avatar/emoji-preview", headers=h, params={"face": "cat", "face_color": "#34D399"})
    assert prev.status_code == 200 and prev.headers["content-type"] == "image/png"

    r = client.post("/auth/avatar/emoji", headers=h, json={"face": "cool", "face_color": "#60a5fa", "bg_color": "#e0f2fe"})
    assert r.status_code == 200, r.text
    me = client.get("/auth/me", headers=h).json()
    assert me["avatar_emoji"] == "cool|#60A5FA|#E0F2FE" and me["avatar_url"].startswith(f"/api/auth/avatar/{uid}.png?t=")
    url = me["avatar_url"].replace("/api", "", 1)
    img = client.get(url)
    assert img.status_code == 200 and Image.open(io.BytesIO(img.content)).size == (256, 256)
    # token ของคนอื่น / ไม่มี token → 403
    other_uid, oh = make_user()
    client.post("/auth/avatar/emoji", headers=oh, json={"face": "smile"})
    other_url = client.get("/auth/me", headers=oh).json()["avatar_url"].replace("/api", "", 1)
    token = other_url.split("t=")[1].split("&")[0]
    assert client.get(f"/auth/avatar/{uid}.png?t={token}").status_code == 403
    assert client.get(f"/auth/avatar/{uid}.png").status_code == 403

    up = client.post("/auth/avatar/upload", headers=h, files={"file": ("me.jpg", _jpeg_with_exif(), "image/jpeg")})
    assert up.status_code == 200 and client.get("/auth/me", headers=h).json()["avatar_emoji"] is None
    bad = client.post("/auth/avatar/upload", headers=h, files={"file": ("x.pdf", b"%PDF", "application/pdf")})
    assert bad.status_code == 400

    assert client.delete("/auth/avatar", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).json()["avatar_url"] is None
    assert client.get(url).status_code == 404
