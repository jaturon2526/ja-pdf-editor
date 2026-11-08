"""API เปรียบเทียบเอกสาร: ไฟล์ในบัญชี / เอกสารที่เปิดอยู่ / อัปโหลด / เวอร์ชันก่อนหน้า · ภาพหน้า · รายงาน · สิทธิ์"""
import fitz

from tests.test_compare_engine import _doc


def _pdf(lines) -> bytes:
    return _doc([lines]).tobytes()


def _upload(client, headers, data, name="a.pdf"):
    r = client.post("/pdf/upload", headers=headers, files={"file": (name, data, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def _file_id(client, headers, sid):
    files = client.get("/pdf/files", headers=headers).json()["files"]
    return next(f["id"] for f in files if f["session_id"] == sid)


def _run(client, headers, data=None, files=None):
    r = client.post("/compare", headers=headers, data=data or {}, files=files or {})
    assert r.status_code == 200, r.text
    task_id = r.json()["task_id"]
    body = client.get(f"/compare/{task_id}", headers=headers).json()  # TestClient รัน background task เสร็จก่อนตอบ
    assert body["status"] == "completed", body
    return task_id, body


def test_compare_uploads_and_report(client, make_user):
    _, h = make_user()
    task_id, body = _run(client, h, files={"a_upload": ("v1.pdf", _pdf(["ค่าเช่า 5,000 บาท"]), "application/pdf"),
                                           "b_upload": ("v2.pdf", _pdf(["ค่าเช่า 6,500 บาท"]), "application/pdf")})
    assert body["name_a"] == "v1.pdf" and body["name_b"] == "v2.pdf"
    changes = body["result"]["changes"]
    assert [(c["kind"], c["a_text"], c["b_text"]) for c in changes] == [("replace", "5,000", "6,500")]

    img = client.get(f"/compare/{task_id}/page/b/0?zoom=1", headers=h)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg" and img.content[:2] == b"\xff\xd8"
    assert client.get(f"/compare/{task_id}/page/b/5", headers=h).status_code == 404

    rep = client.get(f"/compare/{task_id}/report", headers=h)
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF"
    assert "filename*=UTF-8''" in rep.headers["content-disposition"]
    assert fitz.open("pdf", rep.content).page_count == 2  # สรุป + คู่หน้าที่มีจุดต่าง


def test_compare_account_file_with_open_session_including_unsaved_edits(client, make_user):
    _, h = make_user()
    sid = _upload(client, h, _pdf(["Original text"]))["session_id"]
    fid = _file_id(client, h, sid)
    r = client.post(f"/annotation/{sid}", headers=h, json={"page_number": 0, "type": "freetext", "content": "Added note",
                                                          "rect": {"x0": 72, "y0": 300, "x1": 300, "y1": 330}, "fontsize": 14})
    assert r.status_code == 200
    _, body = _run(client, h, data={"a_file_id": fid, "b_session_id": sid})
    assert body["name_b"].endswith("(กำลังแก้ไข)")
    assert body["result"]["changes"], "การแก้ที่ยังไม่บันทึกต้องเห็นเป็นจุดต่าง"
    # จาก Editor: "เทียบกับไฟล์ที่บันทึกไว้" ระบุด้วย session เดียวกัน
    _, saved = _run(client, h, data={"a_session_id": sid, "a_version": "saved", "b_session_id": sid})
    assert saved["name_a"] == body["name_a"] and saved["result"]["changes"]


def test_previous_version_after_save(client, make_user):
    _, h = make_user()
    sid = _upload(client, h, _pdf(["Version one"]))["session_id"]
    fid = _file_id(client, h, sid)
    r = client.post("/compare", headers=h, data={"a_file_id": fid, "a_version": "previous", "b_file_id": fid})
    assert r.status_code == 404 and "เวอร์ชันก่อนหน้า" in r.json()["detail"]

    client.post(f"/annotation/{sid}", headers=h, json={"page_number": 0, "type": "freetext", "content": "Version two",
                                                       "rect": {"x0": 72, "y0": 300, "x1": 300, "y1": 330}, "fontsize": 14})
    assert client.post(f"/pdf/{sid}/save", headers=h).status_code == 200
    listed = next(f for f in client.get("/pdf/files", headers=h).json()["files"] if f["id"] == fid)
    assert listed["has_previous_version"] is True
    _, body = _run(client, h, data={"a_file_id": fid, "a_version": "previous", "b_file_id": fid})
    assert body["name_a"].endswith("(เวอร์ชันก่อนหน้า)")
    assert any("two" in c["b_text"] for c in body["result"]["changes"])

    # เปิดไฟล์ซ้ำ (storage_path เปลี่ยน) เวอร์ชันก่อนหน้ายังอยู่
    client.delete(f"/pdf/{sid}", headers=h)
    reopened = client.post(f"/pdf/{sid}/open", headers=h).json()["session_id"]
    assert reopened != sid
    _, again = _run(client, h, data={"a_file_id": fid, "a_version": "previous", "b_file_id": fid})
    assert again["result"]["changes"]


def test_validation_and_ownership(client, make_user):
    _, h = make_user()
    _, other = make_user()
    sid = _upload(client, h, _pdf(["mine"]))["session_id"]
    fid = _file_id(client, h, sid)
    assert client.post("/compare", headers=h, data={"a_file_id": fid}).status_code == 400  # ไม่มีฝั่ง B
    both = client.post("/compare", headers=h, data={"a_file_id": fid, "a_session_id": sid, "b_file_id": fid})
    assert both.status_code == 400
    assert client.post("/compare", headers=other, data={"a_file_id": fid, "b_file_id": fid}).status_code == 404
    bad = client.post("/compare", headers=h, data={"a_file_id": fid},
                      files={"b_upload": ("x.pdf", b"not a pdf", "application/pdf")})
    assert bad.status_code == 400 and "PDF" in bad.json()["detail"]
    locked = fitz.open("pdf", _pdf(["secret"]))
    enc = locked.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    r = client.post("/compare", headers=h, data={"a_file_id": fid}, files={"b_upload": ("s.pdf", enc, "application/pdf")})
    assert r.status_code == 400 and "รหัสผ่าน" in r.json()["detail"]

    task_id, _ = _run(client, h, data={"a_file_id": fid, "b_file_id": fid})
    assert client.get(f"/compare/{task_id}", headers=other).status_code == 404
    assert client.get(f"/compare/{task_id}/report", headers=other).status_code == 404
    assert client.delete(f"/compare/{task_id}", headers=h).status_code == 200
    assert client.get(f"/compare/{task_id}", headers=h).status_code == 404


def test_identical_files_and_cleanup(client, make_user, monkeypatch):
    import os
    import time

    from app.api import routes_compare

    _, h = make_user()
    sid = _upload(client, h, _pdf(["same"]))["session_id"]
    fid = _file_id(client, h, sid)
    task_id, body = _run(client, h, data={"a_file_id": fid, "b_file_id": fid})
    assert body["result"]["identical"] is True
    folder = routes_compare.task_dir(task_id)
    old = time.time() - 25 * 3600
    os.utime(folder, (old, old))
    assert routes_compare.cleanup_old_tasks() >= 1 and not folder.exists()
    assert client.get(f"/compare/{task_id}", headers=h).status_code == 404
