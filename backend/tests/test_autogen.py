"""Auto-Gen: ความปลอดภัยของ Template, การอ่านไฟล์ข้อมูล, ชื่อไฟล์, ข้อจำกัด และหน้าตัวอย่างข้อมูล"""
import datetime as dt
import io
import zipfile

import docx
import openpyxl
import pytest

from app.api import routes_autogen
from tests.test_autogen_password import fake_pdf  # noqa: F401 — ไม่ต้องรอ LibreOffice


def _tpl(text: str) -> bytes:
    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _gen(client, h, template: bytes, data: bytes, data_name="d.csv", **form):
    form = {"output_format": "docx", "split_files": "true", **form}
    return client.post("/autogen/", headers=h, data=form,
                       files={"template": ("t.docx", template), "data": (data_name, data)})


def _texts(docx_bytes: bytes) -> str:
    return "\n".join(p.text for p in docx.Document(io.BytesIO(docx_bytes)).paragraphs)


def test_template_cannot_run_python(client, make_user):
    """Template Word ที่ผู้ใช้อัปโหลด render ใน sandbox — เดิมใช้ Jinja2 ธรรมดา เข้าถึง object ของ Python ได้"""
    _, h = make_user()
    r = _gen(client, h, _tpl("{{ ''.__class__.__mro__[1].__subclasses__()|length }}"), b"name\nA\n")
    assert r.status_code == 400 and "สร้างเอกสารไม่ได้" in r.json()["detail"]


def test_values_with_xml_characters_keep_the_docx_valid(client, make_user):
    _, h = make_user()
    r = _gen(client, h, _tpl("บริษัท {{ name }}"), "name\nA & B <จำกัด>\n".encode(), split_files="false")
    assert r.status_code == 200, r.text
    assert "บริษัท A & B <จำกัด>" in _texts(r.content)


def test_template_syntax_error_is_reported(client, make_user):
    _, h = make_user()
    r = _gen(client, h, _tpl("{{ name "), b"name\nA\n")
    assert r.status_code == 400 and "Template" in r.json()["detail"]


def test_thai_cp874_semicolon_csv_and_header_spaces_are_detected(client, make_user):
    _, h = make_user()
    csv_bytes = " ชื่อ ;รหัส\nสมชาย;E001\n".encode("cp874")
    r = _gen(client, h, _tpl("เรียน {{ ชื่อ }} รหัส {{ รหัส }}"), csv_bytes, split_files="false")
    assert r.status_code == 200, r.text
    assert "เรียน สมชาย รหัส E001" in _texts(r.content)


def test_excel_numbers_and_dates_render_cleanly(client, make_user):
    _, h = make_user()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "amount", "due"])
    ws.append(["A", 1234.0, dt.datetime(2026, 1, 5)])
    ws.append([None, None, None])                       # แถวว่างถูกข้าม
    buf = io.BytesIO()
    wb.save(buf)
    r = _gen(client, h, _tpl("{{ name }} {{ amount }} {{ due }}"), buf.getvalue(), data_name="d.xlsx", split_files="false")
    assert r.status_code == 200, r.text
    assert "A 1234 2026-01-05" in _texts(r.content)
    assert r.headers["x-autogen-created"] == "1"


def test_file_names_are_sanitised_and_unique(client, make_user):
    _, h = make_user()
    data = 'id,name\n1,../ลับ\\a:b\n2,สมชาย\n3,สมชาย\n4,สมชาย-2\n'.encode()
    r = _gen(client, h, _tpl("{{ name }}"), data, filename_field="name", output_filename='ผล"ลัพธ์.zip')
    assert r.status_code == 200, r.text
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert all("/" not in n and "\\" not in n and ":" not in n and not n.startswith(".") for n in names)
    assert len(set(names)) == 4 and {"สมชาย.docx", "สมชาย-2.docx"} <= set(names)
    assert '"' not in r.headers["content-disposition"].split("filename*=")[0].strip('attachment; filename="').rstrip('"; ')


def test_row_limit(client, make_user, monkeypatch):
    _, h = make_user()
    monkeypatch.setattr(routes_autogen, "MAX_ROWS_PDF", 3)
    data = ("name\n" + "\n".join(f"n{i}" for i in range(5))).encode()
    r = _gen(client, h, _tpl("{{ name }}"), data, output_format="pdf")
    assert r.status_code == 400 and "ไม่เกิน" in r.json()["detail"]


def test_preview_reports_missing_template_variables(client, make_user):
    _, h = make_user()
    r = client.post("/autogen/preview", headers=h,
                    files={"data": ("d.csv", "name,city\nA,B\n".encode()), "template": ("t.docx", _tpl("{{ name }} {{ phone }}"))})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["headers"] == ["name", "city"] and body["missing_variables"] == ["phone"]
    assert body["delimiter"] == "," and body["encoding"] == "utf-8-sig"


@pytest.mark.parametrize("raw, ok", [("ใบแจ้งหนี้ ม.ค.", "ใบแจ้งหนี้ ม.ค"), ("../../etc/passwd", "_.._etc_passwd"), ("", "x")])
def test_safe_name(raw, ok):
    assert routes_autogen.safe_name(raw, "x") == ok
