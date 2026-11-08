"""กล่องข้อความที่คลิกวาง (auto_height) — ความสูงกรอบพอดีกับข้อความ และขยายเองเมื่อแก้ข้อความจนล้น"""
import pytest


@pytest.fixture
def ctx(client, make_user, upload):
    _, headers = make_user()
    return client, headers, upload(headers)


def _add(client, headers, sid, **kw):
    body = dict(page_number=0, type="freetext", rect=dict(x0=72, y0=100, x1=232, y1=140), fontsize=12, **kw)
    r = client.post(f"/annotation/{sid}", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _h(a):
    return a["rect"]["y1"] - a["rect"]["y0"]


def test_click_placed_box_fits_one_line(ctx):
    client, headers, sid = ctx
    a = _add(client, headers, sid, content="ทดสอบ", auto_height=True)
    assert 18 <= _h(a) <= 24          # 12pt หนึ่งบรรทัด (เดิมสูง 40)
    assert a["rect"]["x1"] - a["rect"]["x0"] == pytest.approx(160)


def test_click_placed_box_grows_with_lines(ctx):
    client, headers, sid = ctx
    one = _add(client, headers, sid, content="บรรทัดเดียว", auto_height=True)
    three = _add(client, headers, sid, content="หนึ่ง\nสอง\nสาม", auto_height=True)
    assert _h(three) == pytest.approx(_h(one) + 2 * 12 * 1.35, abs=0.5)


def test_dragged_box_keeps_its_size(ctx):
    client, headers, sid = ctx
    a = _add(client, headers, sid, content="ทดสอบ")
    assert _h(a) == pytest.approx(40)


def test_edit_grows_box_when_text_overflows_but_not_on_resize(ctx):
    client, headers, sid = ctx
    a = _add(client, headers, sid, content="ทดสอบ", auto_height=True)
    upd = dict(page_number=0, xref=a["xref"])
    r = client.patch(f"/annotation/{sid}", headers=headers, json={**upd, "content": "หนึ่ง\nสอง\nสาม\nสี่"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert _h(b) > _h(a) + 3 * 12 * 1.35 - 1
    # ผู้ใช้ลากย่อกรอบเอง → ไม่ขยายกลับ
    small = dict(x0=72, y0=100, x1=232, y1=115)
    c = client.patch(f"/annotation/{sid}", headers=headers, json={"page_number": 0, "xref": b["xref"], "rect": small}).json()
    assert _h(c) == pytest.approx(15)
