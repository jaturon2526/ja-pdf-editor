"""แก้โครงตาราง (v1.40.0): ตรวจหาตาราง · ย้าย · ปรับคอลัมน์/แถว · ตัดบรรทัดเซลล์ที่แคบลง · ทับข้อความ = ถามก่อน · undo"""
from pathlib import Path

import fitz
import pytest

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")
XS = [50, 100, 250, 350]
YS = [100, 130, 155, 180]
ROWS = [["ลำดับ", "ผู้ขอเบิก", "จำนวนเงิน"], ["1", "สมชาย ใจดี", "1,250.00"], ["2", "สมหญิง รักไทย", "980.50"]]


def table_pdf(below_y: float = 230) -> bytes:
    """ตาราง 3×3 มีเส้นครบ หัวตารางพื้นเทา · บาร์โค้ดจำลองมีแท่งกว้าง 0 · ข้อความใต้ตาราง (ข้อมูลสมมติ)"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="th", fontfile=FONT)
    page.draw_rect(fitz.Rect(XS[0], YS[0], XS[-1], YS[1]), color=None, fill=(0.85, 0.85, 0.85))
    for x in XS:
        page.draw_line((x, YS[0]), (x, YS[-1]), color=(0, 0, 0), width=0.75)
    for y in YS:
        page.draw_line((XS[0], y), (XS[-1], y), color=(0, 0, 0), width=0.75)
    for r, row in enumerate(ROWS):
        for c, text in enumerate(row):
            page.insert_text((XS[c] + 4, YS[r] + 18), text, fontname="th", fontsize=11)
    shape = page.new_shape()  # "บาร์โค้ด" มีแท่งกว้าง 0 (redaction ลบไม่ได้)
    for i, w in enumerate([2, 0, 1, 0, 2]):
        shape.draw_rect(fitz.Rect(50 + i * 4, 50, 50 + i * 4 + w, 70))
    shape.finish(fill=(0, 0, 0), color=None)
    shape.commit()
    page.insert_text((50, below_y), "ยอดรวมทั้งสิ้น 2,230.50 บาท", fontname="th", fontsize=12)
    return doc.tobytes()


def _tables(client, h, sid, page=0):
    r = client.get(f"/edit/{sid}/page/{page}/tables", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["tables"]


def _edit(client, h, sid, table, xs, ys, **extra):
    return client.post(f"/edit/{sid}/page/0/table", headers=h,
                       json={"bbox": table["bbox"], "xs": xs, "ys": ys, **extra})


def _doc(client, h, sid):
    return fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)


def _near(values, expected, tol=1.0):
    return len(values) == len(expected) and all(abs(a - b) <= tol for a, b in zip(values, expected))


def _word_x(page, word):
    return [round(w[0], 1) for w in page.get_text("words") if w[4] == word]


@pytest.fixture
def table_session(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, table_pdf())
    return h, sid


def test_detect_table(client, table_session):
    h, sid = table_session
    [t] = _tables(client, h, sid)
    assert _near(t["xs"], XS) and _near(t["ys"], YS)
    assert len(t["cells"]) == 9 and t["cells"][0] == {"r": 0, "c": 0, "rowspan": 1, "colspan": 1}


def test_move_table_keeps_text_once_and_outside_untouched(client, table_session):
    h, sid = table_session
    [t] = _tables(client, h, sid)
    before = _doc(client, h, sid)[0]
    r = _edit(client, h, sid, t, [x + 40 for x in t["xs"]], [y + 5 for y in t["ys"]])
    assert r.status_code == 200, r.text
    assert r.json()["adjusted_rows"] == [] and r.json()["id"].startswith("table-")
    page = _doc(client, h, sid)[0]
    text = page.get_text()
    for word in ("สมชาย", "1,250.00", "จำนวนเงิน", "ยอดรวมทั้งสิ้น"):
        assert text.count(word) == 1, word  # ไม่ซ้ำ (เนื้อหาเซลล์แยกต้นทางทีละเซลล์)
    assert _word_x(page, "1,250.00")[0] == pytest.approx(_word_x(before, "1,250.00")[0] + 40, abs=0.6)
    assert _word_x(page, "ยอดรวมทั้งสิ้น") == _word_x(before, "ยอดรวมทั้งสิ้น")  # ข้อความนอกตารางไม่ขยับ
    xs_lines = sorted({round(d["rect"].x0) for d in page.get_drawings() if d["rect"].width == 0 and d["rect"].height > 50})
    assert _near(xs_lines, [x + 40 for x in XS])
    # หัวตารางพื้นเทาวาดใหม่ที่ตำแหน่งใหม่
    fills = [d for d in page.get_drawings() if d.get("fill") and d["fill"][0] < 0.9 and d["rect"].width > 100]
    assert fills and abs(fills[0]["rect"].x0 - (XS[0] + 40)) <= 1
    # ตรวจหาซ้ำได้ตารางเดิม (จากทะเบียน) และ undo กลับที่เดิม
    [again] = _tables(client, h, sid)
    assert again["id"] == r.json()["id"] and _near(again["xs"], [x + 40 for x in XS])
    assert client.post(f"/pdf/{sid}/undo", headers=h).status_code == 200
    assert _near(_tables(client, h, sid)[0]["xs"], XS)


def test_widen_column_and_text_still_editable(client, table_session):
    h, sid = table_session
    [t] = _tables(client, h, sid)
    xs = list(t["xs"])
    xs[2] += 60  # คอลัมน์ "ผู้ขอเบิก" กว้างขึ้น คอลัมน์ขวาเลื่อนตาม
    xs[3] += 60
    assert _edit(client, h, sid, t, xs, t["ys"]).status_code == 200
    page = _doc(client, h, sid)[0]
    assert _word_x(page, "980.50")[0] > XS[2] + 60
    blocks = client.get(f"/edit/{sid}/page/0/text-blocks", headers=h).json()
    target = next(b for b in blocks if "สมชาย" in b["text"])
    r = client.post(f"/edit/{sid}/text", headers=h, json={
        "page_number": 0, "rect": target["rect"], "new_text": "สมศักดิ์", "fontsize": 11,
        "fontname": "sarabun", "color": [0, 0, 0], "block_id": target["block_id"]})
    assert r.status_code == 200, r.text
    text = _doc(client, h, sid)[0].get_text()
    assert "สมศักดิ์" in text and "สมชาย" not in text


def test_narrow_column_wraps_text_and_grows_row(client, table_session):
    h, sid = table_session
    [t] = _tables(client, h, sid)
    xs = list(t["xs"])
    xs[2] -= 100  # "ผู้ขอเบิก" เหลือ 50 pt — "สมหญิง รักไทย" ไม่พอ
    xs[3] -= 100
    r = _edit(client, h, sid, t, xs, t["ys"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert {(c["r"], c["c"]) for c in body["wrapped_cells"]} >= {(2, 1)}
    assert 2 in body["adjusted_rows"] and body["ys"][-1] > YS[-1]
    text = _doc(client, h, sid)[0].get_text()
    assert "รักไทย" in text and text.count("สมหญิง") == 1
    # ข้อความที่ตัดบรรทัดเลือกแก้ไขต่อได้
    blocks = client.get(f"/edit/{sid}/page/0/text-blocks", headers=h).json()
    assert any("สมหญิง" in b["text"] for b in blocks)


def test_overlap_requires_confirmation(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, table_pdf(below_y=200))
    [t] = _tables(client, h, sid)
    down = [y + 40 for y in t["ys"]]
    r = _edit(client, h, sid, t, t["xs"], down)
    assert r.status_code == 409 and "ทับข้อความ" in r.json()["detail"]
    assert _doc(client, h, sid)[0].get_text().count("สมชาย") == 1  # ไม่ได้แก้อะไร
    assert _edit(client, h, sid, t, t["xs"], down, allow_overlap=True).status_code == 200


def test_validation_and_owner(client, make_user, upload, table_session):
    h, sid = table_session
    [t] = _tables(client, h, sid)
    assert _edit(client, h, sid, t, t["xs"][:-1], t["ys"]).status_code == 400  # จำนวนเส้นไม่ตรง
    xs = list(t["xs"])
    xs[1] = xs[0] + 2
    assert _edit(client, h, sid, t, xs, t["ys"]).status_code == 400  # คอลัมน์แคบเกิน
    assert _edit(client, h, sid, t, [x + 400 for x in t["xs"]], t["ys"]).status_code == 400  # เกินขอบกระดาษ
    other_bbox = {**t, "bbox": {"x0": 1, "y0": 1, "x1": 20, "y1": 20}}
    assert _edit(client, h, sid, other_bbox, t["xs"], t["ys"]).status_code == 400
    _, other = make_user()
    assert client.get(f"/edit/{sid}/page/0/tables", headers=other).status_code in (403, 404)


def test_no_zero_width_shapes_leak_into_cells(client, table_session):
    h, sid = table_session
    [t] = _tables(client, h, sid)
    assert _edit(client, h, sid, t, t["xs"], [y + 3 for y in t["ys"]]).status_code == 200
    [t2] = _tables(client, h, sid)
    assert _edit(client, h, sid, t2, [x + 5 for x in t2["xs"]], t2["ys"]).status_code == 200
    page = _doc(client, h, sid)[0]
    inside = fitz.Rect(XS[0], YS[0], XS[-1] + 10, YS[-1] + 10)
    # แท่งกว้าง 0 ของ "บาร์โค้ด" (y 50-70) ต้องไม่ไปโผล่ในเซลล์ที่ย้ายมา
    stray = [d for d in page.get_drawings() if d["rect"].width == 0 and d["rect"].height == 20]
    assert all(not inside.contains(fitz.Point(d["rect"].x0, d["rect"].y1)) for d in stray)


def test_rotated_page_refused(client, table_session):
    h, sid = table_session
    [t] = _tables(client, h, sid)
    assert client.post(f"/pdf/{sid}/pages/rotate", headers=h, json={"page_numbers": [0], "angle": 90}).status_code == 200
    tables = _tables(client, h, sid)
    if tables:  # หน้าที่หมุนแล้ว normalize เนื้อหาเป็นแนวตั้ง — ตารางยังตรวจเจอได้และแก้ได้ตามพิกัดใหม่
        r = _edit(client, h, sid, tables[0], tables[0]["xs"], tables[0]["ys"])
        assert r.status_code in (200, 400)
