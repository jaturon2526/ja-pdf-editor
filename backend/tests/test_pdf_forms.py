"""Tests for Fillable PDF Forms (AcroForm, v1.45.0): GET /pdf/{sid}/forms & POST /pdf/{sid}/forms/fill."""
import fitz


def _make_form_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 60), "Synthetic AcroForm Test", fontsize=14)

    w_text = fitz.Widget()
    w_text.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w_text.field_name = "fullname"
    w_text.field_label = "ชื่อ-นามสกุล"
    w_text.rect = fitz.Rect(60, 90, 320, 118)
    w_text.field_value = ""
    page.add_widget(w_text)

    w_cb = fitz.Widget()
    w_cb.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w_cb.field_name = "agree"
    w_cb.field_label = "ยอมรับเงื่อนไข"
    w_cb.rect = fitz.Rect(60, 140, 80, 160)
    w_cb.field_value = False
    page.add_widget(w_cb)

    w_dd = fitz.Widget()
    w_dd.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    w_dd.field_name = "department"
    w_dd.field_label = "แผนก"
    w_dd.choice_values = ["บัญชี", "บุคคล", "ไอที"]
    w_dd.rect = fitz.Rect(60, 180, 260, 208)
    w_dd.field_value = "บัญชี"
    page.add_widget(w_dd)

    w_ro = fitz.Widget()
    w_ro.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w_ro.field_name = "readonly_code"
    w_ro.field_label = "รหัสเอกสาร"
    w_ro.field_flags = fitz.PDF_FIELD_IS_READ_ONLY
    w_ro.rect = fitz.Rect(60, 230, 220, 258)
    w_ro.field_value = "DOC-001"
    page.add_widget(w_ro)

    data = doc.tobytes()
    doc.close()
    return data


def test_list_fill_and_undo_form_fields(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_form_pdf_bytes())

    r = client.get(f"/pdf/{sid}/forms", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4
    by_name = {f["name"]: f for f in body["fields"]}
    assert by_name["fullname"]["type"] == "text"
    assert by_name["agree"]["type"] == "checkbox"
    assert by_name["agree"]["value"] is False
    assert by_name["department"]["type"] == "dropdown"
    assert len(by_name["department"]["options"]) == 3
    assert by_name["readonly_code"]["read_only"] is True

    # Fill Thai text + check checkbox + change dropdown + attempt readonly change (should skip)
    r_fill = client.post(
        f"/pdf/{sid}/forms/fill",
        json={
            "updates": [
                {"xref": by_name["fullname"]["xref"], "page": 0, "value": "สมชาย ใจดี"},
                {"xref": by_name["agree"]["xref"], "page": 0, "value": True},
                {"xref": by_name["department"]["xref"], "page": 0, "value": "ไอที"},
                {"xref": by_name["readonly_code"]["xref"], "page": 0, "value": "HACKED"},
            ]
        },
        headers=h,
    )
    assert r_fill.status_code == 200, r_fill.text
    assert r_fill.json() == {"status": "ok", "updated": 3}

    # Verify persisted values
    r2 = client.get(f"/pdf/{sid}/forms", headers=h).json()
    by_name2 = {f["name"]: f for f in r2["fields"]}
    assert by_name2["fullname"]["value"] == "สมชาย ใจดี"
    assert by_name2["agree"]["value"] is True
    assert by_name2["department"]["value"] == "ไอที"
    assert by_name2["readonly_code"]["value"] == "DOC-001"

    # Undo restores original blank values
    client.post(f"/pdf/{sid}/undo", headers=h)
    r3 = client.get(f"/pdf/{sid}/forms", headers=h).json()
    by_name3 = {f["name"]: f for f in r3["fields"]}
    assert by_name3["fullname"]["value"] == ""
    assert by_name3["agree"]["value"] is False
    assert by_name3["department"]["value"] == "บัญชี"


def test_form_noop_and_validation(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_form_pdf_bytes())

    r_noop = client.post(f"/pdf/{sid}/forms/fill", json={"updates": []}, headers=h)
    assert r_noop.status_code == 200
    assert r_noop.json() == {"status": "no_change", "updated": 0}

    r_oor = client.post(
        f"/pdf/{sid}/forms/fill",
        json={"updates": [{"xref": 999, "page": 5, "value": "x"}]},
        headers=h,
    )
    assert r_oor.status_code == 400
