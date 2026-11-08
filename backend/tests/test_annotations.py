"""คำอธิบายประกอบ: กล่องข้อความ/กรอบมีข้อความไทยในไฟล์จริง (ทุกโปรแกรมเห็น), ไม่ทำลาย annotation ของโปรแกรมอื่น,
ไฮไลต์หลายบรรทัดเปลี่ยนสีแล้วไม่กลายเป็นแถบทึบ, กรอบผิดรูปไม่ทำให้ 500"""
import fitz
import pytest


def _blank(n=1):
    d = fitz.open()
    for _ in range(n):
        d.new_page()
    return d.tobytes()


def _download(client, h, sid):
    r = client.get(f"/pdf/{sid}/download", headers=h)
    assert r.status_code == 200
    return fitz.open("pdf", r.content)


def _add(client, h, sid, **kw):
    body = {"page_number": 0, **kw}
    r = client.post(f"/annotation/{sid}", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _appearance_text(doc, xref):
    """ข้อความใน appearance stream ของ annotation (สิ่งที่โปรแกรมอื่นวาด)"""
    ap = doc.xref_get_key(xref, "AP/N")
    assert ap[0] == "xref", ap
    tmp = fitz.open()
    page = tmp.new_page()
    src = fitz.open("pdf", doc.tobytes())
    page.show_pdf_page(page.rect, src, 0)
    return page.get_text()


@pytest.mark.parametrize("kind", ["freetext", "rect"])
def test_text_box_appearance_has_thai_text(client, make_user, upload, kind):
    _, h = make_user()
    sid = upload(h, _blank(), name="doc.pdf")
    a = _add(client, h, sid, type=kind, content="สวัสดีครับ Hello", fontsize=14,
             rect={"x0": 72, "y0": 72, "x1": 400, "y1": 140})
    doc = _download(client, h, sid)
    annot = doc[0].load_annot(a["xref"]) if doc[0].load_annot(a["xref"]) else next(doc[0].annots())
    assert doc.xref_get_key(annot.xref, "AP/N")[0] == "xref"  # เดิม FreeText: AP null · rect: มีแต่เส้นกรอบ
    # วาดหน้าแบบรวม annotation (เหมือนโปรแกรมอ่าน PDF) แล้วอ่านข้อความกลับ: ภาษาไทยต้องครบ
    baked = fitz.open("pdf", doc.tobytes())
    baked.bake(annots=True, widgets=True)
    text = baked[0].get_text()
    assert "สวัสดีครับ" in text.replace("\n", "") and "Hello" in text


def test_render_does_not_destroy_foreign_freetext(client, make_user, upload):
    d = fitz.open()
    p = d.new_page()
    a = p.add_freetext_annot(fitz.Rect(72, 72, 300, 100), "From Acrobat", fontsize=12)
    a.update()
    _, h = make_user()
    sid = upload(h, d.tobytes(), name="doc.pdf")
    assert client.get(f"/pdf/{sid}/page/0", headers=h).status_code == 200
    out = _download(client, h, sid)
    ft = next(out[0].annots())
    assert out.xref_get_key(ft.xref, "AP/N")[0] == "xref"  # เดิม: แค่เปิดดูหน้า AP ถูกลบทิ้ง ข้อความหายในไฟล์
    assert ft.info["content"] == "From Acrobat"


def test_legacy_null_ap_text_box_is_migrated(client, make_user, upload):
    """กล่องข้อความที่สร้างก่อนเวอร์ชันนี้ (AP = null) ได้ appearance ข้อความไทยตอนเปิดดู/ดาวน์โหลด"""
    d = fitz.open()
    p = d.new_page()
    a = p.add_freetext_annot(fitz.Rect(72, 72, 300, 110), "ทดสอบ", fontsize=12)
    a.set_info(content="กล่องเก่า", title="sarabun:12|")
    d.xref_set_key(a.xref, "AP", "null")
    _, h = make_user()
    sid = upload(h, d.tobytes(), name="doc.pdf")
    out = _download(client, h, sid)
    baked = fitz.open("pdf", out.tobytes())
    baked.bake(annots=True)
    assert "กล่องเก่า" in baked[0].get_text().replace("\n", "")


def test_flatten_keeps_rect_text(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _blank(), name="doc.pdf")
    _add(client, h, sid, type="rect", content="ข้อความในกรอบ", rect={"x0": 72, "y0": 72, "x1": 400, "y1": 140})
    r = client.post(f"/pdf/{sid}/flatten", headers=h)
    assert r.status_code == 200, r.text
    out = _download(client, h, sid)
    assert list(out[0].annots()) == []
    assert "ข้อความในกรอบ" in out[0].get_text().replace("\n", "")  # เดิม: หายตอนรวมเลเยอร์


def test_recolor_multiline_highlight_keeps_quads(client, make_user, upload):
    d = fitz.open()
    p = d.new_page()
    q1, q2 = fitz.Rect(72, 72, 400, 86), fitz.Rect(72, 100, 200, 114)
    hl = p.add_highlight_annot([q1.quad, q2.quad])
    hl.update()
    _, h = make_user()
    sid = upload(h, d.tobytes(), name="doc.pdf")
    xref = client.get(f"/annotation/{sid}/page/0", headers=h).json()[0]["xref"]
    r = client.patch(f"/annotation/{sid}", headers=h, json={"page_number": 0, "xref": xref, "color": [0.2, 0.8, 0.2]})
    assert r.status_code == 200, r.text
    out = _download(client, h, sid)
    annot = next(out[0].annots())
    assert len(annot.vertices) == 8  # 2 quads — เดิมกลายเป็นกรอบเดียวทึบทับช่องว่างระหว่างบรรทัด
    assert [round(c, 1) for c in annot.colors["stroke"]] == [0.2, 0.8, 0.2]


@pytest.mark.parametrize("body,code", [
    ({"type": "rect", "rect": {"x0": 400, "y0": 140, "x1": 72, "y1": 72}}, 200),   # ลากย้อนทาง
    ({"type": "freetext", "content": "x", "rect": {"x0": 72, "y0": 72, "x1": 72, "y1": 72}}, 400),
    ({"type": "rect", "rect": {"x0": 900, "y0": 900, "x1": 950, "y1": 950}}, 400),   # นอกหน้า
    ({"type": "highlight", "color": [2, 0, 0], "rect": {"x0": 72, "y0": 72, "x1": 100, "y1": 90}}, 422),
    ({"type": "freetext", "fontsize": 0, "content": "x", "rect": {"x0": 72, "y0": 72, "x1": 100, "y1": 90}}, 422),
    ({"type": "text_note", "content": "n", "rect": {"x0": 590, "y0": 840, "x1": 600, "y1": 850}}, 200),
])
def test_bad_geometry_is_handled(client, make_user, upload, body, code):
    _, h = make_user()
    sid = upload(h, _blank(), name="doc.pdf")
    r = client.post(f"/annotation/{sid}", headers=h, json={"page_number": 0, **body})
    assert r.status_code == code, r.text
    if code == 200:
        rect = r.json()["rect"]
        assert rect["x0"] < rect["x1"] and rect["x1"] <= 595.5 and rect["y1"] <= 842.5


@pytest.mark.parametrize("kind", ["freetext", "rect"])
def test_appearance_survives_render_and_undo(client, make_user, upload, kind):
    _, h = make_user()
    sid = upload(h, _blank(), name="doc.pdf")
    _add(client, h, sid, type=kind, content="ทดสอบหลังแสดงผล", rect={"x0": 72, "y0": 72, "x1": 400, "y1": 140})
    assert client.get(f"/pdf/{sid}/page/0", headers=h).status_code == 200
    _add(client, h, sid, type="highlight", rect={"x0": 72, "y0": 300, "x1": 200, "y1": 320})
    assert client.post(f"/pdf/{sid}/undo", headers=h).status_code == 200
    assert client.get(f"/pdf/{sid}/page/0", headers=h).status_code == 200
    out = _download(client, h, sid)
    baked = fitz.open("pdf", out.tobytes())
    baked.bake(annots=True)
    assert "ทดสอบหลังแสดงผล" in baked[0].get_text().replace("\n", "")


def test_text_box_text_is_not_page_text(client, make_user, upload):
    """ข้อความในกล่องข้อความ/กรอบ (annotation) ไม่ปนกับข้อความเนื้อหน้า: ไม่โผล่เป็นย่อหน้าให้แก้ไข และค้นหาเพื่อ
    เซ็นเซอร์แล้วปิดในกล่อง (วาดภาพใหม่ยังมีอักษรไทย) โดยไม่ปิดทับเนื้อหน้าใต้กล่อง"""
    from pathlib import Path

    font = str(Path("app/assets/fonts/Sarabun-Regular.ttf").resolve())
    d = fitz.open()
    p = d.new_page()
    p.insert_font(fontname="sar", fontfile=font)
    p.insert_text((80, 120), "เนื้อหาใต้กรอบ", fontname="sar", fontsize=12)
    _, h = make_user()
    sid = upload(h, d.tobytes(), name="doc.pdf")
    _add(client, h, sid, type="rect", content="ความลับ ABC123", rect={"x0": 72, "y0": 100, "x1": 400, "y1": 160})
    blocks = client.get(f"/edit/{sid}/page/0/text-blocks", headers=h).json()
    assert not any("ABC123" in b["text"] for b in blocks)
    assert any("เนื้อหาใต้กรอบ" in b["text"] for b in blocks)
    r = client.post(f"/pdf/{sid}/redact-search", headers=h, json={"keyword": "ABC123"})
    assert r.status_code == 200, r.text
    out = _download(client, h, sid)
    baked = fitz.open("pdf", out.tobytes())
    baked.bake(annots=True)
    text = baked[0].get_text().replace("\n", "")
    assert "ABC123" not in text and "ความลับ" in text and "เนื้อหาใต้กรอบ" in text
