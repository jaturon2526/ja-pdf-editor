"""วัดผลกับไฟล์ PDF จริงใน test_pdf_files/ (ไม่อยู่ใน git — ข้ามเมื่อไม่มีโฟลเดอร์ เช่นใน CI)

ทุกคำใน test_pdf_files/expected.json ต้องหาเจอหลังจัดรูป และค้นหาเพื่อเซ็นเซอร์เจอ และไม่เหลือรูปแบบที่ผิดแน่ๆ
ตั้ง THAI_CORPUS_DIR เพื่อชี้ไปโฟลเดอร์อื่นได้
"""
import json
import os
from pathlib import Path

import pytest

from scripts.thai_eval import evaluate

CORPUS = Path(os.getenv("THAI_CORPUS_DIR", Path(__file__).resolve().parents[2] / "test_pdf_files"))
EXPECTED = CORPUS / "expected.json"

pytestmark = pytest.mark.skipif(not EXPECTED.exists(), reason="ไม่มีไฟล์ตัวอย่างจริง (test_pdf_files/expected.json)")


def _cases():
    if not EXPECTED.exists():
        return []
    return sorted(json.loads(EXPECTED.read_text("utf-8")).items())


@pytest.mark.parametrize("name, keywords", _cases())
def test_real_pdf_reads_correctly(name, keywords):
    r = evaluate(CORPUS / name, keywords)
    missing = [k for k, v in r["keywords"].items() if not v["normalized"]]
    assert not missing, f"{name}: หาไม่เจอหลังจัดรูป {missing}"
    not_redactable = [k for k, v in r["keywords"].items() if not v["redact"]]
    assert not not_redactable, f"{name}: ค้นหาเพื่อเซ็นเซอร์ไม่เจอ {not_redactable}"
    assert r["issues_after"] == 0, f"{name}: ยังมีรูปแบบผิด {r}"
    assert r["coverage_after"] >= r["coverage_before"]
