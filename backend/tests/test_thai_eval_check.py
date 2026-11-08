"""เกณฑ์ --check ของ scripts/thai_eval (ด่านก่อน push image ใน scripts/ship.sh) — ไม่ต้องมีไฟล์ทดสอบจริง"""
from scripts.thai_eval import check_failures, main


def _r(name, issues=0, redact=None):
    return {"file": name, "issues_after": issues,
            "keywords": {k: {"redact": v} for k, v in (redact or {}).items()}}


def test_pass_when_clean():
    assert check_failures([_r("a.pdf", 0, {"คำขอ": True}), _r("b.pdf")]) == []


def test_fail_on_issues_and_missing_keyword():
    out = check_failures([_r("a.pdf", 2, {"คำขอ": True}), _r("b.pdf", 0, {"สำนักงาน": False})])
    assert len(out) == 2
    assert "a.pdf" in out[0] and "2" in out[0]
    assert "b.pdf" in out[1] and "สำนักงาน" in out[1]


def test_check_fails_on_empty_folder(tmp_path, capsys):
    assert main([str(tmp_path), "--check"]) == 1
    assert "CHECK FAIL" in capsys.readouterr().out
