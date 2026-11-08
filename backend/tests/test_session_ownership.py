"""ทุก endpoint ที่รับ {session_id} ต้องตรวจว่าผู้เรียก login อยู่และเป็นเจ้าของ session"""
import pytest


def _session_routes(sid):
    return [
        ("get", f"/pdf/{sid}/info", None),
        ("get", f"/pdf/{sid}/page/0", None),
        ("get", f"/pdf/{sid}/download", None),
        ("get", f"/pdf/{sid}/export-pages?pages=0", None),
        ("get", f"/pdf/{sid}/bookmarks", None),
        ("get", f"/pdf/{sid}/properties", None),
        ("post", f"/pdf/{sid}/undo", None),
        ("post", f"/pdf/{sid}/pages/rotate", {"page_numbers": [0], "angle": 90}),
        ("post", f"/pdf/{sid}/redact", {"pageNumber": 0, "rect": {"x0": 0, "y0": 0, "x1": 10, "y1": 10}}),
        ("post", f"/pdf/{sid}/remove-password", None),
        ("get", f"/annotation/{sid}/page/0", None),
        ("get", f"/edit/{sid}/page/0/text-blocks", None),
        ("get", f"/edit/{sid}/page/0/images", None),
        ("delete", f"/pdf/{sid}", None),
    ]


def _call(client, method, url, body, headers):
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


def test_owner_can_use_session(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers)
    r = client.get(f"/pdf/{sid}/info", headers=headers)
    assert r.status_code == 200
    assert r.json()["page_count"] == 2
    assert client.get(f"/pdf/{sid}/download", headers=headers).status_code == 200


def test_anonymous_is_rejected(client, make_user, upload):
    _, headers = make_user()
    sid = upload(headers)
    for method, url, body in _session_routes(sid):
        r = _call(client, method, url, body, {})
        assert r.status_code == 401, f"{method.upper()} {url} -> {r.status_code}"


def test_other_user_gets_404(client, make_user, upload):
    _, owner = make_user()
    _, intruder = make_user()
    sid = upload(owner)
    for method, url, body in _session_routes(sid):
        r = _call(client, method, url, body, intruder)
        assert r.status_code == 404, f"{method.upper()} {url} -> {r.status_code}"
    # เจ้าของยังใช้งานได้ตามปกติ (intruder ปิด session ไม่ได้)
    assert client.get(f"/pdf/{sid}/info", headers=owner).status_code == 200


def test_legacy_session_is_claimed_by_file_owner(client, make_user, upload):
    from app.core.session import session_manager

    _, owner = make_user()
    _, other = make_user()
    sid = upload(owner)
    session_manager.get(sid).user_id = None  # จำลอง session ที่สร้างก่อนมีระบบตรวจเจ้าของ
    assert client.get(f"/pdf/{sid}/info", headers=other).status_code == 404
    assert client.get(f"/pdf/{sid}/info", headers=owner).status_code == 200
    assert session_manager.get(sid).user_id is not None


def test_merge_and_convert_sessions_belong_to_creator(client, make_user, pdf_bytes):
    uid, headers = make_user()
    _, other = make_user()
    r = client.post("/pdf/merge", headers=headers, files=[
        ("files", ("a.pdf", pdf_bytes, "application/pdf")),
        ("files", ("b.pdf", pdf_bytes, "application/pdf")),
    ])
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert client.get(f"/pdf/{sid}/info", headers=headers).json()["page_count"] == 4
    assert client.get(f"/pdf/{sid}/info", headers=other).status_code == 404
    assert client.post("/pdf/merge", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))] * 2).status_code == 401


def test_open_existing_file_requires_record_owner(client, make_user, upload):
    _, owner = make_user()
    _, other = make_user()
    sid = upload(owner)
    assert client.post(f"/pdf/{sid}/open", headers=other).status_code == 404
    r = client.post(f"/pdf/{sid}/open", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/autogen/preview", "/autogen/"])
def test_autogen_requires_login(client, path):
    assert client.post(path).status_code == 401
