"""AI หลายค่าย (services/ai_client.py): Gemini / Claude / OpenAI-compatible — ค่าของระบบ, key ส่วนตัวที่เลือกค่ายได้,
การส่งคำขอ HTTP ของแต่ละค่าย, กัน URL ภายใน, และงานแปลง PDF→Word ใช้ค่ายที่ตั้งไว้"""
import io
import json

import pytest
from PIL import Image

from app.core.config import settings
from app.services import ai_client, gemini_client
from tests.test_ai_quota import _convert, _thai_pdf


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def http(monkeypatch):
    """จับคำขอ HTTP ที่ ai_client ส่ง (url, headers, body) และตอบตาม state['reply']"""
    state = {"calls": [], "reply": None, "errors": []}

    def fake_open(req, timeout=None):
        body = json.loads(req.data.decode())
        state["calls"].append({"url": req.full_url, "headers": {k.lower(): v for k, v in req.header_items()}, "body": body})
        if state["errors"]:
            raise state["errors"].pop(0)
        return _Resp(json.dumps(state["reply"](body) if callable(state["reply"]) else state["reply"]).encode())

    monkeypatch.setattr(ai_client._opener, "open", fake_open)
    return state


@pytest.fixture
def ai_settings(monkeypatch):
    def apply(**kw):
        defaults = {"AI_PROVIDER": "", "AI_API_KEY": "", "AI_MODEL": "", "AI_BASE_URL": "", "GEMINI_API_KEY": None,
                    "AI_USER_KEYS_ENABLED": True, "AI_PRIVATE_HOSTS": ""}
        for k, v in {**defaults, **kw}.items():
            monkeypatch.setattr(settings, k, v)
    return apply


def test_system_config_defaults_to_gemini_and_supports_others(ai_settings):
    ai_settings()
    assert ai_client.system_config() is None
    ai_settings(GEMINI_API_KEY="G-KEY")
    cfg = ai_client.system_config()
    assert cfg.provider == "gemini" and cfg.api_key == "G-KEY"
    ai_settings(AI_PROVIDER="claude", AI_API_KEY="sk-ant", GEMINI_API_KEY="G-KEY")
    cfg = ai_client.system_config()
    assert cfg.provider == "anthropic" and cfg.api_key == "sk-ant" and cfg.label == "Anthropic Claude"
    assert ai_client.resolve_model(cfg) == ai_client.DEFAULT_MODELS["anthropic"]
    # vLLM/Ollama ภายใน: ไม่มี key แต่มี base_url · openai ต้องระบุรุ่น
    ai_settings(AI_PROVIDER="openai", AI_BASE_URL="http://llm.corp.local:8000/v1")
    cfg = ai_client.system_config()
    assert cfg.provider == "openai" and cfg.api_key == ""
    with pytest.raises(ai_client.AINotConfigured):
        ai_client.resolve_model(cfg)


def test_anthropic_request_with_image(http):
    http["reply"] = {"content": [{"type": "text", "text": " สวัสดี "}]}
    cfg = ai_client.AIConfig("anthropic", "sk-ant-1", "claude-test")
    img = Image.new("RGB", (8, 8), "white")
    assert ai_client.generate(cfg, "อ่านข้อความ", img) == "สวัสดี"
    call = http["calls"][0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == "sk-ant-1" and call["headers"]["anthropic-version"]
    content = call["body"]["messages"][0]["content"]
    assert call["body"]["model"] == "claude-test"
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert content[1] == {"type": "text", "text": "อ่านข้อความ"}


def test_openai_compatible_request_and_max_tokens_retry(http):
    from urllib.error import HTTPError

    http["reply"] = {"choices": [{"message": {"content": "ok"}}]}
    err = HTTPError("u", 400, "bad", {}, io.BytesIO(json.dumps(
        {"error": {"message": "Unsupported parameter: 'max_tokens' is not supported with this model."}}).encode()))
    http["errors"].append(err)
    cfg = ai_client.AIConfig("openai", "sk-oa", "gpt-test", "https://myres.openai.azure.com/openai/v1/")
    assert ai_client.generate(cfg, "hello") == "ok"
    first, second = http["calls"]
    assert first["url"] == "https://myres.openai.azure.com/openai/v1/chat/completions"
    assert first["headers"]["authorization"] == "Bearer sk-oa" and first["headers"]["api-key"] == "sk-oa"
    assert "max_tokens" in first["body"] and "max_completion_tokens" in second["body"]
    assert second["body"]["messages"][0]["content"] == "hello"


def test_errors_are_friendly_and_rate_limits_detected(http):
    from urllib.error import HTTPError

    for code, expect in ((401, "API key ไม่ถูกต้อง"), (429, "จำกัดการใช้งาน"), (404, "ไม่พบรุ่น")):
        http["errors"].append(HTTPError("u", code, "x", {}, io.BytesIO(b'{"error":{"message":"m"}}')))
        with pytest.raises(ai_client.AIError) as exc:
            ai_client.generate(ai_client.AIConfig("anthropic", "k", "m"), "hi")
        assert expect in ai_client.friendly_error(exc.value)
    assert ai_client.is_rate_limited(ai_client.AIError("x", 529))


def test_personal_base_url_blocks_internal_hosts(ai_settings):
    ai_settings()
    with pytest.raises(ValueError):
        ai_client.validate_base_url("http://api.example.com/v1", personal=True)
    with pytest.raises(ValueError):
        ai_client.validate_base_url("https://127.0.0.1/v1", personal=True)
    with pytest.raises(ValueError):
        ai_client.validate_base_url("https://localhost:8000/v1", personal=True)
    ai_settings(AI_PRIVATE_HOSTS="llm.corp.local, localhost")
    assert ai_client.validate_base_url("http://localhost:8000/v1/", personal=True) == "http://localhost:8000/v1"
    # ของระบบ (ผู้ดูแลตั้งใน .env) ใช้ http ภายในได้
    assert ai_client.validate_base_url("http://10.0.0.5:8000/v1", personal=False)


def test_personal_key_api_with_provider(client, make_user, ai_settings, monkeypatch):
    ai_settings(AI_PROVIDER="anthropic", AI_API_KEY="sk-ant-system-123456")
    tested = []
    monkeypatch.setattr(ai_client, "test_config", lambda cfg: tested.append(cfg) or (cfg.model or "gemini-x"))
    _, h = make_user()
    r = client.post("/auth/api-key", headers=h, json={"api_key": "AIza-personal-key-1", "provider": "gemini"})
    assert r.status_code == 200, r.text
    q = client.get("/auth/ai-quota", headers=h).json()
    assert q["personal_provider"] == "gemini" and q["personal_key_preview"] == "AIza-p...ey-1"
    assert q["system_provider"] == "anthropic" and q["system_key_preview"] is None  # ไม่ใช่แอดมิน
    assert {p["value"] for p in q["providers"]} == {"gemini", "anthropic", "openai"}

    r = client.post("/auth/api-key", headers=h, json={"api_key": "k", "provider": "openai"})
    assert r.status_code == 400 and "model" in r.json()["detail"]
    r = client.post("/auth/api-key", headers=h, json={"api_key": "k", "provider": "openai", "model": "m",
                                                      "base_url": "https://127.0.0.1/v1"})
    assert r.status_code == 400 and "ภายใน" in r.json()["detail"]
    r = client.post("/auth/api-key", headers=h, json={"api_key": "sk-oa-dept-key", "provider": "openai", "model": "gpt-dept"})
    assert r.status_code == 200 and r.json()["model"] == "gpt-dept"
    assert tested[-1].provider == "openai" and tested[-1].source == "personal"
    q = client.get("/auth/ai-quota", headers=h).json()
    assert q["personal_provider"] == "openai" and q["personal_model"] == "gpt-dept"

    def failing(cfg):
        raise ai_client.AIError("HTTP 401", 401)
    monkeypatch.setattr(ai_client, "test_config", failing)
    r = client.post("/auth/api-key", headers=h, json={"api_key": "bad", "provider": "anthropic"})
    assert r.status_code == 400 and "API key ไม่ถูกต้อง" in r.json()["detail"]
    assert client.get("/auth/ai-quota", headers=h).json()["personal_provider"] == "openai"  # ไม่บันทึกทับ

    assert client.delete("/auth/api-key", headers=h).status_code == 200
    q = client.get("/auth/ai-quota", headers=h).json()
    assert q["personal_provider"] is None and q["personal_key_preview"] is None

    ai_settings(AI_USER_KEYS_ENABLED=False)
    assert client.post("/auth/api-key", headers=h, json={"api_key": "x", "provider": "gemini"}).status_code == 403


def test_conversion_uses_configured_system_provider(client, make_user, upload, ai_settings, monkeypatch):
    ai_settings(AI_PROVIDER="anthropic", AI_API_KEY="sk-ant-system", AI_MODEL="claude-test")
    monkeypatch.setattr(settings, "AI_SYSTEM_DAILY_LIMIT", 5)
    seen = []

    def fake_generate(cfg, prompt, image=None, *, model=None, max_tokens=None):
        seen.append((cfg.provider, cfg.source, model))
        texts = json.loads(prompt.split("Input JSON:\n", 1)[1])
        return json.dumps(texts, ensure_ascii=False)

    monkeypatch.setattr(ai_client, "generate", fake_generate)
    monkeypatch.setattr(gemini_client, "generate_text", lambda *a, **k: pytest.fail("ไม่ควรเรียก Gemini"))
    _, h = make_user()
    status = _convert(client, h, upload(h, _thai_pdf(), "thai.pdf"))
    assert status["status"] == "completed", status
    assert seen and seen[0] == ("anthropic", "system", "claude-test")


def test_no_ai_configured_disables_ai_features(client, make_user, upload, ai_settings, monkeypatch):
    """ไม่ได้ตั้ง AI เลย: /auth/ai-quota บอก ai_available=False (หน้าเว็บซ่อนกล่องโควต้า/ตัวเลือก AI) และงานแปลง
    ได้สถานะ "basic" (ไม่ใช่ "fallback" ที่หน้าเว็บแจ้งว่า AI ขัดข้อง) โดยไม่เรียก AI"""
    ai_settings()
    monkeypatch.setattr(ai_client, "generate", lambda *a, **k: pytest.fail("ไม่ควรเรียก AI"))
    _, h = make_user()
    q = client.get("/auth/ai-quota", headers=h).json()
    assert q["ai_available"] is False and q["ai_ocr"] is False and q["system_ai"] is False
    status = _convert(client, h, upload(h, _thai_pdf(), "thai.pdf"))
    assert status["status"] == "completed" and status["error_message"] == "basic", status

    # มี key ส่วนตัว → ใช้ AI ได้ (รวมอ่านข้อความด้วย AI) · ผู้ดูแลปิด key ส่วนตัว → กลับเป็นไม่มี AI
    monkeypatch.setattr(ai_client, "test_config", lambda cfg: cfg.model or "gemini-x")
    assert client.post("/auth/api-key", headers=h, json={"api_key": "AIza-personal-key-1", "provider": "gemini"}).status_code == 200
    q = client.get("/auth/ai-quota", headers=h).json()
    assert q["ai_available"] is True and q["ai_ocr"] is True
    ai_settings(AI_USER_KEYS_ENABLED=False)
    q = client.get("/auth/ai-quota", headers=h).json()
    assert q["ai_available"] is False and q["ai_ocr"] is False
    ai_settings(GEMINI_API_KEY="G-KEY", AI_USER_KEYS_ENABLED=False)
    q = client.get("/auth/ai-quota", headers=h).json()
    assert q["ai_available"] is True and q["ai_ocr"] is False


def test_scan_use_ai_ignored_without_ai(ai_settings, monkeypatch):
    from app.services import convert_service, scan_docx

    ai_settings()
    monkeypatch.setattr(scan_docx, "convert_scan_to_docx", lambda pdf, progress_callback=None: b"DOCX")
    monkeypatch.setattr(convert_service, "_fix_thai_in_docx", lambda *a, **k: pytest.fail("ไม่ควรเรียก AI"))
    assert convert_service.convert_scan_pdf_to_docx(b"%PDF", None, use_ai=True) == (b"DOCX", "scan")
