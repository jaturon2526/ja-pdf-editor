"""รวมไฟล์ PDF (POST /pdf/merge): บันทึกเข้าเอกสารของฉัน · ไฟล์จากเครื่อง + ไฟล์ในระบบ · ข้อความผิดพลาดที่ชัดเจน · บุ๊กมาร์ก"""
import fitz

from tests.conftest import make_pdf_bytes


def _with_toc(pages: int, title: str) -> bytes:
    doc = fitz.open("pdf", make_pdf_bytes(pages, title))
    doc.set_toc([[1, f"{title} บทที่ 1", 1], [2, "หัวข้อย่อย", 2]])
    return doc.tobytes()


def _merge(client, headers, files=(), **form):
    return client.post("/pdf/merge", headers=headers, data=form,
                       files=[("files", (name, data, "application/pdf")) for name, data in files] or None)


def test_merge_is_saved_to_my_documents_with_bookmarks(client, make_user):
    _, h = make_user()
    r = _merge(client, h, [("สัญญา.pdf", _with_toc(2, "AAA")), ("ภาคผนวก.pdf", make_pdf_bytes(3, "BBB"))])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "สัญญา (รวม 2 ไฟล์).pdf" and body["page_count"] == 5
    names = [f["filename"] for f in client.get("/pdf/files", headers=h).json()["files"]]
    assert "สัญญา (รวม 2 ไฟล์).pdf" in names                         # อยู่ในเอกสารของฉัน
    assert client.post(f"/pdf/{body['session_id']}/save", headers=h).status_code == 200   # กดบันทึกได้
    from app.core.session import session_manager

    toc = [tuple(t[:3]) for t in session_manager.get(body["session_id"]).doc.get_toc()]
    assert (1, "สัญญา", 1) in toc and (1, "ภาคผนวก", 3) in toc and (2, "AAA บทที่ 1", 1) in toc   # บุ๊กมาร์กเดิมซ้อนใต้ชื่อไฟล์
    # ชื่อซ้ำ → เติม (2)
    r = _merge(client, h, [("สัญญา.pdf", make_pdf_bytes(1)), ("x.pdf", make_pdf_bytes(1))])
    assert r.json()["filename"] == "สัญญา (รวม 2 ไฟล์) (2).pdf"


def test_merge_files_from_my_documents_in_given_order(client, make_user, upload):
    _, h = make_user()
    upload(h, make_pdf_bytes(2, "STORED"), name="stored.pdf")
    stored = next(f for f in client.get("/pdf/files", headers=h).json()["files"] if f["filename"] == "stored.pdf")
    r = _merge(client, h, [("local.pdf", make_pdf_bytes(1, "LOCAL"))], file_ids=str(stored["id"]), order=f"f{stored['id']},u0")
    assert r.status_code == 200, r.text
    assert r.json()["filename"] == "stored (รวม 2 ไฟล์).pdf" and r.json()["page_count"] == 3


def test_merge_rejects_other_users_files_and_bad_input(client, make_user, upload):
    _, owner = make_user()
    upload(owner, name="private.pdf")
    fid = client.get("/pdf/files", headers=owner).json()["files"][0]["id"]
    _, other = make_user()
    r = _merge(client, other, [("a.pdf", make_pdf_bytes(1))], file_ids=str(fid))
    assert r.status_code == 404
    r = _merge(client, other, [("a.pdf", make_pdf_bytes(1))])
    assert r.status_code == 400 and "อย่างน้อย 2" in r.json()["detail"]
    r = _merge(client, other, [("a.pdf", make_pdf_bytes(1)), ("b.pdf", make_pdf_bytes(1))], order="u0,u5")
    assert r.status_code == 400


def test_merge_explains_encrypted_and_broken_files(client, make_user):
    _, h = make_user()
    d = fitz.open()
    d.new_page()
    enc = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="o")
    r = _merge(client, h, [("a.pdf", make_pdf_bytes(1)), ("ลับ.pdf", enc)])
    assert r.status_code == 400 and "ลับ.pdf" in r.json()["detail"] and "รหัสผ่าน" in r.json()["detail"]
    r = _merge(client, h, [("a.pdf", make_pdf_bytes(1)), ("เสีย.pdf", b"not a pdf")])
    assert r.status_code == 400 and "เสีย.pdf" in r.json()["detail"]
    assert client.get("/pdf/files", headers=h).json()["files"] == []          # ไม่สร้างไฟล์ครึ่ง ๆ กลาง ๆ
