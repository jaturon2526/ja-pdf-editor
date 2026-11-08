"""แทรก/ลบ/ย้ายรูปภาพ และแทรกข้อความ — ไม่ลบข้อความหรือรูปอื่นที่อยู่ใกล้/ใต้"""
import io
from pathlib import Path

import fitz
from PIL import Image

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")


def _png(color=(255, 0, 0), size=(40, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _doc_with_logo_and_text(background=False, logo_pages=1):
    d = fitz.open()
    for i in range(logo_pages):
        p = d.new_page()
        if background:
            p.insert_image(p.rect, stream=_png((230, 230, 230), (60, 80)))  # รูปสแกนเต็มหน้า
        p.insert_image(fitz.Rect(72, 72, 172, 172), stream=_png())
        p.insert_font(fontname="sar", fontfile=FONT)
        p.insert_text((80, 120), "ข้อความบนรูป", fontname="sar", fontsize=12)
        p.insert_text((80, 260), "ข้อความใต้ตำแหน่งใหม่", fontname="sar", fontsize=12)
    return d.tobytes()


def _download(client, h, sid):
    return fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)


def _logo(client, h, sid, page=0):
    imgs = client.get(f"/edit/{sid}/page/{page}/images", headers=h).json()
    return next(i for i in imgs if abs(i["rect"]["x0"] - 72) < 1)


def test_delete_image_keeps_text_and_background_scan(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc_with_logo_and_text(background=True), name="doc.pdf")
    logo = _logo(client, h, sid)
    r = client.delete(f"/edit/{sid}/page/0/image/{logo['xref']}", headers=h, params={
        "x0": 72, "y0": 72, "x1": 172, "y1": 172})
    assert r.status_code == 200, r.text
    out = _download(client, h, sid)
    text = out[0].get_text()
    assert "ข้อความบนรูป" in text  # เดิม: redaction ลบข้อความบนรูปด้วย
    visible = [i for i in out[0].get_image_info(xrefs=True)]
    # รูปสแกนเต็มหน้ายังอยู่ (เดิม IMAGE_REMOVE ลบทุกรูปที่ทับกรอบ — หน้าสแกนหายทั้งหน้า)
    assert any(abs(i["bbox"][2] - i["bbox"][0] - out[0].rect.width) < 1 for i in visible)
    # โลโก้มองไม่เห็นแล้ว: พิกเซลกลางโลโก้ไม่ใช่สีแดง
    pix = out[0].get_pixmap(clip=fitz.Rect(150, 150, 151, 151))
    assert pix.pixel(0, 0)[:3] != (255, 0, 0)


def test_move_image_keeps_text(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc_with_logo_and_text(), name="doc.pdf")
    logo = _logo(client, h, sid)
    r = client.post(f"/edit/{sid}/page/0/image/{logo['xref']}/reposition", headers=h, json={
        "old_rect": logo["rect"], "new_rect": {"x0": 72, "y0": 240, "x1": 172, "y1": 340}})
    assert r.status_code == 200, r.text
    out = _download(client, h, sid)
    text = out[0].get_text()
    assert "ข้อความบนรูป" in text and "ข้อความใต้ตำแหน่งใหม่" in text  # เดิม: ทั้งสองหาย
    assert out[0].get_pixmap(clip=fitz.Rect(100, 300, 101, 301)).pixel(0, 0)[:3] == (255, 0, 0)
    assert out[0].get_pixmap(clip=fitz.Rect(150, 150, 151, 151)).pixel(0, 0)[:3] != (255, 0, 0)
    assert not Path("debug_reposition.png").exists()


def test_delete_shared_image_only_on_this_page(client, make_user, upload):
    d = fitz.open()
    d.new_page()
    d.new_page()
    x = d[0].insert_image(fitz.Rect(72, 72, 172, 172), stream=_png())
    d[1].insert_image(fitz.Rect(72, 72, 172, 172), xref=x)  # โลโก้เดียวกันสองหน้า
    _, h = make_user()
    sid = upload(h, d.tobytes(), name="doc.pdf")
    logo = _logo(client, h, sid, page=0)
    assert client.delete(f"/edit/{sid}/page/0/image/{logo['xref']}", headers=h).status_code == 200
    out = _download(client, h, sid)
    red = lambda pg: out[pg].get_pixmap(clip=fitz.Rect(100, 100, 101, 101)).pixel(0, 0)[:3] == (255, 0, 0)
    assert not red(0) and red(1)


def test_insert_text_does_not_erase_underlying_text(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc_with_logo_and_text(), name="doc.pdf")
    r = client.post(f"/edit/{sid}/text", headers=h, json={
        "page_number": 0, "rect": {"x0": 70, "y0": 245, "x1": 400, "y1": 275}, "new_text": "เติมคำ",
        "fontsize": 12, "fontname": "sarabun", "block_id": "insert-1"})
    assert r.status_code == 200, r.text
    text = _download(client, h, sid)[0].get_text()
    assert "ข้อความใต้ตำแหน่งใหม่" in text  # เดิม: ข้อความใต้กล่องที่ลากถูกลบ
    assert "เติมคำ" in text


def test_insert_image_bad_rect(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc_with_logo_and_text(), name="doc.pdf")
    r = client.post(f"/edit/{sid}/page/0/image", headers=h, data={"x0": 100, "y0": 100, "x1": 100, "y1": 100},
                    files={"file": ("a.png", _png(), "image/png")})
    assert r.status_code == 400
    r = client.post(f"/edit/{sid}/page/0/image", headers=h, data={"x0": 300, "y0": 300, "x1": 200, "y1": 200},
                    files={"file": ("a.png", _png(), "image/png")})
    assert r.status_code == 200  # ลากย้อนทางได้


def test_reedit_inserted_text_keeps_underlying_text(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc_with_logo_and_text(), name="doc.pdf")
    body = {"page_number": 0, "rect": {"x0": 70, "y0": 245, "x1": 400, "y1": 275}, "new_text": "เติมคำ",
            "fontsize": 12, "fontname": "sarabun", "block_id": "insert-1"}
    assert client.post(f"/edit/{sid}/text", headers=h, json=body).status_code == 200
    blocks = client.get(f"/edit/{sid}/page/0/text-blocks", headers=h).json()
    mine = next(b for b in blocks if "เติมคำ" in b["text"])
    body2 = {**body, "new_text": "แก้คำ", "block_id": mine["block_id"], "previous_rect": mine["rect"], "rect": mine["rect"]}
    r = client.post(f"/edit/{sid}/text", headers=h, json=body2)
    assert r.status_code == 200, r.text
    text = _download(client, h, sid)[0].get_text()
    assert "ข้อความใต้ตำแหน่งใหม่" in text and "แก้คำ" in text and "เติมคำ" not in text
