"""PDF → Word: ขั้นแก้คำไทย (convert_service._fix_thai_in_docx) — คงรูปแบบ run และตรวจผลจาก Gemini ก่อนใช้"""
import json
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.text import WD_BREAK

from app.services import convert_service
from app.services.convert_service import accept_ai_text


@pytest.mark.parametrize("local, ai, expected", [
    ("ขอแสดงความนับถอ", "ขอแสดงความนับถือ", "ขอแสดงความนับถือ"),             # แก้สะกด → ใช้
    ("ใบกำกับภาษี INV-001 ยอด 1,500 บาท", "ใบกำกับภาษี INV-001 ยอด 1,500 บาท", "ใบกำกับภาษี INV-001 ยอด 1,500 บาท"),
    ("ใบกำกับภาษี INV-001 ยอด 1,500 บาท", "ใบกำกับภาษี INV-002 ยอด 1,500 บาท", None),   # ตัวเลขเปลี่ยน
    ("ใบกำกับภาษีเลขที่ 15", "Tax invoice number 15", None),                         # แปลภาษา
    ("รายงานผลการดำเนินงานประจำปี", "รายงาน", None),                                # ตัดเนื้อหา
    ("รายงานผลการดำเนินงานประจำปี", "นี่คือข้อความที่แก้แล้ว: รายงานผลการดำเนินงานประจำปี", None),  # ตอบปนคำอธิบาย
    ("สำนักงานใหญ่", "สำนักงานใหญ​่", "สำนักงานใหญ่"),                      # ตัด zero-width ทิ้ง
    ("ขอแสดงความนับถือ", "ขอแสดงความนบถอ", None),                                  # ทำให้แย่ลง (คำไม่รู้จักเพิ่ม)
    ("ข้อความ", ["ไม่ใช่สตริง"], None),
])
def test_accept_ai_text(local, ai, expected):
    assert accept_ai_text(local, ai) == expected


def _docx(tmp_path):
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("หมายเหตุ:").bold = True
    p.add_run(" ขอแสดงความนับถอ")          # สะกดผิด (ให้ AI แก้)
    p.add_run().add_break(WD_BREAK.LINE)
    p.add_run("ใบกำกับภาษี INV-001")
    doc.add_paragraph("รายงานผลการดำเนินงาน ส าหรับปี 2569")
    path = tmp_path / "t.docx"
    doc.save(path)
    return str(path)


@pytest.fixture
def ai(monkeypatch, client):
    """Gemini ปลอม: ฟังก์ชันที่ส่งเข้ามารับรายการข้อความ (หนึ่งย่อหน้าต่อสตริง) คืนผลที่ต้องการทดสอบ"""
    from tests.test_ai_quota import _make_plain_user

    state = SimpleNamespace(fn=None, prompts=[])
    monkeypatch.setattr(convert_service.settings, "GEMINI_API_KEY", "SYSTEM")
    monkeypatch.setattr(convert_service, "get_latest_flash_model", lambda key=None: "flash")

    def fake(key, model, prompt):
        state.prompts.append(prompt)
        texts = json.loads(prompt.split("Input JSON:\n", 1)[1])
        return json.dumps(state.fn(texts), ensure_ascii=False)

    monkeypatch.setattr(convert_service.gemini_client, "generate_text", fake)
    state.user = SimpleNamespace(id=_make_plain_user(), encrypted_gemini_key=None)
    return state


def _paras(path):
    return [(p.text.replace("​", ""), [(r.text.replace("​", ""), bool(r.bold)) for r in p.runs if r.text.strip()])
            for p in Document(path).paragraphs]


def test_ai_fix_is_applied_and_run_formatting_kept(ai, tmp_path):
    ai.fn = lambda texts: [t.replace("นับถอ", "นับถือ") for t in texts]
    path = _docx(tmp_path)
    assert convert_service._fix_thai_in_docx(path, ai.user) == "ai"
    # ส่งให้ AI หลังจัดรูปในเครื่องแล้ว (ส าหรับ → สำหรับ) และช่วงหลังขึ้นบรรทัดเป็นอีกบรรทัด
    assert json.loads(ai.prompts[0].split("Input JSON:\n", 1)[1]) == [
        "หมายเหตุ: ขอแสดงความนับถอ\nใบกำกับภาษี INV-001", "รายงานผลการดำเนินงาน สำหรับปี 2569"]
    (t1, runs1), (t2, _) = _paras(path)
    assert t1 == "หมายเหตุ: ขอแสดงความนับถือ\nใบกำกับภาษี INV-001"
    assert runs1 == [("หมายเหตุ:", True), (" ขอแสดงความนับถือ", False), ("ใบกำกับภาษี INV-001", False)]
    assert t2 == "รายงานผลการดำเนินงาน สำหรับปี 2569"


@pytest.mark.parametrize("bad", [
    lambda texts: ["Note: Yours sincerely\nTax invoice INV-001", "Annual report for 2569"],   # แปล
    lambda texts: [t.replace("INV-001", "INV-999").replace("2569", "2570") for t in texts],  # เปลี่ยนเลข
    lambda texts: [t.replace("\n", " ") for t in texts],                                     # จำนวนบรรทัดไม่ตรง
])
def test_rejected_ai_output_falls_back_to_local_normalization(ai, tmp_path, bad):
    ai.fn = bad
    path = _docx(tmp_path)
    convert_service._fix_thai_in_docx(path, ai.user)
    (t1, runs1), (t2, _) = _paras(path)
    assert t1 == "หมายเหตุ: ขอแสดงความนับถอ\nใบกำกับภาษี INV-001"   # คงข้อความเดิม (ไม่เชื่อ AI)
    assert t2 == "รายงานผลการดำเนินงาน สำหรับปี 2569"                 # แต่ยังจัดรูปในเครื่อง
    assert runs1[0] == ("หมายเหตุ:", True)


def test_ai_failure_uses_local_normalization(ai, tmp_path):
    def boom(texts):
        raise RuntimeError("quota")

    ai.fn = boom
    path = _docx(tmp_path)
    assert convert_service._fix_thai_in_docx(path, ai.user) == "fallback"
    assert _paras(path)[1][0] == "รายงานผลการดำเนินงาน สำหรับปี 2569"
