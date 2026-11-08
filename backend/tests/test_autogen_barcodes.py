"""Auto-Gen + QR/บาร์โค้ด: พิมพ์ในข้อความ · รูปตัวแทน (Alt Text) · ข้อมูลว่าง · ข้อมูลผิด → ไฟล์ error · ตัวอย่างในคู่มือ"""
import io
import zipfile
from pathlib import Path

import docx
import pytest
from PIL import Image

from app.services import barcode_service
from tests.test_autogen import _gen, _tpl
from tests.test_autogen_password import fake_pdf  # noqa: F401 — ไม่ต้องรอ LibreOffice (autouse)

zxingcpp = pytest.importorskip("zxingcpp")
SAMPLES = Path(__file__).resolve().parents[1] / "sample_autogen"


def _images(docx_bytes: bytes) -> list[Image.Image]:
    d = docx.Document(io.BytesIO(docx_bytes))
    out = []
    for rel in d.part.rels.values():
        if "image" in rel.reltype:
            out.append(Image.open(io.BytesIO(rel.target_part.blob)))
    return out


def _decoded(docx_bytes: bytes) -> set[str]:
    texts = set()
    for img in _images(docx_bytes):
        texts |= {r.text for r in zxingcpp.read_barcodes(img.convert("RGB"))}
    return texts


def _unzip(resp) -> dict[str, bytes]:
    assert resp.status_code == 200, resp.text
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    return {n: z.read(n) for n in z.namelist()}


def test_inline_qr_and_barcode_with_thai(client, make_user):
    _, h = make_user()
    tpl = _tpl('ชื่อ {{ name }}\n{{ qr(link, 30) }}\nรหัส {{ barcode("code128", code, 50, 12) }} ท้ายบรรทัด\n{{ qr("ชื่อ: " ~ name) }}')
    data = "name,link,code\nสมชาย ใจดี,https://example.com/ก,EMP-001\nJohn,https://example.com/j,EMP-002\n".encode()
    files = _unzip(_gen(client, h, tpl, data))
    first = files["สมชาย ใจดี.docx"]
    assert _decoded(first) == {"https://example.com/ก", "EMP-001", "ชื่อ: สมชาย ใจดี"}
    d = docx.Document(io.BytesIO(first))
    assert d.paragraphs[2].text == "รหัส  ท้ายบรรทัด"     # ข้อความรอบบาร์โค้ดยังอยู่
    widths = sorted(round(s.width.mm) for s in d.inline_shapes)
    assert widths == [25, 30, 50]                         # ค่าเริ่มต้น QR 25 มม. · กำหนดเอง 30 / 50
    assert "@@JABC" not in "\n".join(p.text for p in d.paragraphs)


def test_frame_placeholder_keeps_box_and_empty_value_removes_it(client, make_user):
    _, h = make_user()
    tpl = (SAMPLES / "template_qr.docx").read_bytes()
    files = _unzip(_gen(client, h, tpl, (SAMPLES / "data_qr.csv").read_bytes(), data_name="data_qr.csv"))
    assert len(files) == 4 and not any(n.startswith("error") for n in files)
    first = files["สมชาย ใจดี.docx"]
    found = _decoded(first)
    assert {"https://example.com/staff/EMP-00123", "EMP-00123"} <= found
    assert any(t.startswith("ชื่อ: สมชาย ใจดี") for t in found)
    d = docx.Document(io.BytesIO(first))
    frame = next(s for s in d.inline_shapes if round(s.width.mm) == 28)
    assert round(frame.height.mm) == 28                    # ขนาดตามกรอบที่ออกแบบ
    descr = d.part.element.xpath(".//wp:docPr/@descr")
    assert any(x.startswith("QR Code: https://example.com/staff/EMP-00123") for x in descr)
    # คนที่ 4 ไม่มีลิงก์ → ไม่มี QR มุมขวา แต่บาร์โค้ดและ QR ข้อมูลติดต่อยังอยู่
    last = files["วิไล มั่นคง.docx"]
    assert "EMP-00126" in _decoded(last)
    assert not any(round(s.width.mm) == 28 for s in docx.Document(io.BytesIO(last)).inline_shapes)


def test_invalid_data_goes_to_error_file(client, make_user):
    _, h = make_user()
    tpl = _tpl('{{ name }} {{ barcode("ean13", sku) }}')
    data = "name,sku\nดี,5901234123457\nผิด,12AB\n".encode()
    files = _unzip(_gen(client, h, tpl, data))
    assert "ดี.docx" in files and "error_item_2.txt" in files
    assert "EAN-13" in files["error_item_2.txt"].decode()
    r = _gen(client, h, _tpl('{{ barcode("hologram", sku) }}'), data)
    assert r.status_code == 400 and "ไม่รู้จักประเภทบาร์โค้ด" in r.json()["detail"]


def test_preview_lists_columns_not_functions(client, make_user):
    _, h = make_user()
    r = client.post("/autogen/preview", headers=h,
                    files={"data": ("data_qr.csv", (SAMPLES / "data_qr.csv").read_bytes()),
                           "template": ("template_qr.docx", (SAMPLES / "template_qr.docx").read_bytes())})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["template_variables"]) == {"name", "emp_id", "dept", "phone", "profile_url"}
    assert body["missing_variables"] == []


def test_merged_pdf_output(client, make_user, fake_pdf):  # noqa: F811
    _, h = make_user()
    tpl = (SAMPLES / "template_qr.docx").read_bytes()
    r = _gen(client, h, tpl, (SAMPLES / "data_qr.xlsx").read_bytes(), data_name="data_qr.xlsx",
             output_format="pdf", split_files="false")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert r.headers["x-autogen-created"] == "4"


def test_batch_renderer_isolates_failures_and_dedupes(client):
    specs = [barcode_service.BarcodeSpec("qrcode", "same"), barcode_service.BarcodeSpec("code128", "OK-1"),
             barcode_service.BarcodeSpec("qrcode", "ก" * 990, ec_level="H"), barcode_service.BarcodeSpec("code128", "OK-2")]
    out = barcode_service.render_png_batch(specs)
    assert isinstance(out[2], barcode_service.BarcodeError) and "ยาวเกิน" in str(out[2])
    texts = [zxingcpp.read_barcodes(Image.open(io.BytesIO(out[k])).convert("RGB"))[0].text for k in (0, 1, 3)]
    assert texts == ["same", "OK-1", "OK-2"]


def test_samples_downloadable(client):
    for name in ("template_qr.docx", "data_qr.xlsx", "data_qr.csv"):
        assert client.get(f"/autogen/samples/{name}").status_code == 200
