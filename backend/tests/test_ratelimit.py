"""จำกัดความถี่: ล็อก login หลังผิด 5 ครั้ง (ต่อบัญชี) · ผิดรวมต่อ IP · อีเมลลืมรหัส/ยืนยันซ้ำ · สมัครต่อ IP · เปลี่ยนรหัส"""
import pytest

from app.api import routes_auth
from app.core import ratelimit
from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.models.domain import User

IP = {"X-Real-IP": "203.0.113.7"}


def _user(email: str, password: str = "password123") -> None:
    with SessionLocal() as db:
        db.add(User(email=email, hashed_password=get_password_hash(password), is_verified=True, is_active=True,
                    plan_type="free", accepted_tos=True))
        db.commit()


def _login(client, email, password, headers=IP):
    return client.post("/auth/login", data={"username": email, "password": password}, headers=headers)


def test_account_locks_after_five_failures_even_with_right_password(client):
    _user("rl-lock@example.com")
    codes = [_login(client, "rl-lock@example.com", f"bad{i}").status_code for i in range(5)]
    assert codes == [401, 401, 401, 401, 429]
    r = _login(client, "RL-Lock@example.com", "password123")  # อีเมลตัวใหญ่ = บัญชีเดียวกัน
    assert r.status_code == 429
    assert "ล็อก" in r.json()["detail"] and "15 นาที" in r.json()["detail"]
    assert int(r.headers["retry-after"]) > 0
    ratelimit.reset("login-acct", "rl-lock@example.com")  # ครบเวลา → เข้าได้
    assert _login(client, "rl-lock@example.com", "password123").status_code == 200


def test_warns_when_few_attempts_left_and_success_resets(client):
    _user("rl-warn@example.com")
    for _ in range(2):
        assert "ลองได้อีก" not in _login(client, "rl-warn@example.com", "bad").json()["detail"]
    assert "ลองได้อีก 2 ครั้ง" in _login(client, "rl-warn@example.com", "bad").json()["detail"]
    assert _login(client, "rl-warn@example.com", "password123").status_code == 200
    assert ratelimit.count("login-acct", "rl-warn@example.com")[0] == 0


def test_ip_limit_across_accounts(client, monkeypatch):
    monkeypatch.setattr(routes_auth, "LOGIN_MAX_FAILS_PER_IP", 3)
    for i in range(3):
        assert _login(client, f"nobody{i}@example.com", "x").status_code == 401
    assert _login(client, "someone-else@example.com", "x").status_code == 429
    # IP อื่นไม่โดน
    assert _login(client, "someone-else@example.com", "x", {"X-Real-IP": "198.51.100.1"}).status_code == 401


def test_forgot_password_and_resend_limited_per_address(client):
    for _ in range(3):
        assert client.post("/auth/forgot-password", json={"email": "rl-mail@example.com"}, headers=IP).status_code == 200
    r = client.post("/auth/forgot-password", json={"email": "rl-mail@example.com"}, headers=IP)
    assert r.status_code == 429 and "บ่อยเกินไป" in r.json()["detail"]
    # นับรวมกับส่งอีเมลยืนยันซ้ำ (อีเมลเดียวกัน)
    assert client.post("/auth/resend-verification", json={"email": "rl-mail@example.com"}, headers=IP).status_code == 429
    assert client.post("/auth/forgot-password", json={"email": "other@example.com"}, headers=IP).status_code == 200


def test_register_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(routes_auth, "REGISTER_MAX_PER_IP", 2)
    for i in range(2):
        client.post("/auth/register", json={"email": f"rl-reg{i}@example.com", "password": "Password123!"}, headers=IP)
    r = client.post("/auth/register", json={"email": "rl-reg9@example.com", "password": "Password123!"}, headers=IP)
    assert r.status_code == 429


def test_change_password_counts_wrong_old_password(client, make_user):
    _, headers = make_user()
    for _ in range(5):
        r = client.put("/auth/change-password", headers=headers,
                       json={"old_password": "wrong", "new_password": "NewPassword123!"})
        assert r.status_code == 400
    r = client.put("/auth/change-password", headers=headers,
                   json={"old_password": "password123", "new_password": "NewPassword123!"})
    assert r.status_code == 429


@pytest.mark.parametrize("raw,expected", [("203.0.113.7", "203.0.113.7"), ("not-an-ip", ""), ("2001:db8::1", "2001:db8::1")])
def test_client_ip_parsing(raw, expected):
    from starlette.requests import Request

    req = Request({"type": "http", "headers": [(b"x-real-ip", raw.encode())], "client": None})
    assert ratelimit.client_ip(req) == expected


def test_redis_backend_shared_counter():
    fakeredis = pytest.importorskip("fakeredis")
    from app.core import redis_client

    r = fakeredis.FakeRedis()
    redis_client._redis_instance, redis_client._initialized = r, True
    try:
        assert ratelimit.hit("t", "a@example.com", 60) == 1
        assert ratelimit.hit("t", "A@example.com ", 60) == 2
        n, ttl = ratelimit.count("t", "a@example.com")
        assert n == 2 and 0 < ttl <= 60
        assert not any(b"a@example.com" in k for k in r.keys())  # ไม่เก็บอีเมลตรง ๆ
        ratelimit.reset("t", "a@example.com")
        assert ratelimit.count("t", "a@example.com")[0] == 0
    finally:
        redis_client.reset_for_testing()
