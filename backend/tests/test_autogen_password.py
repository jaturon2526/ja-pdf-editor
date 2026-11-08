"""Auto-Gen: เข้ารหัส PDF แต่ละไฟล์ด้วยรหัสผ่านจากคอลัมน์ในไฟล์ข้อมูล (แยกไฟล์ + PDF)"""
import io
import zipfile

import docx
import fitz
import pytest

from app.api import routes_autogen


def _template() -> bytes:
    d = docx.Document()
    d.add_paragraph("เรียน {{ name }} รหัส {{ emp_id }}")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def fake_pdf(monkeypatch):
    """ไม่ต้องรอ LibreOffice — คืน PDF 1 หน้าที่มีข้อความจาก docx"""
    async def _convert(doc_bytes, _name, user_id=None):
        text = " ".join(p.text for p in docx.Document(io.BytesIO(doc_bytes)).paragraphs)
        pdf = fitz.open()
        pdf.new_page().insert_text((72, 72), text.encode("ascii", "ignore").decode() or "x")
        out = pdf.tobytes()
        pdf.close()
        return out

    async def _batch(docs, user_id=None):
        return [await _convert(d, "x.docx") for d in docs]

    monkeypatch.setattr(routes_autogen, "convert_office_to_pdf_bytes", _convert)
    monkeypatch.setattr(routes_autogen, "convert_docx_batch_to_pdf", _batch)


CSV = "name,emp_id,birth\nSomchai,E001,1990\nSomying,E002,1985\nNoPass,E003,\n"


def _generate(client, headers, **form):
    data = {"output_format": "pdf", "split_files": "true", "filename_field": "emp_id", **form}
    return client.post("/autogen/", headers=headers, data=data,
                       files={"template": ("t.docx", _template()), "data": ("d.csv", CSV.encode("utf-8"), "text/csv")})


def test_each_pdf_is_encrypted_with_its_own_password(client, make_user):
    _, h = make_user()
    r = _generate(client, h, password_field="birth")
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert {"E001.pdf", "E002.pdf"} <= names
    for name, pw in (("E001.pdf", "1990"), ("E002.pdf", "1985")):
        doc = fitz.open("pdf", zf.read(name))
        assert doc.needs_pass and not doc.authenticate("wrong") and doc.authenticate(pw)
    # แถวที่ไม่มีรหัสผ่าน: ไม่มีไฟล์ PDF หลุดออกไปแบบไม่เข้ารหัส มีแค่ไฟล์แจ้ง error
    assert "E003.pdf" not in names
    assert any(n.startswith("error_item_3") for n in names)


def test_password_from_template_expression(client, make_user):
    _, h = make_user()
    r = _generate(client, h, password_field="{{ emp_id }}{{ birth }}")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert fitz.open("pdf", zf.read("E001.pdf")).authenticate("E0011990")


def test_without_password_field_files_are_not_encrypted(client, make_user):
    _, h = make_user()
    zf = zipfile.ZipFile(io.BytesIO(_generate(client, h).content))
    assert not fitz.open("pdf", zf.read("E003.pdf")).needs_pass


def test_password_field_requires_split_pdf(client, make_user):
    _, h = make_user()
    assert _generate(client, h, password_field="birth", output_format="docx").status_code == 400
    assert _generate(client, h, password_field="birth", split_files="false").status_code == 400


def test_unknown_password_column(client, make_user):
    _, h = make_user()
    r = _generate(client, h, password_field="citizen_id")
    assert r.status_code == 400 and "citizen_id" in r.json()["detail"]


def test_filename_template_is_sandboxed(client, make_user):
    _, h = make_user()
    r = _generate(client, h, filename_field="{{ ''.__class__.__mro__[1].__subclasses__() }}")
    assert r.status_code == 200
    assert not any("class" in n for n in zipfile.ZipFile(io.BytesIO(r.content)).namelist())
