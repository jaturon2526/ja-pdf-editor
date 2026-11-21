"""ค้นหาข้อความในเอกสาร (Ctrl+F, v1.42.0 — GET /pdf/{sid}/search)"""
import fitz


def _make_multipage_pdf() -> bytes:
    doc = fitz.open()
    p0 = doc.new_page()
    p0.insert_text((60, 100), "Hello World hello invoice 001", fontsize=12)
    p0.insert_text((60, 140), "Second line with Hello again", fontsize=12)
    p1 = doc.new_page()
    p1.insert_text((60, 100), "Page two has HELLO and summary", fontsize=12)
    return doc.tobytes()


def test_search_case_insensitive_and_match_case(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_multipage_pdf())

    r = client.get(f"/pdf/{sid}/search", params={"q": "hello"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4
    assert body["truncated"] is False
    assert [m["page"] for m in body["matches"]] == [0, 0, 0, 1]
    assert all(len(m["rects"]) >= 1 for m in body["matches"])

    r_case = client.get(f"/pdf/{sid}/search", params={"q": "Hello", "match_case": True}, headers=h)
    assert r_case.status_code == 200
    assert r_case.json()["total"] == 2
    assert [m["page"] for m in r_case.json()["matches"]] == [0, 0]


def test_search_not_found_and_validation(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_multipage_pdf())

    r_none = client.get(f"/pdf/{sid}/search", params={"q": "NoSuchKeyword"}, headers=h)
    assert r_none.status_code == 200
    assert r_none.json()["total"] == 0
    assert r_none.json()["matches"] == []

    r_empty = client.get(f"/pdf/{sid}/search", params={"q": "   "}, headers=h)
    assert r_empty.status_code == 400

    r_long = client.get(f"/pdf/{sid}/search", params={"q": "a" * 301}, headers=h)
    assert r_long.status_code == 400

    _, other = make_user()
    assert client.get(f"/pdf/{sid}/search", params={"q": "hello"}, headers=other).status_code in (403, 404)
