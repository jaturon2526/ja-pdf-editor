"""เครื่องมือด่วน: ลายน้ำ / เซ็นเซอร์ด้วยคำค้นหา — บั๊กที่พบจากการรีวิว v1.26.5"""
import io

import fitz
import numpy as np
import pytest

from tests.test_file_signature_status import _download, _file_id, _files
from app.services.edit_service import watermark as wm_mod
from app.services.pdf_service import redact, text_index


# --------------------------------------------------------------------------- เซ็นเซอร์
def _pdf_with_hidden_copies() -> bytes:
    d = fitz.open()
    p = d.new_page()
    p.insert_text((50, 80), "Customer Alice Smith", fontsize=14)
    note = p.add_text_annot((300, 80), "note about Alice")
    note.set_info(title="Alice")
    w = fitz.Widget()
    w.field_name, w.field_value, w.rect = "name", "Alice", fitz.Rect(50, 300, 250, 320)
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    p.add_widget(w)
    d.set_toc([[1, "Alice section", 1]])
    d.set_metadata({"title": "Report on Alice", "author": "Alice"})
    return d.tobytes()


def test_redact_search_scrubs_fields_notes_bookmarks_metadata(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, _pdf_with_hidden_copies(), name="a.pdf"))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={"action": "redact_search", "keyword": "alice"})
    assert r.status_code == 200, r.text
    out = fitz.open("pdf", _download(client, owner, r.json()["file"]["session_id"]))
    page = out[0]
    assert "Alice" not in page.get_text()                      # รวมข้อความในช่องฟอร์มที่แสดงบนหน้า
    assert all("Alice" not in (w.field_value or "") for w in page.widgets())
    for a in page.annots():
        assert "Alice" not in a.info["content"] and "Alice" not in a.info["title"]
    assert "Alice" not in str(out.get_toc()) and "Alice" not in str(out.metadata)


def test_redact_search_only_in_metadata_still_creates_file(client, make_user, upload):
    _, owner = make_user()
    d = fitz.open()
    d.new_page().insert_text((50, 80), "nothing here")
    d.set_metadata({"author": "Somchai"})
    fid = _file_id(client, owner, upload(owner, d.tobytes(), name="m.pdf"))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={"action": "redact_search", "keyword": "Somchai"})
    assert r.json()["status"] == "ok"
    out = fitz.open("pdf", _download(client, owner, r.json()["file"]["session_id"]))
    assert "Somchai" not in out.metadata["author"]


def test_quick_action_names_are_unique(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, _pdf_with_hidden_copies(), name="รายงาน.pdf"))
    names = [client.post(f"/pdf/files/{fid}/quick-action", headers=owner,
                         json={"action": "watermark", "watermark": {"text": "ลับ"}}).json()["file"]["filename"]
             for _ in range(3)]
    assert names == ["รายงาน (ลายน้ำ).pdf", "รายงาน (ลายน้ำ) (2).pdf", "รายงาน (ลายน้ำ) (3).pdf"]
    assert len({f["filename"] for f in _files(client, owner)}) == 4


@pytest.mark.parametrize("regex", [r"(a+)+$", r"(\w*\s?)*x", r"(-+)+x"])
def test_nested_quantifier_regex_rejected(client, make_user, upload, regex):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, _pdf_with_hidden_copies()))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner,
                    json={"action": "redact_search", "keyword": regex, "is_regex": True})
    assert r.status_code == 400 and "ซ้ำซ้อน" in r.json()["detail"]


@pytest.mark.parametrize("regex", [r"0[689]\d-?\d{3}-?\d{4}", r"\d{1,3}(,\d{3})*", r"(\d|-)+", r"[\w.+-]+@[\w-]+\.[\w.-]+"])
def test_common_regex_allowed(regex):
    assert not text_index._nested_repeat(regex)


def test_match_case(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, _pdf_with_hidden_copies()))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner,
                    json={"action": "redact_search", "keyword": "customer", "match_case": True})
    assert r.json()["status"] == "not_found"


# --------------------------------------------------------------------------- ลายน้ำ
class _S:
    def __init__(self, doc):
        self.doc, self.user_id = doc, None

    def mark_dirty(self):
        pass


@pytest.fixture
def unlocked(monkeypatch):
    monkeypatch.setattr(wm_mod, "require_unlocked", lambda s: s.doc)


def _red_box(page):
    pix = page.get_pixmap(dpi=36)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].astype(int)
    m = (a[:, :, 0] > 150) & (a[:, :, 1] < 120) & (a[:, :, 2] < 120)
    ys, xs = np.nonzero(m)
    return pix.width, pix.height, xs, ys


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_watermark_centered_and_upright_on_rotated_pages(unlocked, rotation):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.set_rotation(rotation)
    wm_mod.apply_watermark(_S(d), "WWWWWWWWWW", 1.0, 0, (1, 0, 0), 60)  # แนวนอน → ต้องกว้างกว่าสูงตามที่มองเห็น
    W, H, xs, ys = _red_box(d[0])
    assert abs(xs.mean() - W / 2) < W * 0.05 and abs(ys.mean() - H / 2) < H * 0.05
    assert (xs.max() - xs.min()) > 3 * (ys.max() - ys.min())


def test_watermark_long_text_fits_small_page(unlocked):
    d = fitz.open()
    d.new_page(width=298, height=420)  # A6
    wm_mod.apply_watermark(_S(d), "สำเนาถูกต้อง ใช้สำหรับยื่นธนาคารเท่านั้น ห้ามนำไปใช้อย่างอื่น", 1.0, 45, (1, 0, 0), 100)
    W, H, xs, ys = _red_box(d[0])
    assert len(xs) and xs.min() > 0 and ys.min() > 0 and xs.max() < W - 1 and ys.max() < H - 1


def test_watermark_huge_text_does_not_explode(unlocked):
    d = fitz.open()
    d.new_page()
    wm_mod.apply_watermark(_S(d), "ก" * 200, 0.5, 30, (1, 0, 0), 300)
    img = d[0].get_images()[0]
    assert max(img[2], img[3]) <= 4500


def test_watermark_request_validation(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, _pdf_with_hidden_copies()))
    for bad in ({"text": "x" * 201}, {"text": "x", "font_size": 5000}, {"text": "x", "opacity": 3},
                {"text": "x", "color": [2, 0, 0]}):
        r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={"action": "watermark", "watermark": bad})
        assert r.status_code == 422, bad
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={"action": "watermark", "watermark": {"text": "  \n "}})
    assert r.status_code == 400
