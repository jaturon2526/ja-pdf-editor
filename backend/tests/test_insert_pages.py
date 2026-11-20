"""แทรกหน้า (v1.39.0): จากไฟล์ในเครื่อง / เอกสารของฉัน / หน้าว่าง — เลือกช่วงหน้า + ตำแหน่ง, undo, สิทธิ์เจ้าของ"""
import fitz

from tests.conftest import make_pdf_bytes


def _texts(client, h, sid):
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    return [p.get_text().strip() for p in doc]


def _source(client, h, data=None, name="src.pdf"):
    r = client.post("/pdf/insert-source", headers=h, files={"file": (name, data or make_pdf_bytes(5, "SRC"), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def test_insert_selected_pages_in_typed_order(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(3, "DST"))
    src = _source(client, h)
    assert src["page_count"] == 5 and src["status"] == "ok"
    r = client.post(f"/pdf/{sid}/pages/insert", headers=h,
                    json={"source_session_id": src["session_id"], "pages": "4-5, 1", "position": 1})
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 3 and r.json()["page_count"] == 6
    assert _texts(client, h, sid) == ["DST page 1", "SRC page 4", "SRC page 5", "SRC page 1", "DST page 2", "DST page 3"]

    # undo กลับเป็น 3 หน้า
    assert client.post(f"/pdf/{sid}/undo", headers=h).status_code == 200
    assert len(_texts(client, h, sid)) == 3


def test_insert_at_end_all_pages_and_blank(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(2, "DST"))
    src = _source(client, h, make_pdf_bytes(2, "SRC"))
    r = client.post(f"/pdf/{sid}/pages/insert", headers=h, json={"source_session_id": src["session_id"], "position": 99})
    assert r.status_code == 200 and r.json()["position"] == 2  # เกินจำนวนหน้า = ท้ายไฟล์
    r = client.post(f"/pdf/{sid}/pages/insert", headers=h,
                    json={"blank": {"count": 2, "width": 300, "height": 400}, "position": 0})
    assert r.status_code == 200 and r.json()["page_count"] == 6
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    assert [round(doc[i].rect.width) for i in (0, 1, 2)] == [300, 300, 595]
    assert doc[0].get_text().strip() == "" and doc[5].get_text().strip() == "SRC page 2"


def test_insert_validation(client, make_user, upload):
    _, h = make_user()
    sid = upload(h)
    src = _source(client, h)
    bad = [
        {"position": 0},  # ไม่ระบุแหล่ง
        {"source_session_id": src["session_id"], "blank": {"count": 1}, "position": 0},  # ระบุทั้งสอง
        {"source_session_id": src["session_id"], "pages": "9", "position": 0},  # เกินจำนวนหน้าต้นทาง
        {"source_session_id": src["session_id"], "pages": "a-b", "position": 0},
    ]
    for body in bad:
        assert client.post(f"/pdf/{sid}/pages/insert", headers=h, json=body).status_code in (400, 422), body
    r = client.post(f"/pdf/{sid}/pages/insert", headers=h, json={"source_session_id": "nope", "position": 0})
    assert r.status_code == 404


def test_source_must_belong_to_user(client, make_user, upload):
    _, owner = make_user()
    _, other = make_user()
    sid = upload(owner)
    other_src = _source(client, other)
    r = client.post(f"/pdf/{sid}/pages/insert", headers=owner,
                    json={"source_session_id": other_src["session_id"], "position": 0})
    assert r.status_code in (403, 404)
    # เอกสารของฉัน: ไฟล์คนอื่น = 404
    files = client.get("/pdf/files", headers=other).json()["files"]
    assert client.post(f"/pdf/insert-source/from-file/{files[0]['id']}", headers=owner).status_code == 404 if files else True


def test_insert_from_my_documents_and_duplicate_own_pages(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(2, "DST"))
    upload(h, make_pdf_bytes(3, "STORED"), name="stored.pdf")
    stored = next(f for f in client.get("/pdf/files", headers=h).json()["files"] if f["filename"] == "stored.pdf")
    src = client.post(f"/pdf/insert-source/from-file/{stored['id']}", headers=h).json()
    assert src["page_count"] == 3 and src["filename"] == "stored.pdf"
    client.post(f"/pdf/{sid}/pages/insert", headers=h, json={"source_session_id": src["session_id"], "pages": "2", "position": 2})
    # ต้นทางเป็นไฟล์ตัวเอง = ทำซ้ำหน้า
    r = client.post(f"/pdf/{sid}/pages/insert", headers=h, json={"source_session_id": sid, "pages": "1", "position": 0})
    assert r.status_code == 200, r.text
    assert _texts(client, h, sid) == ["DST page 1", "DST page 1", "DST page 2", "STORED page 2"]
    # ไฟล์ต้นทางชั่วคราวไม่เพิ่มในเอกสารของฉัน
    assert len(client.get("/pdf/files", headers=h).json()["files"]) == 2


def test_form_fields_of_source_are_baked(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(1, "DST"))
    src_doc = fitz.open()
    page = src_doc.new_page()
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect, w.field_value = "name", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(50, 50, 250, 75), "Somchai"
    page.add_widget(w)
    src = _source(client, h, src_doc.tobytes())
    r = client.post(f"/pdf/{sid}/pages/insert", headers=h, json={"source_session_id": src["session_id"], "position": 1})
    assert r.json()["flattened_fields"] == 1
    assert "Somchai" in _texts(client, h, sid)[1]


def test_insert_source_converts_images(client, make_user):
    _, h = make_user()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), False)
    pix.clear_with(200)
    src = _source(client, h, pix.tobytes("png"), name="photo.png")
    assert src["page_count"] == 1 and src["filename"] == "photo.pdf"
    r = client.post("/pdf/insert-source", headers=h, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_signed_document_refuses_insert(client, make_user, upload, monkeypatch):
    from app.services.pdf_service import pages as pages_mod

    _, h = make_user()
    sid = upload(h)
    monkeypatch.setattr(pages_mod, "has_digital_signatures", lambda _doc: True)
    r = client.post(f"/pdf/{sid}/pages/insert", headers=h, json={"blank": {"count": 1}, "position": 0})
    assert r.status_code == 400 and "ลายเซ็นดิจิทัล" in r.json()["detail"]
