def _rotation(client, sid, headers):
    """ทิศของหน้าแรกตามที่เห็น (หน้าแนวตั้ง A4): 0 = ตั้ง, 90 = นอน — หมุนแล้ว /Rotate เป็น 0 เสมอ
    (หมุนเข้าเนื้อหน้า ดู pdf_service.core.normalize_page_rotation) จึงดูจากขนาดหน้าแทน"""
    from app.core.session import session_manager

    s = session_manager.get(sid)
    with s.lock:
        page = s.doc[0]
        assert page.rotation == 0
        return 90 if page.rect.width > page.rect.height else 0


def test_rotate_undo_redo(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers)
    r = client.post(f"/pdf/{sid}/pages/rotate", headers=headers, json={"page_numbers": [0], "angle": 90})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert _rotation(client, sid, headers) == 90

    r = client.post(f"/pdf/{sid}/undo", headers=headers)
    assert r.json()["status"] == "ok" and r.json()["can_redo"] is True
    assert _rotation(client, sid, headers) == 0

    r = client.post(f"/pdf/{sid}/redo", headers=headers)
    assert r.json()["status"] == "ok"
    assert _rotation(client, sid, headers) == 90


def test_redact_search_pushes_history(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers)
    r = client.post(f"/pdf/{sid}/redact-search", headers=headers, json={"keyword": "Hello"})
    assert r.status_code == 200, r.text
    assert r.json()["redacted_count"] == 2
    assert client.post(f"/pdf/{sid}/undo", headers=headers).json()["status"] == "ok"


def test_redact_missing_fields_is_400(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers)
    assert client.post(f"/pdf/{sid}/redact-all-pages", headers=headers, json={}).status_code == 400
    assert client.post(f"/pdf/{sid}/redact", headers=headers, json={}).status_code == 400


def test_print_as_shown_keeps_screen_orientation(client, make_user, upload):
    """หน้าที่หมุนซ้ายต้องถูกวางบนกระดาษแนวตั้งตามที่เห็นบนจอ (หัวกระดาษอยู่ซ้าย) ไม่ใช่ให้เครื่องพิมพ์หมุนเอง"""
    import fitz

    _, headers = make_user()
    sid = upload(headers)
    client.post(f"/pdf/{sid}/pages/rotate", headers=headers, json={"page_numbers": [0], "angle": -90})
    ann = client.post(f"/annotation/{sid}", headers=headers, json={
        "page_number": 1, "type": "highlight", "rect": {"x0": 50, "y0": 60, "x1": 200, "y1": 80}, "color": [1, 1, 0]})
    assert ann.status_code == 200, ann.text
    r = client.get(f"/pdf/{sid}/print", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    with fitz.open("pdf", r.content) as doc:
        assert doc.page_count == 2
        for page in doc:
            assert page.rotation == 0 and page.rect.height > page.rect.width  # แนวตั้งทุกหน้า ไม่ต้องหมุนอีก
            assert not list(page.annots())  # annotation ถูกรวมเข้าเนื้อหาหน้าแล้ว
        # ข้อความหน้าแรกต้องวิ่งแนวตั้ง (หมุนตามที่เห็นบนจอ) และอยู่ครึ่งบนของกระดาษ (ย่อ+จัดกึ่งกลาง)
        lines = [l for b in doc[0].get_text("dict")["blocks"] for l in b.get("lines", [])]
        assert lines and all(abs(l["dir"][0]) < 0.01 for l in lines)
    assert client.get(f"/pdf/{sid}/print?layout=nope", headers=headers).status_code == 400
