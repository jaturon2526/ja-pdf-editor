"""แยกหน้าเอกสาร (/extract) และส่งออกหน้าที่เลือก — ลำดับ, ฟอร์ม/ลิงก์/บุ๊กมาร์ก, ขนาดไฟล์, รหัสผ่าน, ชื่อไฟล์ไทย"""
import io
import zipfile
from pathlib import Path
from urllib.parse import unquote

import fitz
import pytest

from app.services.pdf_service.core import PDFError
from app.services.pdf_service.pages import _range_label, parse_page_range

FONT = str(Path("app/assets/fonts/Sarabun-Regular.ttf").resolve())


def _doc(n=12):
    d = fitz.open()
    for i in range(n):
        p = d.new_page()
        p.insert_font(fontname="sar", fontfile=FONT)
        p.insert_text((72, 80), f"หน้า {i + 1}", fontname="sar", fontsize=20)
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect, w.field_value = "f", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(72, 200, 300, 220), "ค่า"
    d[2].add_widget(w)
    d[1].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 100, 200, 120), "page": 2})
    d.set_toc([[1, "บทที่ 1", 1], [1, "บทที่ 2", 3]])
    return d.tobytes(garbage=3, deflate=True)


def _texts(pdf):
    return [p.get_text().strip().splitlines()[0] for p in pdf]


def _filename(resp):
    cd = resp.headers["content-disposition"]
    return unquote(cd.split("filename*=UTF-8''", 1)[1])


@pytest.mark.parametrize("text,expected", [
    ("1,2,4-6", [0, 1, 3, 4, 5]),
    ("5,1-3", [4, 0, 1, 2]),
    ("6-4", [5, 4, 3]),
    ("1-3,2,1", [0, 1, 2]),
    ("2–4", [1, 2, 3]),
    (" 1 , 3 ", [0, 2]),
    ("-3", [0, 1, 2]),
    ("10-", [9, 10, 11]),
    ("1,,2", [0, 1]),
    ("๑-๓", [0, 1, 2]),
])
def test_parse_page_range(text, expected):
    assert parse_page_range(text, 12) == expected


@pytest.mark.parametrize("bad", ["0", "13", "abc", "1-3-5", "2-x", "-", "1.5"])
def test_parse_page_range_rejects(bad):
    with pytest.raises(PDFError):
        parse_page_range(bad, 12)


def test_range_label():
    assert _range_label([0, 1, 2, 4]) == "1-3,5"
    assert _range_label([4, 0, 1]) == "5,1-2"


def test_extract_single_keeps_order_forms_links_toc_and_size(client, make_user, upload):
    _, h = make_user()
    data = _doc()
    sid = upload(h, data, name="สัญญาเช่า.pdf")
    r = client.post(f"/pdf/{sid}/extract", headers=h, json={"page_range": "3,1-2", "mode": "single"})
    assert r.status_code == 200, r.text  # เดิม: ชื่อไฟล์ไทย → 500 (header latin-1)
    assert _filename(r) == "สัญญาเช่า (หน้า 3,1-2).pdf"
    out = fitz.open("pdf", r.content)
    assert _texts(out) == ["หน้า 3", "หน้า 1", "หน้า 2"]  # เดิมเรียง 1,2,3 เสมอ
    assert [w.field_name for w in out[0].widgets()] == ["f"]  # ช่องกรอกฟอร์มยังอยู่
    links = out[2].get_links()  # ลิงก์บนหน้า 2 เดิม (ชี้หน้า 3) → ตอนนี้ชี้หน้าแรกของไฟล์ใหม่
    assert links and links[0]["page"] == 0
    assert [t[1] for t in out.get_toc()] == ["บทที่ 1", "บทที่ 2"]
    assert len(r.content) < len(data)  # เดิม 3 หน้าใหญ่กว่าต้นฉบับ 12 หน้าเกือบ 3 เท่า


def test_extract_split_zero_padded_names(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(), name="doc.pdf")
    r = client.post(f"/pdf/{sid}/extract", headers=h, json={"page_range": "10,2", "mode": "split"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert _filename(r) == "doc (แยก 2 หน้า).zip"
    assert 'filename="pages.zip"' in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.namelist() == ["doc_หน้า_10.pdf", "doc_หน้า_02.pdf"]
    assert _texts(fitz.open("pdf", z.read("doc_หน้า_02.pdf"))) == ["หน้า 2"]


def test_extract_includes_unsaved_edits_and_password(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(3), name="doc.pdf")
    assert client.post(f"/pdf/{sid}/add-password", headers=h, json={"password": "pw-1234"}).status_code == 200
    r = client.post(f"/pdf/{sid}/extract", headers=h, json={"page_range": "1", "mode": "single"})
    assert r.status_code == 200
    out = fitz.open("pdf", r.content)
    assert out.needs_pass  # เดิม: ไฟล์ที่แยกออกมาไม่มีรหัสผ่าน ทั้งที่ตั้งไว้แล้ว
    assert out.authenticate("pw-1234")
    assert _texts(out) == ["หน้า 1"]


def test_extract_errors(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _doc(3), name="doc.pdf")
    for bad in ["4", "abc", " "]:
        r = client.post(f"/pdf/{sid}/extract", headers=h, json={"page_range": bad, "mode": "single"})
        assert r.status_code == 400, (bad, r.text)
    r = client.post(f"/pdf/{sid}/extract", headers=h, json={"page_range": "1", "mode": "zip"})
    assert r.status_code == 400
