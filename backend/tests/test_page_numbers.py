"""ใส่เลขหน้า (edit_service/page_numbers.py): รูปแบบ 1 / 1/N / เลขไทย / คำนำหน้า, เริ่มที่หน้าไหนก็ได้ (หน้าแรกที่ใส่ = 1,
N = จำนวนหน้าที่ใส่), หน้าคู่สลับข้าง (ตามลำดับหน้าจริง), หน้าหมุน, ข้อความจริงค้นหาได้, Editor + Dashboard"""
import fitz
import pytest

from app.services.edit_service.page_numbers import PageNumberOptions, page_plan
from app.services.pdf_service import PDFError
from tests.conftest import make_pdf_bytes
from tests.test_file_signature_status import _download, _file_id


def test_plan_matches_user_defaults():
    plan = page_plan(10, PageNumberOptions(fmt="n_total", start_page=2, hpos="left", mirror_even=True))
    assert len(plan) == 9
    assert plan[0] == (1, "1/9", "right")      # หน้า 2 ในไฟล์ (คู่) → เลข 1 ฝั่งตรงข้าม
    assert plan[1] == (2, "2/9", "left")       # หน้า 3 (คี่) → ฝั่งที่เลือก
    assert plan[-1] == (9, "9/9", "right")
    thai = page_plan(3, PageNumberOptions(fmt="n_total", thai_digits=True, separator=" จาก ", prefix="หน้า "))
    assert [t for _, t, _ in thai] == ["หน้า ๑ จาก ๓", "หน้า ๒ จาก ๓", "หน้า ๓ จาก ๓"]
    assert [s for _, _, s in page_plan(4, PageNumberOptions(hpos="center", mirror_even=True))] == ["center"] * 4
    with pytest.raises(PDFError):
        page_plan(3, PageNumberOptions(start_page=5))


def _words(page):
    return [(w[4], fitz.Rect(w[:4])) for w in page.get_text("words")]


def test_editor_adds_searchable_numbers_at_positions(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(pages=4, text="Body"))
    r = client.post(f"/edit/{sid}/page-numbers", headers=h, json={
        "fmt": "n_total", "start_page": 2, "hpos": "left", "mirror_even": True, "vpos": "bottom"})
    assert r.status_code == 200 and r.json()["count"] == 3, r.text
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    assert "1/3" not in doc[0].get_text()                      # หน้าแรกไม่ใส่
    for idx, label, side in ((1, "1/3", "right"), (2, "2/3", "left"), (3, "3/3", "right")):
        page = doc[idx]
        hits = page.search_for(label)
        assert hits, (idx, page.get_text())
        rect = hits[0]
        assert rect.y0 > page.rect.height * 0.85               # ด้านล่าง
        if side == "left":
            assert rect.x1 < page.rect.width * 0.3
        else:
            assert rect.x0 > page.rect.width * 0.7
    # undo ได้
    assert client.post(f"/pdf/{sid}/undo", headers=h).status_code == 200
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    assert not doc[1].search_for("1/3")


def test_thai_digits_via_api(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(pages=2, text="Body"))
    r = client.post(f"/edit/{sid}/page-numbers", headers=h, json={
        "thai_digits": True, "prefix": "หน้า ", "vpos": "top", "hpos": "right"})
    assert r.status_code == 200, r.text
    doc = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    assert "หน้า ๑" in doc[0].get_text() and "หน้า ๒" in doc[1].get_text()


@pytest.mark.parametrize("rotation, expected_dir", [(90, (0, -1)), (180, (-1, 0)), (270, (0, 1))])
def test_rotated_page_number_is_upright_at_visible_corner(monkeypatch, rotation, expected_dir):
    """หน้าที่มี /Rotate (ระบบอัปโหลดบางเส้นทางเก็บ rotation ไว้): ตัวเลขต้องอยู่มุมที่มองเห็นและตั้งตรง (เคยกลับหัว)"""
    from types import SimpleNamespace

    from app.services.edit_service import page_numbers as pn

    doc = fitz.open("pdf", make_pdf_bytes(pages=1, text="Body"))
    doc[0].set_rotation(rotation)
    session = SimpleNamespace(doc=doc, user_id=None, mark_dirty=lambda: None)
    monkeypatch.setattr(pn, "require_unlocked", lambda s: s.doc)
    pn.apply_page_numbers(session, PageNumberOptions(prefix="หน้า ", vpos="top", hpos="right"))
    page = doc[0]
    lines = [line for b in page.get_text("dict")["blocks"] for line in b.get("lines", [])
             if "หน้า" in "".join(sp["text"] for sp in line["spans"])]
    assert [tuple(round(v) for v in line["dir"]) for line in lines] == [expected_dir]
    rect = fitz.Rect(lines[0]["bbox"]) * page.rotation_matrix  # พิกัดที่มองเห็น
    vis = page.rect
    assert rect.y1 < vis.height * 0.2 and rect.x0 > vis.width * 0.6, (rect, vis)


def test_dashboard_quick_action_creates_new_file(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, make_pdf_bytes(pages=3, text="Body"), name="รายงาน.pdf")
    fid = _file_id(client, h, sid)
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=h,
                    json={"action": "page_numbers", "page_numbers": {"fmt": "n_total"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file"]["filename"] == "รายงาน (เลขหน้า).pdf"
    doc = fitz.open("pdf", _download(client, h, body["file"]["session_id"]))
    assert doc[2].search_for("3/3")
    bad = client.post(f"/pdf/files/{fid}/quick-action", headers=h,
                      json={"action": "page_numbers", "page_numbers": {"start_page": 9}})
    assert bad.status_code == 400 and "3 หน้า" in bad.json()["detail"]
