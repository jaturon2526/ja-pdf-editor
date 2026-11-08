"""แผงหน้าเอกสาร (ลบหน้า) และบุ๊กมาร์ก — โครงสร้างหลายชั้น/จุดหมายเดิม/ลิงก์เว็บไม่หาย, ลบหน้าไม่ทำไฟล์พัง"""
import fitz


def _doc(n=5, toc=True):
    d = fitz.open()
    for i in range(n):
        d.new_page().insert_text((72, 72), f"P{i + 1}")
    if toc:
        d.set_toc([
            [1, "บทที่ 1", 1],
            [2, "1.1 กลางหน้า", 2, {"kind": fitz.LINK_GOTO, "to": fitz.Point(0, 300), "zoom": 0}],
            [1, "เว็บไซต์", -1, {"kind": fitz.LINK_URI, "uri": "https://example.com"}],
            [1, "บทที่ 2", 4],
        ])
    return d.tobytes()


def _toc(client, h, sid):
    data = client.get(f"/pdf/{sid}/download", headers=h).content
    return fitz.open("pdf", data).get_toc(simple=False)


def test_get_bookmarks_has_level_and_ref(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(), name="doc.pdf")
    bms = client.get(f"/pdf/{sid}/bookmarks", headers=h).json()["bookmarks"]
    assert [(b["label"], b["page"], b["level"], b["ref"]) for b in bms] == [
        ("บทที่ 1", 0, 1, 0), ("1.1 กลางหน้า", 1, 2, 1), ("บทที่ 2", 3, 1, 3)]


def test_rename_keeps_structure_destination_and_web_links(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(), name="doc.pdf")
    bms = client.get(f"/pdf/{sid}/bookmarks", headers=h).json()["bookmarks"]
    bms[2]["label"] = "บทที่ 2 (แก้ชื่อ)"
    r = client.put(f"/pdf/{sid}/bookmarks", headers=h, json={"bookmarks": bms})
    assert r.status_code == 200, r.text
    toc = _toc(client, h, sid)
    assert [(e[0], e[1], e[2]) for e in toc] == [
        (1, "บทที่ 1", 1), (2, "1.1 กลางหน้า", 2), (1, "เว็บไซต์", -1), (1, "บทที่ 2 (แก้ชื่อ)", 4)]
    assert toc[1][3]["to"].y == 300  # เดิม: กลายเป็นหัวหน้ากระดาษ
    assert toc[2][3]["uri"] == "https://example.com"  # เดิม: หายไปเลย


def test_remove_parent_promotes_child_and_add_new(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(), name="doc.pdf")
    bms = client.get(f"/pdf/{sid}/bookmarks", headers=h).json()["bookmarks"]
    new = [bms[1], bms[2], {"page": 4, "label": "ใหม่"}]
    r = client.put(f"/pdf/{sid}/bookmarks", headers=h, json={"bookmarks": new})
    assert r.status_code == 200, r.text  # เดิม (ถ้าส่ง level): ลูกขึ้นต้น → set_toc error
    toc = _toc(client, h, sid)
    assert [(e[0], e[1], e[2]) for e in toc] == [
        (1, "1.1 กลางหน้า", 2), (1, "เว็บไซต์", -1), (1, "บทที่ 2", 4), (1, "ใหม่", 5)]


def test_bookmark_validation(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(), name="doc.pdf")
    for bad in [{"page": 9, "label": "x"}, {"page": 0, "label": "  "}, {"page": 0, "label": "ก" * 301}]:
        r = client.put(f"/pdf/{sid}/bookmarks", headers=h, json={"bookmarks": [bad]})
        assert r.status_code in (400, 422), bad


def test_delete_pages_removes_dead_bookmarks(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(), name="doc.pdf")
    r = client.request("DELETE", f"/pdf/{sid}/pages", headers=h, json={"page_numbers": [1]})
    assert r.status_code == 200, r.text
    toc = _toc(client, h, sid)
    # "1.1" ชี้หน้า 2 ที่ถูกลบ → ลบทิ้ง (เดิมค้างในไฟล์ กดแล้วไม่ไปไหน) · บทที่ 2 เลื่อนจากหน้า 4 เป็น 3
    assert [(e[1], e[2]) for e in toc] == [("บทที่ 1", 1), ("เว็บไซต์", -1), ("บทที่ 2", 3)]


def test_cannot_delete_every_page(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(3, toc=False), name="doc.pdf")
    r = client.request("DELETE", f"/pdf/{sid}/pages", headers=h, json={"page_numbers": [0, 1, 2]})
    assert r.status_code == 400
    assert "อย่างน้อย 1 หน้า" in r.json()["detail"]
    assert client.get(f"/pdf/{sid}/info", headers=h).json()["page_count"] == 3
    assert client.get(f"/pdf/{sid}/download", headers=h).status_code == 200
