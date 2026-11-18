"""SEC-08: URL ของ AI ที่ผู้ใช้ตั้งเอง — ตรวจ IP แล้วเชื่อมต่อ IP นั้นตรง ๆ (DNS rebinding ใช้ไม่ได้)"""
import socket

import pytest

from app.core.config import settings
from app.services import ai_client

PUBLIC = "93.184.216.34"


def _addrinfo(*ips):
    return lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]


class _FakeSock:
    connected = []

    def __init__(self, *a, **k):
        pass

    def settimeout(self, t):
        pass

    def connect(self, addr):
        _FakeSock.connected.append(addr)

    def close(self):
        pass


def test_pinned_connection_uses_checked_ip_and_resolves_once(monkeypatch):
    calls = []
    answers = iter([[PUBLIC], ["127.0.0.1"]])  # ครั้งที่สองชี้เข้าเครื่องตัวเอง (rebinding)

    def resolve(host, port, *a, **k):
        calls.append(host)
        return _addrinfo(*next(answers))(host, port)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "socket", _FakeSock)
    _FakeSock.connected = []
    conn = ai_client._PinnedHTTPSConnection("api.example.com", 443, timeout=5,
                                            context=ai_client.ssl.create_default_context())
    wrapped = {}
    monkeypatch.setattr(conn._context, "wrap_socket", lambda sock, server_hostname: wrapped.setdefault("h", server_hostname))
    conn.connect()
    assert calls == ["api.example.com"]
    assert _FakeSock.connected == [(PUBLIC, 443)]
    assert wrapped["h"] == "api.example.com"  # TLS ยังตรวจใบรับรองกับชื่อโฮสต์


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"])
def test_pinned_connection_refuses_internal_addresses(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _addrinfo(ip))
    conn = ai_client._PinnedHTTPSConnection("evil.example.com", 443, context=ai_client.ssl.create_default_context())
    with pytest.raises(ai_client._BlockedAddress):
        conn.connect()


def test_personal_url_requests_are_pinned_but_system_and_allowed_hosts_are_not(monkeypatch):
    seen = []
    monkeypatch.setattr(settings, "AI_PRIVATE_HOSTS", "llm.corp.local")
    monkeypatch.setattr(ai_client, "validate_base_url", lambda url, personal: url)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"choices": [{"message": {"content": "OK"}}]}'

    monkeypatch.setattr(ai_client._opener, "open", lambda req, timeout=None: seen.append(req.pin_public) or _Resp())
    for source, url in [("personal", "https://api.example.com/v1"), ("system", "http://10.0.0.9/v1"),
                        ("personal", "https://llm.corp.local/v1")]:
        ai_client.generate(ai_client.AIConfig("openai", "k", "m", url, source), "hi")
    assert seen == [True, False, False]
