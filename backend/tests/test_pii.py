"""PDPA — ตรวจหาและปิดข้อมูลส่วนบุคคล (pdf_service.pii + /pdf/{sid}/pii/* + Dashboard pdpa)"""
from pathlib import Path

import fitz
import pytest

from app.services.pdf_service import pii
from tests.test_signing import _file_id

FONT = Path(__file__).resolve().parents[1] / "app/assets/fonts/Sarabun-Regular.ttf"


def _make_id(first12: str) -> str:
    total = sum(int(first12[i]) * (13 - i) for i in range(12))
    return first12 + str((11 - total % 11) % 10)


VALID_ID = _make_id("110170023070")          # บุคคล
VALID_TAX = _make_id("010555612345")         # นิติบุคคล (ขึ้นต้น 0)
BAD_ID = VALID_ID[:-1] + str((int(VALID_ID[-1]) + 1) % 10)
VISA = "4111111111111111"


def _fmt_id(d: str) -> str:
    return f"{d[0]}-{d[1:5]}-{d[5:10]}-{d[10:12]}-{d[12]}"


def _pdf(lines: list[str], rotate: int = 0, metadata: bool = False) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for line in lines:
        page.insert_text((50, y), line, fontsize=12, fontname="sarabun", fontfile=str(FONT))
        y += 22
    if rotate:
        page.set_rotation(rotate)
    if metadata:
        doc.set_metadata({"author": "สมชาย ใจดี", "title": "สัญญาเช่า"})
    data = doc.tobytes()
    doc.close()
    return data


class _S:  # session จำลองสำหรับทดสอบ service โดยตรง
    def __init__(self, data):
        self.doc = fitz.open("pdf", data)
        self.session_id = "test"
        self.is_unlocked = True
        self.dirty = 0

    def mark_dirty(self):
        self.dirty += 1

    def push_history(self):
        pass


def _types(data):
    return sorted((f["type"], f["text"]) for f in pii.scan_pii(_S(data))["findings"])


# ---------------------------------------------------------------- ตัวตรวจ

def test_thai_id_checksum():
    assert pii.thai_id_checksum_ok(VALID_ID)
    assert pii.thai_id_checksum_ok(VALID_TAX)
    assert not pii.thai_id_checksum_ok(BAD_ID)
    assert not pii.thai_id_checksum_ok("123")


def test_luhn():
    assert pii.luhn_ok(VISA)
    assert not pii.luhn_ok("4111111111111112")


def test_detects_each_type_in_thai_text():
    found = _types(_pdf([
        f"เลขประจำตัวประชาชน {_fmt_id(VALID_ID)}",
        f"เลขผู้เสียภาษี {VALID_TAX}",
        "โทร 081-234-5678 หรือ 02 123 4567 หรือ +66 89 765 4321",
        "อีเมล somchai.j@example.co.th",
        "โอนเข้าบัญชีธนาคารกสิกรไทย เลขที่ 123-4-56789-0",
        "บัตรเครดิต 4111 1111 1111 1111",
        "ข้าพเจ้า นายสมชาย ใจดี ตกลงเช่า",
        "ที่อยู่ 99/1 หมู่ 2 ตำบลบางพลัด อำเภอเมือง จังหวัดนนทบุรี 11000",
        "Contact Mr. John Smith for details",
    ]))
    types = [t for t, _ in found]
    assert ("national_id", _fmt_id(VALID_ID)) in found
    assert ("national_id", VALID_TAX) in found
    assert types.count("phone") == 3
    assert ("email", "somchai.j@example.co.th") in found
    assert ("bank_account", "123-4-56789-0") in found
    assert ("credit_card", "4111 1111 1111 1111") in found
    assert ("person_name", "นายสมชาย ใจดี") in found
    assert ("person_name", "Mr. John Smith") in found
    addr = [t for typ, t in found if typ == "address"]
    assert addr and addr[0].startswith("99/1") and addr[0].endswith("11000")


def test_ignores_false_positives():
    found = _types(_pdf([
        f"เลขอ้างอิง {BAD_ID}",                 # checksum ผิด
        "ยอดเงิน 1234567890 บาท",               # 10 หลักแต่ไม่มีคำว่าบัญชี / ไม่ใช่รูปแบบเบอร์
        "นายจ้าง ตกลงจ่ายค่าจ้าง",                # ไม่ใช่ชื่อคน
        "ผลการทำนายสภาพอากาศ วันนี้",            # "นาย" อยู่กลางคำ
        "รหัสสินค้า 4111111111111112",           # Luhn ผิด
    ]))
    assert found == []


def test_rects_cover_only_the_match():
    data = _pdf([f"บัตร {_fmt_id(VALID_ID)} ของผู้เช่า"])
    f = pii.scan_pii(_S(data))["findings"][0]
    doc = fitz.open("pdf", data)
    page = doc[0]
    words = page.get_text("text", clip=fitz.Rect(f["rects"][0]["x0"], f["rects"][0]["y0"],
                                                 f["rects"][0]["x1"], f["rects"][0]["y1"])).strip()
    assert words == _fmt_id(VALID_ID)


def test_rotated_page_returns_display_coordinates():
    f = pii.scan_pii(_S(_pdf(["อีเมล a@b.co"], rotate=90)))["findings"][0]
    r = f["rects"][0]
    # หน้า A4 หมุน 90° → กว้าง 842 สูง 595 ข้อความเดิมอยู่ซ้ายบน (x≈50) จึงไปอยู่ด้านขวาบนของหน้าที่แสดง
    assert r["x0"] > 595 and r["y0"] < 200


def test_redact_removes_text_and_reports_masked():
    s = _S(_pdf([f"บัตร {_fmt_id(VALID_ID)}", "โทร 0812345678", "ผู้ติดต่อ"], metadata=True))
    found = pii.scan_pii(s)["findings"]
    id_only = [f["id"] for f in found if f["type"] == "national_id"]
    result = pii.redact_pii(s, id_only, clean_metadata=True)
    text = s.doc[0].get_text()
    assert VALID_ID[1:5] not in text            # เลขบัตรถูกลบจริง ไม่ใช่แค่ทับสี
    assert "0812345678" in text                  # รายการที่ไม่ได้เลือกยังอยู่
    assert result["redacted"] == 1 and s.dirty == 1
    masked = result["report"][0]["masked"]
    assert masked.startswith(VALID_ID[0]) and masked.endswith(VALID_ID[-1]) and "x" in masked
    assert VALID_ID[1:11] not in masked.replace("-", "")
    assert not s.doc.metadata.get("author")


def test_redact_with_stale_id_raises():
    s = _S(_pdf(["โทร 0812345678"]))
    with pytest.raises(pii.PIIStaleError):
        pii.redact_pii(s, ["p0-1-2-phone"])


def test_pages_without_text_are_reported():
    doc = fitz.open()
    doc.new_page()
    out = pii.scan_pii(_S(doc.tobytes()))
    assert out["pages_without_text"] == [0] and out["findings"] == []


# ---------------------------------------------------------------- API

def test_editor_scan_and_redact_api(client, make_user, upload):
    _, owner = make_user()
    sid = upload(owner, _pdf(["โทร 0812345678", "อีเมล x@y.com"]))
    scan = client.post(f"/pdf/{sid}/pii/scan", headers=owner)
    assert scan.status_code == 200, scan.text
    found = scan.json()["findings"]
    assert {f["type"] for f in found} == {"phone", "email"}
    phone = next(f["id"] for f in found if f["type"] == "phone")
    r = client.post(f"/pdf/{sid}/pii/redact", headers=owner, json={"ids": [phone]})
    assert r.status_code == 200 and r.json()["redacted"] == 1
    # สแกนซ้ำ: เหลือแค่อีเมล · id เดิมใช้ไม่ได้แล้ว → 409
    assert [f["type"] for f in client.post(f"/pdf/{sid}/pii/scan", headers=owner).json()["findings"]] == ["email"]
    assert client.post(f"/pdf/{sid}/pii/redact", headers=owner, json={"ids": [phone]}).status_code == 409


def test_other_user_cannot_scan(client, make_user, upload):
    _, owner = make_user()
    _, other = make_user()
    sid = upload(owner, _pdf(["โทร 0812345678"]))
    assert client.post(f"/pdf/{sid}/pii/scan", headers=other).status_code in (403, 404)


def test_dashboard_pdpa_creates_new_file(client, make_user, upload):
    _, owner = make_user()
    sid = upload(owner, _pdf([f"บัตร {_fmt_id(VALID_ID)}"]), name="สัญญา.pdf")
    fid = _file_id(client, owner, sid)
    scan = client.post(f"/pdf/files/{fid}/pii-scan", headers=owner, json={})
    assert scan.status_code == 200, scan.text
    ids = [f["id"] for f in scan.json()["findings"]]
    assert len(ids) == 1
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner,
                    json={"action": "pdpa", "pii_ids": ids, "clean_metadata": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1 and body["file"]["filename"] == "สัญญา (PDPA).pdf"
    assert body["report"][0]["type"] == "national_id"
    # ไฟล์ใหม่สแกนแล้วไม่พบอีก ไฟล์เดิมยังพบอยู่
    assert client.post(f"/pdf/files/{body['file']['id']}/pii-scan", headers=owner, json={}).json()["findings"] == []
    assert len(client.post(f"/pdf/files/{fid}/pii-scan", headers=owner, json={}).json()["findings"]) == 1


def test_dashboard_pdpa_requires_selection(client, make_user, upload):
    _, owner = make_user()
    fid = _file_id(client, owner, upload(owner, _pdf(["โทร 0812345678"])))
    r = client.post(f"/pdf/files/{fid}/quick-action", headers=owner, json={"action": "pdpa"})
    assert r.status_code == 400


# ---------------------------------------------------------------- เฟส 8: เลขไทย ยศ ราชสกุล ชื่อข้ามบรรทัด

def test_pii_eval_cases_all_found_without_false_positives():
    """ชุดข้อความทดสอบใน scripts/pii_eval.py (ชื่อ/เลขแต่งขึ้นทั้งหมด) — ต้องพบครบและไม่จับคำทั่วไป"""
    from scripts.pii_eval import evaluate

    r = evaluate()
    assert r["misses"] == [], r["misses"]
    assert r["false_pos"] == [], r["false_pos"]


def test_thai_digit_id_and_phone_in_pdf_keep_their_positions():
    th = str.maketrans("0123456789", "๐๑๒๓๔๕๖๗๘๙")
    data = _pdf([f"เลขประจำตัวประชาชน {_fmt_id(VALID_ID).translate(th)}", "โทรศัพท์ ๐๘๑-๒๓๔-๕๖๗๘"])
    found = _types(data)
    assert ("national_id", _fmt_id(VALID_ID).translate(th)) in found
    assert ("phone", "๐๘๑-๒๓๔-๕๖๗๘") in found
    report = pii.redact_pii(_S(data), [f["id"] for f in pii.scan_pii(_S(data))["findings"]])["report"]
    [masked] = [r["masked"] for r in report if r["type"] == "national_id"]
    assert masked[0] == "๑" and "x" in masked and masked[-2:] == _fmt_id(VALID_ID).translate(th)[-2:]   # ปิดเลขไทยด้วย


def test_name_split_across_lines_is_found_and_both_lines_are_covered():
    data = _pdf(["ข้าพเจ้า นายสมชาย", "ใจดี อายุ ๔๕ ปี"])
    [f] = [f for f in pii.scan_pii(_S(data))["findings"] if f["type"] == "person_name"]
    assert f["text"] == "นายสมชาย ใจดี"
    assert len(f["rects"]) == 2 and f["rects"][1]["y0"] > f["rects"][0]["y1"] - 1   # กรอบละบรรทัด


@pytest.mark.parametrize("text", ["คุณภาพ สินค้าดีเยี่ยม", "นายจ้าง ต้องจ่ายค่าจ้าง", "ประกาศ ณ วันที่ ๒๑ กันยายน พ.ศ. ๒๕๖๙",
                                  "พระมหากษัตริย์ ทรงพระกรุณา"])
def test_common_words_that_start_like_titles_are_not_names(text):
    assert [t for t in pii.find_in_text(text) if t[0] == "person_name"] == []


def _form_pdf() -> bytes:
    """แบบฟอร์มที่หัวข้อกับค่าอยู่คนละคอลัมน์ (คนละ block) — แบบใบส่งสินค้า"""
    doc = fitz.open()
    page = doc.new_page()
    for k, (label, value) in enumerate([("ชื่อลูกค้า :", "กิตติพัฒน์  ทองประเสริฐ"), ("เบอร์โทรศัพท์ :", "0891234567"),
                                        ("วันที่สั่งซื้อ :", "12/01/2568")]):
        y = 80 + 18 * k
        page.insert_text((50, y), label, fontsize=11, fontname="sarabun", fontfile=str(FONT))
        page.insert_text((170, y), value, fontsize=11, fontname="sarabun", fontfile=str(FONT))
    page.insert_text((50, 150), "ที่อยู่จัดส่ง : รหัสร้าน 01234 สาขา ทดสอบสุข เลขที่ 2 ซ.ทดสอบสุข แขวงสามเสนใน",
                     fontsize=11, fontname="sarabun", fontfile=str(FONT))
    page.insert_text((50, 168), "เขตพญาไท กรุงเทพฯ 10400", fontsize=11, fontname="sarabun", fontfile=str(FONT))
    data = doc.tobytes()
    doc.close()
    return data


def test_name_after_form_label_without_title_is_found():
    found = _types(_form_pdf())
    assert ("person_name", "กิตติพัฒน์ ทองประเสริฐ") in found
    assert ("phone", "0891234567") in found
    [addr] = [t for typ, t in found if typ == "address"]
    assert addr.startswith("เลขที่ 2") and "12/01/2568" not in addr      # วันที่ไม่ใช่บ้านเลขที่


@pytest.mark.parametrize("text, name", [
    ("ชื่อผู้รับ: สมหญิง ใจงาม โทร 0812345678", "สมหญิง ใจงาม"),
    ("ผู้ติดต่อ : วิชัย ศรีสุข", "วิชัย ศรีสุข"),
    ("ลงชื่อ ................................ ผู้รับเงิน\n(ประเสริฐ วงศ์ทอง)", "ประเสริฐ วงศ์ทอง"),
    ("Customer Name: John Smith", "John Smith"),
])
def test_names_after_labels_and_signatures(text, name):
    assert any(t == "person_name" and text[s:e].replace("\n", " ") == name for t, s, e in pii.find_in_text(text))


def test_name_without_title_or_label_is_only_a_guess():
    found = pii.find_in_text("ประชุมร่วมกับ วิชัย ศรีสุข และทีมงานฝ่ายบัญชี")
    assert [(t, "ประชุมร่วมกับ วิชัย ศรีสุข และทีมงานฝ่ายบัญชี"[s:e]) for t, s, e in found] == [("person_name_guess", "วิชัย ศรีสุข")]
    assert pii.PII_TYPES["person_name_guess"]["confidence"] == "low"     # หน้าจอไม่ติ๊กให้อัตโนมัติ
    assert [t for t in pii.find_in_text("ธนาคาร กรุงเทพ สาขาสีลม") if t[0].startswith("person")] == []


# ---------------------------------------------------------------- ช่องฟอร์ม / กล่องข้อความ / ส่วนอื่นของไฟล์
def _filled_form_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 60), "แบบฟอร์มสมัคร", fontsize=14, fontname="sarabun", fontfile=str(FONT))
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect = "idcard", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(50, 100, 300, 120)
    w.field_value = f"เลขบัตร {VALID_ID}"
    page.add_widget(w)
    note = page.add_text_annot((400, 100), "ติดต่อ 0812345678")
    note.update()
    doc.set_toc([[1, f"ผู้สมัคร {VALID_ID}", 1]])
    return doc.tobytes()


def test_scan_finds_pii_in_form_fields_and_notes():
    found = pii.scan_pii(_S(_filled_form_pdf()))["findings"]
    assert {(f["type"], f["text"]) for f in found} >= {("national_id", VALID_ID), ("phone", "0812345678")}


def test_redact_masks_fields_notes_and_bookmarks(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _filled_form_pdf())
    found = client.post(f"/pdf/{sid}/pii/scan", headers=h).json()["findings"]
    ids = [f["id"] for f in found if f["type"] in ("national_id", "phone")]
    assert len(ids) == 2
    r = client.post(f"/pdf/{sid}/pii/redact", headers=h, json={"ids": ids})
    assert r.status_code == 200 and r.json()["redacted"] == 2
    out = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    page = out[0]
    w = next(page.widgets())
    assert VALID_ID not in w.field_value and "เลขบัตร" in w.field_value  # ปิดเฉพาะเลข
    note = next(a for a in page.annots() if a.type[0] == fitz.PDF_ANNOT_TEXT)
    assert "0812345678" not in note.info["content"]
    assert VALID_ID not in out.get_toc()[0][1]  # ค่าเดียวกันในบุ๊กมาร์กถูกปิดด้วย
    assert "แบบฟอร์มสมัคร" in page.get_text()  # เนื้อหน้าใต้ช่องฟอร์มไม่ถูกลบ
    assert client.post(f"/pdf/{sid}/pii/scan", headers=h).json()["findings"] == []


def test_redact_app_text_box_redraws_appearance(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _pdf(["หัวเรื่อง"]))
    client.post(f"/annotation/{sid}", headers=h, json={"page_number": 0, "type": "freetext",
                "content": "โทร 0812345678", "rect": {"x0": 50, "y0": 200, "x1": 300, "y1": 230}})
    found = client.post(f"/pdf/{sid}/pii/scan", headers=h).json()["findings"]
    phone = next(f["id"] for f in found if f["type"] == "phone")  # เดิม: กล่องข้อความไม่ถูกตรวจ
    assert client.post(f"/pdf/{sid}/pii/redact", headers=h, json={"ids": [phone]}).status_code == 200
    out = fitz.open("pdf", client.get(f"/pdf/{sid}/download", headers=h).content)
    baked = fitz.open("pdf", out.tobytes())
    baked.bake(annots=True)
    text = baked[0].get_text().replace("\n", "")
    assert "0812345678" not in text and "โทร" in text
