"""Tests for Blank PDF Creation & PDF Form Builder (v1.47.0)."""


def test_create_blank_pdf_and_build_form_fields_with_undo(client, make_user):
    _, h = make_user()

    # 1) Create a 2-page blank A4 PDF
    r_blank = client.post(
        "/pdf/blank",
        json={"filename": "ใบสมัครใหม่", "width": 595, "height": 842, "page_count": 2},
        headers=h,
    )
    assert r_blank.status_code == 200, r_blank.text
    body = r_blank.json()
    sid = body["session_id"]
    assert body["filename"].endswith(".pdf")
    assert body["page_count"] == 2

    # 2) Add Text, Checkbox, and Dropdown fields on page 0
    r_text = client.post(
        f"/pdf/{sid}/forms/fields",
        json={
            "page": 0,
            "type": "text",
            "label": "ชื่อ-นามสกุล",
            "rect": {"x0": 72, "y0": 100, "x1": 320, "y1": 128},
        },
        headers=h,
    )
    assert r_text.status_code == 200, r_text.text
    f_text = r_text.json()["field"]
    assert f_text["type"] == "text"
    assert f_text["label"] == "ชื่อ-นามสกุล"

    r_cb = client.post(
        f"/pdf/{sid}/forms/fields",
        json={
            "page": 0,
            "type": "checkbox",
            "label": "ยืนยันข้อมูล",
            "rect": {"x0": 72, "y0": 150, "x1": 94, "y1": 172},
        },
        headers=h,
    )
    assert r_cb.status_code == 200, r_cb.text
    f_cb = r_cb.json()["field"]

    r_dd = client.post(
        f"/pdf/{sid}/forms/fields",
        json={
            "page": 0,
            "type": "dropdown",
            "label": "สาขา",
            "rect": {"x0": 72, "y0": 195, "x1": 260, "y1": 223},
            "options": ["กรุงเทพฯ", "เชียงใหม่", "ภูเก็ต"],
        },
        headers=h,
    )
    assert r_dd.status_code == 200, r_dd.text

    # 3) List fields → 3 fields
    listed = client.get(f"/pdf/{sid}/forms", headers=h).json()
    assert listed["total"] == 3

    # 4) Fill newly created text field with Thai text
    r_fill = client.post(
        f"/pdf/{sid}/forms/fill",
        json={"updates": [{"xref": f_text["xref"], "page": 0, "value": "สมหญิง ทดสอบ"}]},
        headers=h,
    )
    assert r_fill.status_code == 200, r_fill.text
    assert r_fill.json() == {"status": "ok", "updated": 1}

    # 5) Delete checkbox field → 2 fields left
    r_del = client.delete(f"/pdf/{sid}/forms/fields/{f_cb['xref']}?page=0", headers=h)
    assert r_del.status_code == 200, r_del.text
    assert client.get(f"/pdf/{sid}/forms", headers=h).json()["total"] == 2

    # 6) Undo restores deleted checkbox → back to 3 fields
    client.post(f"/pdf/{sid}/undo", headers=h)
    assert client.get(f"/pdf/{sid}/forms", headers=h).json()["total"] == 3


def test_form_builder_validation(client, make_user):
    _, h = make_user()
    sid = client.post("/pdf/blank", json={"filename": "v.pdf"}, headers=h).json()["session_id"]

    # Dropdown without options → 400
    r_no_opt = client.post(
        f"/pdf/{sid}/forms/fields",
        json={"page": 0, "type": "dropdown", "label": "empty", "rect": {"x0": 50, "y0": 50, "x1": 200, "y1": 80}, "options": []},
        headers=h,
    )
    assert r_no_opt.status_code == 400

    # Too-small rect → 400
    r_small = client.post(
        f"/pdf/{sid}/forms/fields",
        json={"page": 0, "type": "text", "label": "tiny", "rect": {"x0": 50, "y0": 50, "x1": 54, "y1": 54}},
        headers=h,
    )
    assert r_small.status_code == 400
