"""เทสต์โหมดวาดใหม่เป็น PDF Object (scan_pdf_rebuild + POST /pdf/scan output_mode=rebuild)"""
import io
import json
import shutil
import subprocess
from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services import ai_client, ai_usage, scan_pdf_rebuild
from app.services.scan_docx.layout import PageLayout, Paragraph, Picture, Run, Tab, Table, TableCell

FONT = str(Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts" / "Sarabun-Regular.ttf")


def _has_thai_tesseract() -> bool:
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return "tha" in out.split()


def _visible_text_chars(page: fitz.Page) -> int:
    """นับจำนวนอักขระที่มองเห็นจริง (ไม่นับชั้น OCR ล่องหน render mode 3)"""
    return sum(len(b.get("chars", ())) for b in page.get_texttrace() if b.get("type") != 3)


def _sample_scan_png_with_table() -> bytes:
    """ภาพสแกนสมมติที่มีทั้งหัวข้อภาษาไทยและตาราง 2x2"""
    img = Image.new("L", (1240, 1754), 255)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 46)
    d.text((120, 120), "ใบเสนอราคา", font=font, fill=0)
    # วาดตาราง 2 แถว 2 คอลัมน์
    d.rectangle([120, 260, 1080, 520], outline=0, width=3)
    d.line([120, 390, 1080, 390], fill=0, width=3)
    d.line([600, 260, 600, 520], fill=0, width=3)
    d.text((160, 300), "รายการ", font=font, fill=0)
    d.text((640, 300), "จำนวนเงิน", font=font, fill=0)
    d.text((160, 430), "ค่าบริการ", font=font, fill=0)
    d.text((640, 430), "1,500", font=font, fill=0)
    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(200, 200))
    return buf.getvalue()


def test_render_layouts_to_pdf_draws_visible_thai_text_and_detectable_table():
    """วาด PageLayout (ย่อหน้า + แท็บจุดไข่ปลา + ตาราง + รูปย่อย) → PDF Object ที่มองเห็นและแก้ตารางได้"""
    color = Image.new("RGB", (600, 800), (255, 255, 255))
    d = ImageDraw.Draw(color)
    d.rectangle([20, 20, 120, 90], fill=(20, 90, 180))

    pl = PageLayout(
        width=595.0,
        height=842.0,
        margins=(54.0, 54.0, 54.0, 54.0),
        blocks=[
            Picture(box=(20, 20, 120, 90), kind="graphic", x=54.0, y=54.0, w=72.0, h=50.0, top=54.0, bottom=104.0),
            Paragraph(
                runs=[Run("ใบเสนอราคา", bold=True, size=18.0)],
                align="center",
                top=120.0,
                bottom=144.0,
            ),
            Paragraph(
                runs=[Run("หัวข้อที่ 1\t100", bold=False, size=12.0)],
                tabs=[Tab(pos=460.0, align="right", leader="dot")],
                top=160.0,
                bottom=178.0,
            ),
            Table(
                col_widths=[240.0, 220.0],
                row_heights=[32.0, 32.0],
                left=0.0,
                top=210.0,
                bottom=274.0,
                cells=[
                    TableCell(0, 0, 1, 1, [Paragraph([Run("รายการ", bold=True, size=12.0, color="FFFFFF")])], shade="1E293B"),
                    TableCell(0, 1, 1, 1, [Paragraph([Run("จำนวนเงิน", bold=True, size=12.0, color="FFFFFF")], align="right")], shade="1E293B"),
                    TableCell(1, 0, 1, 1, [Paragraph([Run("ค่าบริการตรวจสอบเอกสาร", size=11.0)])]),
                    TableCell(1, 1, 1, 1, [Paragraph([Run("1,500 บาท", size=11.0)], align="right")]),
                ],
            ),
        ],
    )

    pdf_bytes = scan_pdf_rebuild.render_layouts_to_pdf([(pl, color)], title="TestRebuild")
    with fitz.open("pdf", pdf_bytes) as doc:
        assert doc.page_count == 1
        assert doc.metadata["creator"] == "JA PDF Editor Scan (Rebuild)"
        page = doc[0]
        assert _visible_text_chars(page) > 20
        text = page.get_text()
        assert "ใบเสนอราคา" in text
        assert "รายการ" in text
        assert "1,500" in text
        # เส้นตารางเป็นเวกเตอร์จริง → PyMuPDF find_tables() ต้องตรวจพบตาราง
        tables = page.find_tables()
        assert len(tables.tables) >= 1
        # รูปภาพย่อยถูกตัดแยกมาวาง (ไม่ใช่ภาพเต็มหน้า)
        imgs = page.get_image_info()
        assert len(imgs) == 1
        r = fitz.Rect(imgs[0]["bbox"])
        assert r.width < page.rect.width * 0.5


def test_refine_thai_layouts_local_and_ai_with_safety_guard(monkeypatch):
    """ตรวจคำไทยในเครื่องทำงานเสมอ และเมื่อเปิด AI ต้องแก้คำไทยโดยคงแท็บและปฏิเสธคำตอบที่เปลี่ยนตัวเลข"""
    color = Image.new("RGB", (200, 200), (255, 255, 255))
    p1 = Paragraph(runs=[Run("จ าเป็น\t100")])  # สระอำแตก → local normalize แก้เป็น จำเป็น
    p2 = Paragraph(runs=[Run("สำนักงาณ เลขที่ 2569")])
    pl = PageLayout(width=595.0, height=842.0, margins=(54.0, 54.0, 54.0, 54.0), blocks=[p1, p2])

    # 1) ไม่เปิด AI → local normalize ทำงาน และคืน "local"
    status_local = scan_pdf_rebuild._refine_thai_layouts([(pl, color)], user=None, use_ai=False)
    assert status_local == "local"
    assert p1.runs[0].text == "จำเป็น\t100"

    # 2) เปิด AI (mock system_config + generate + ai_usage) → แก้คำไทยได้และคงแท็บ + ตัวเลข
    cfg = ai_client.AIConfig(provider="gemini", api_key="dummy-key", model="gemini-test", source="system")
    monkeypatch.setattr(ai_client, "personal_config", lambda _u: None)
    monkeypatch.setattr(ai_client, "system_config", lambda: cfg)
    monkeypatch.setattr(ai_client, "resolve_model", lambda _c: "gemini-test")
    monkeypatch.setattr(ai_usage, "try_reserve", lambda _uid, _kind, _limit: True)
    monkeypatch.setattr(ai_usage, "add", lambda _uid, _kind, _delta: None)
    monkeypatch.setattr(
        ai_client,
        "generate",
        lambda _cfg, _prompt, model=None: json.dumps([
            "จำเป็น\n100",
            "สำนักงาน เลขที่ 2569",
        ], ensure_ascii=False),
    )

    class _DummyUser:
        id = 999001

    status_ai = scan_pdf_rebuild._refine_thai_layouts([(pl, color)], user=_DummyUser(), use_ai=True)
    assert status_ai == "ai"
    assert p1.runs[0].text == "จำเป็น\t100"
    assert p2.runs[0].text == "สำนักงาน เลขที่ 2569"


def test_scan_api_rejects_invalid_output_mode(client, make_user):
    _, headers = make_user()
    img = _sample_scan_png_with_table()
    r = client.post(
        "/pdf/scan",
        headers=headers,
        data={"filename": "BadMode", "output_mode": "unknown"},
        files=[("pages", ("p1.png", img, "image/png"))],
    )
    assert r.status_code == 400
    assert "รูปแบบผลลัพธ์" in r.json()["detail"]


@pytest.mark.skipif(not _has_thai_tesseract(), reason="ไม่มี tesseract ภาษาไทย (CI ติดตั้งให้)")
def test_scan_api_rebuild_mode_end_to_end(client, make_user):
    """POST /pdf/scan ด้วย output_mode=rebuild → ได้ PDF ที่มีข้อความจริง (ไม่ล่องหน) และคืน output_mode/ai_status"""
    _, headers = make_user()
    img = _sample_scan_png_with_table()
    r = client.post(
        "/pdf/scan",
        headers=headers,
        data={"filename": "ScanRebuild", "output_mode": "rebuild", "use_ai": "false"},
        files=[("pages", ("p1.png", img, "image/png"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output_mode"] == "rebuild"

    st = client.get(f"/pdf/scan/status/{body['task_id']}", headers=headers).json()
    assert st["status"] == "completed", st
    assert st["output_mode"] == "rebuild"
    assert st["ai_status"] == "local"
    assert st["file"]["filename"] == "ScanRebuild.pdf"

    dl = client.get(f"/pdf/files/{st['file']['id']}/download", headers=headers)
    assert dl.status_code == 200
    with fitz.open("pdf", dl.content) as doc:
        assert doc.page_count == 1
        assert doc.metadata["creator"] == "JA PDF Editor Scan (Rebuild)"
        page = doc[0]
        assert _visible_text_chars(page) > 5
        assert page.search_for("ใบเสนอราคา") or page.search_for("รายการ")
