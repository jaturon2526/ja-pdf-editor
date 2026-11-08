"""google-genai: client แยกตาม API key (ไม่มี global state แบบ genai.configure เดิม)"""
from types import SimpleNamespace

import pytest

from app.services import gemini_client


class FakeModels:
    def __init__(self, key, calls, names):
        self.key, self.calls, self.names = key, calls, names

    def generate_content(self, model, contents):
        self.calls.append((self.key, model, contents))
        if isinstance(contents, str) and contents.startswith("You are a Thai text fixing tool"):
            import json
            texts = json.loads(contents.split("Input JSON:\n", 1)[1])
            return SimpleNamespace(text=json.dumps([t + "!" for t in texts], ensure_ascii=False))
        return SimpleNamespace(text=f"  text-from-{self.key}  ")

    def list(self):
        if self.names is None:
            raise RuntimeError("network down")
        return [SimpleNamespace(name=f"models/{n}") for n in self.names]


@pytest.fixture
def fake_genai(monkeypatch):
    calls = []
    state = {"names": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.0-flash-preview", "gemini-2.5-pro"]}

    class FakeClient:
        def __init__(self, api_key, http_options=None):
            self.api_key = api_key
            self.models = FakeModels(api_key, calls, state["names"])

    monkeypatch.setattr(gemini_client.genai, "Client", FakeClient)
    gemini_client.reset_for_testing()
    yield SimpleNamespace(calls=calls, state=state)
    gemini_client.reset_for_testing()


def test_client_cached_per_key(fake_genai):
    a1 = gemini_client.get_client("key-a")
    assert gemini_client.get_client("key-a") is a1
    assert gemini_client.get_client("key-b") is not a1
    with pytest.raises(gemini_client.GeminiNotConfigured):
        gemini_client.get_client(None)


def test_generate_text_uses_given_key(fake_genai):
    assert gemini_client.generate_text("user-1", "gemini-2.5-flash", "hi") == "text-from-user-1"
    assert gemini_client.generate_text("user-2", "gemini-2.5-flash", "hi") == "text-from-user-2"
    assert [c[0] for c in fake_genai.calls] == ["user-1", "user-2"]


def test_latest_flash_model_filters_and_falls_back(fake_genai):
    assert gemini_client.latest_flash_model("k") == "gemini-2.5-flash"
    gemini_client.reset_for_testing()
    fake_genai.state["names"] = None
    assert gemini_client.latest_flash_model("k") == gemini_client.DEFAULT_FLASH_MODEL


def _thai_docx(tmp_path):
    from docx import Document

    path = tmp_path / "t.docx"
    doc = Document()
    doc.add_paragraph("สวัสดีครับ")
    doc.save(path)
    return str(path)


@pytest.mark.parametrize("system_key, expected_key", [("SYSTEM-KEY", "SYSTEM-KEY"), (None, "PERSONAL-KEY")])
def test_docx_fix_uses_system_key_else_personal_key(client, fake_genai, monkeypatch, tmp_path, system_key, expected_key):
    from app.services import convert_service

    monkeypatch.setattr(convert_service.settings, "GEMINI_API_KEY", system_key)
    monkeypatch.setattr("app.core.crypto.decrypt_api_key", lambda enc, user: "PERSONAL-KEY")
    from tests.test_ai_quota import _make_plain_user

    user = SimpleNamespace(id=_make_plain_user(), encrypted_gemini_key="enc")

    status = convert_service._fix_thai_in_docx(_thai_docx(tmp_path), user)
    assert status == "ai"
    gen_calls = [c for c in fake_genai.calls if isinstance(c[2], str)]
    assert gen_calls and {c[0] for c in gen_calls} == {expected_key}


def test_ocr_with_personal_key_does_not_leak_to_system_calls(fake_genai, monkeypatch):
    """เดิม genai.configure(api_key=user_key) ตอน OCR ทำให้ key ของผู้ใช้ค้างเป็น key ของทั้ง process"""
    gemini_client.generate_text("PERSONAL-KEY", "gemini-2.5-flash", ["ocr", object()])
    gemini_client.generate_text("SYSTEM-KEY", "gemini-2.5-flash", "system job")
    assert fake_genai.calls[-1][0] == "SYSTEM-KEY"
