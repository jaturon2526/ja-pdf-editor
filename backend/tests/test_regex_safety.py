"""regex ที่ SonarQube เตือนว่า backtrack หนัก (S5852/S8786) — ผลเหมือนเดิม และข้อความยาวผิดปกติไม่ทำให้ช้า"""
import time

import pytest

from app.services.line_login_service import _EMAIL_RE as LINE_EMAIL_RE
from app.services.pdf2docx_fixes import _strip_style_suffix
from app.services.signing_service import _EMAIL_RE as SIGN_EMAIL_RE


@pytest.mark.parametrize("name,expected", [
    ("THSarabunNew-Bold", "THSarabunNew"),
    ("Arial,BoldItalic", "Arial"),
    ("Tahoma-ExtraBoldItalic", "Tahoma"),
    ("Angsana-PSMT", "Angsana"),
    ("Foo-Bold-Italic", "Foo-Bold"),
    ("Foo-Bar", "Foo-Bar"),
    ("Abc-boldx", "Abc-boldx"),
    ("Times", "Times"),
])
def test_strip_style_suffix(name, expected):
    assert _strip_style_suffix(name) == expected


@pytest.mark.parametrize("regex", [LINE_EMAIL_RE, SIGN_EMAIL_RE])
@pytest.mark.parametrize("email,ok", [
    ("a@b.co", True), ("first.last@mail.example.co.th", True),
    ("a@b", False), ("a@.b", False), ("a@b.", False), ("x y@b.c", False), ("a@b..c", False),
])
def test_email_regex(regex, email, ok):
    assert bool(regex.match(email)) is ok


def test_long_inputs_are_fast():
    start = time.perf_counter()
    SIGN_EMAIL_RE.match("a@" + "b." * 20000 + "!")
    _strip_style_suffix("x-" + "bold" * 20000 + "z")
    assert time.perf_counter() - start < 1.0
