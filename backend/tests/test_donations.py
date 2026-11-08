"""รับบริจาค PromptPay: QR ตรงมาตรฐาน, แจ้งโอน → แอดมินอนุมัติ/ปฏิเสธ → สิทธิ์ + กระดาน, แพ็กเกจหมดอายุ"""
import datetime as dt
import io

import pytest
from PIL import Image

from app.db.database import SessionLocal
from app.models.domain import Donation, Notification, User
from app.services import donation_service, promptpay

PP = "0812345678"  # เลขตัวอย่าง (ไม่ใช่เลขจริงของใคร)


# ---- QR: เทียบกับไลบรารี promptpay-qr (npm) ที่แอปธนาคารใช้อ่านได้
@pytest.mark.parametrize("pid,amount,expected", [
    ("0812345678", 100, "00020101021229370016A000000677010111011300668123456785802TH53037645406100.006304BB8A"),
    ("081-234-5678", None, "00020101021129370016A000000677010111011300668123456785802TH530376463045D82"),
    ("1234567890123", 4.22, "00020101021229370016A000000677010111021312345678901235802TH530376454044.226304B731"),
    ("004999000288505", 50, "00020101021229390016A00000067701011103150049990002885055802TH5303764540550.0063047001"),
])
def test_promptpay_payload_matches_reference(pid, amount, expected):
    assert promptpay.payload(pid, amount) == expected


def test_promptpay_rejects_bad_ids_and_masks():
    with pytest.raises(promptpay.PromptPayError):
        promptpay.normalize_id("12345")
    assert promptpay.mask_id("0812345678") == "081-xxx-5678"
    assert promptpay.mask_id("1234567890123").endswith("0123") and "x" in promptpay.mask_id("1234567890123")
    assert promptpay.normalize_id("+66 81 234 5678") == ("phone", "0812345678")


# ---- helpers
def _admin(make_user):
    uid, headers = make_user("free")
    with SessionLocal() as db:
        db.get(User, uid).is_admin = True
        db.commit()
    return uid, headers


def _enable(client, headers, **extra):
    body = {"enabled": True, "promptpay_id": PP, "receiver_name": "ผู้พัฒนา JA PDF",
            "tiers": [{"min_amount": 50, "plan": "pro", "days": 30}, {"min_amount": 500, "plan": "premium", "days": 365}]}
    body.update(extra)
    r = client.put("/admin/donations/config", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _report(client, headers, amount="100", **form):
    data = {"amount": amount, "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat(), **form}
    return client.post("/donations", headers=headers, data=data, files=form.pop("files", None))


def _slip_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), "white").save(buf, "PNG")
    return buf.getvalue()


def test_disabled_by_default_and_cannot_enable_without_id(client, make_user):
    _, admin = _admin(make_user)
    client.put("/admin/donations/config", headers=admin, json={"enabled": False, "promptpay_id": ""})
    assert client.get("/donations/info").json()["enabled"] is False
    assert client.get("/donations/qr.svg").status_code == 400
    r = client.put("/admin/donations/config", headers=admin, json={"enabled": True, "promptpay_id": ""})
    assert r.status_code == 400
    r = client.put("/admin/donations/config", headers=admin, json={"enabled": True, "promptpay_id": "12"})
    assert r.status_code == 400


def test_public_info_hides_full_number_and_qr_is_svg(client, make_user):
    _, admin = _admin(make_user)
    _enable(client, admin)
    info = client.get("/donations/info").json()
    assert info["enabled"] and info["promptpay_masked"] == "081-xxx-5678"
    assert PP not in str(info)
    assert [t["plan"] for t in info["tiers"]] == ["pro", "premium"]
    assert info["tiers"][0]["max_storage_mb"] > info["free_plan"]["max_storage_mb"]  # สิทธิ์ต้องได้พื้นที่เพิ่มจริง
    r = client.get("/donations/qr.svg?amount=150")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and "<svg" in r.text
    assert client.get("/donations/qr.svg?amount=abc").status_code == 400
    # เฉพาะแอดมินดู/แก้ค่าตั้งได้
    _, user = make_user("free")
    assert client.get("/admin/donations/config", headers=user).status_code == 403


def test_report_approve_grants_plan_and_shows_on_board(client, make_user):
    _, admin = _admin(make_user)
    _enable(client, admin)
    uid, user = make_user("free")
    r = client.post("/donations", headers=user, data={
        "amount": "120", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "display_name": "คุณใจดี ทดสอบ", "message": "เป็นกำลังใจให้ครับ", "show_on_board": "true",
    }, files={"slip": ("slip.png", _slip_png(), "image/png")})
    assert r.status_code == 200, r.text
    did = r.json()["id"]
    pending = client.get("/admin/donations", headers=admin).json()
    item = next(i for i in pending["items"] if i["id"] == did)
    assert item["has_slip"] and item["suggested"] == {"min_amount": 50, "plan": "pro", "days": 30}
    slip = client.get(f"/admin/donations/{did}/slip", headers=admin)
    assert slip.status_code == 200 and slip.headers["content-type"] == "image/jpeg"
    assert client.get(f"/admin/donations/{did}/slip", headers=user).status_code == 403

    r = client.post(f"/admin/donations/{did}/approve", headers=admin, json={})
    assert r.status_code == 200 and r.json()["granted_plan"] == "pro" and r.json()["granted_days"] == 30
    assert r.json()["has_slip"] is False  # ลบสลิปทันทีที่ตรวจเสร็จ
    with SessionLocal() as db:
        u = db.get(User, uid)
        assert u.plan_type == "pro" and u.expire_date is not None
        assert db.query(Notification).filter_by(user_id=uid, kind="donation_approved").count() == 1
    assert client.post(f"/admin/donations/{did}/approve", headers=admin, json={}).status_code == 400

    names = [b["name"] for b in client.get("/donations/board").json()["items"]]
    assert "คุณใจดี ทดสอบ" in names
    board_item = next(b for b in client.get("/donations/board").json()["items"] if b["name"] == "คุณใจดี ทดสอบ")
    assert "amount" not in board_item and "email" not in board_item

    # แจ้งโอนอีกครั้งด้วยแพ็กเกจเดิม → ต่อวันหมดอายุ ไม่เริ่มนับใหม่
    with SessionLocal() as db:
        first_expire = db.get(User, uid).expire_date
    did2 = _report(client, user, "60").json()["id"]
    client.post(f"/admin/donations/{did2}/approve", headers=admin, json={})
    with SessionLocal() as db:
        assert (db.get(User, uid).expire_date - first_expire).days == 30

    # แอดมินซ่อนจากกระดานได้
    client.put(f"/admin/donations/{did}/board", headers=admin, json={"show_on_board": False})
    assert "คุณใจดี ทดสอบ" not in [b["name"] for b in client.get("/donations/board").json()["items"]]


def test_anonymous_donor_and_reject(client, make_user):
    _, admin = _admin(make_user)
    _enable(client, admin)
    uid, user = make_user("free")
    did = _report(client, user, "999", display_name="ชื่อจริงที่ไม่อยากเปิด", anonymous="true").json()["id"]
    client.post(f"/admin/donations/{did}/approve", headers=admin, json={"plan": "none"})
    items = client.get("/donations/board").json()["items"]
    assert "ชื่อจริงที่ไม่อยากเปิด" not in str(items)
    assert any(b["anonymous"] and b["name"] == donation_service.ANONYMOUS_NAME for b in items)
    with SessionLocal() as db:
        assert db.get(User, uid).plan_type == "free"  # plan "none" = ไม่ให้สิทธิ์

    did = _report(client, user, "77").json()["id"]
    r = client.post(f"/admin/donations/{did}/reject", headers=admin, json={"note": "ไม่พบยอดเข้า"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    mine = client.get("/donations/mine", headers=user).json()["items"]
    assert {d["status"] for d in mine} >= {"approved", "rejected"}


def test_report_validation_and_rate_limit(client, make_user):
    _, admin = _admin(make_user)
    _enable(client, admin)
    _, user = make_user("free")
    assert _report(client, user, "0").status_code == 400
    assert _report(client, user, "200000").status_code == 400
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)).isoformat()
    assert client.post("/donations", headers=user, data={"amount": "100", "transferred_at": old}).status_code == 400
    r = client.post("/donations", headers=user, data={"amount": "100", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    files={"slip": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 400
    for _ in range(5):
        assert _report(client, user, "10").status_code == 200
    assert _report(client, user, "10").status_code == 429
    assert client.post("/donations", data={"amount": "1", "transferred_at": old}).status_code == 401


def test_higher_plan_is_not_downgraded_and_expired_plan_reverts(client, make_user):
    _, admin = _admin(make_user)
    _enable(client, admin)
    uid, user = make_user("premium")  # แอดมินให้ premium ถาวร (expire_date = None)
    did = _report(client, user, "60").json()["id"]
    client.post(f"/admin/donations/{did}/approve", headers=admin, json={})
    with SessionLocal() as db:
        u = db.get(User, uid)
        assert u.plan_type == "premium" and u.expire_date is None

        u.expire_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        db.commit()
        assert donation_service.effective_plan(u) == "free"
        assert donation_service.expire_plans(db) >= 1
        db.refresh(u)
        assert u.plan_type == "free" and u.expire_date is None
        assert db.query(Notification).filter_by(user_id=uid, kind="plan_expired").count() == 1


def test_storage_quota_uses_effective_plan(client, make_user):
    from app.api.pdf.files import _storage_limit_bytes

    uid, _ = make_user("premium")
    with SessionLocal() as db:
        u = db.get(User, uid)
        u.expire_date = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        db.commit()
        free_user = User(email="quota-free@example.com", hashed_password="x", plan_type="free")
        assert _storage_limit_bytes(db, u) == _storage_limit_bytes(db, free_user)
    with SessionLocal() as db:
        db.query(Donation).delete()
        db.commit()


def test_deleting_account_removes_name_and_slip_but_keeps_amount(client, make_user):
    _, admin = _admin(make_user)
    _enable(client, admin)
    uid, user = make_user("free")
    approved = _report(client, user, "100", display_name="ชื่อที่ต้องหาย", message="ข้อความที่ต้องหาย").json()["id"]
    client.post(f"/admin/donations/{approved}/approve", headers=admin, json={})
    r = client.post("/donations", headers=user, data={"amount": "50", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    files={"slip": ("s.png", _slip_png(), "image/png")})
    pending = r.json()["id"]
    with SessionLocal() as db:
        slip = donation_service.slip_path(db.get(Donation, pending))
        assert slip and slip.exists()
    with SessionLocal() as db:
        email = db.get(User, uid).email
    r = client.post("/auth/account/delete", headers=user, json={"confirm_email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        a, p = db.get(Donation, approved), db.get(Donation, pending)
        assert a.user_id is None and a.display_name is None and a.message is None and a.amount_satang == 10000
        assert p.status == "rejected" and p.slip_path is None
    assert not slip.exists()
    assert "ชื่อที่ต้องหาย" not in str(client.get("/donations/board").json())


# ---------------------------------------------------------------- ตรวจสลิป
from app.services import slip_verify  # noqa: E402


def _slip_payload(ref="015312101530BPM04512") -> str:
    def tlv(t, v):
        return f"{t}{len(v):02d}{v}"
    body = tlv("00", tlv("00", "000001") + tlv("01", "004") + tlv("02", ref)) + tlv("51", "TH") + "9104"
    return body + promptpay.crc16(body)


def _slip_image(payload: str) -> bytes:
    import segno

    qr = io.BytesIO()
    segno.make(payload, error="m", micro=False).save(qr, kind="png", scale=4, border=4)
    slip = Image.new("RGB", (420, 640), "white")
    with Image.open(qr) as q:
        slip.paste(q.convert("RGB"), (240, 440))
    out = io.BytesIO()
    slip.save(out, "PNG")
    return out.getvalue()


def test_slip_payload_parsing_and_masked_match():
    p = _slip_payload()
    assert slip_verify.parse_slip_payload(p).trans_ref == "015312101530BPM04512"
    assert slip_verify.parse_slip_payload(p[:-1] + ("0" if p[-1] != "0" else "1")) is None  # CRC ผิด
    assert slip_verify.parse_slip_payload(promptpay.payload("0812345678", 10)) is None      # QR รับเงิน ไม่ใช่สลิป
    assert slip_verify.read_slip_qr(_slip_image(p)).bank_code == "004"
    assert slip_verify.read_slip_qr(_slip_png()) is None
    assert slip_verify.masked_match("xxx-xxx-5678", "0812345678")
    assert not slip_verify.masked_match("xxx-xxx-5679", "0812345678")
    assert not slip_verify.masked_match("xxx-xxx-xx78", "0812345678")  # เปิดน้อยกว่า 4 หลัก
    assert slip_verify.masked_match("xxx-x-x2345-x", "123-4-52345-6")          # เลขบัญชีธนาคาร (ตำแหน่งตรง)
    assert not slip_verify.masked_match("xxx-x-x5234-x", "123-4-52345-6")      # เลขเดียวกันแต่เลื่อนตำแหน่ง


def _easyslip_ok(amount=120.0, account="xxx-xxx-5678", date=None):
    date = date or dt.datetime.now(dt.timezone.utc).isoformat()
    return 200, {"status": 200, "data": {
        "transRef": "015312101530BPM04512", "date": date, "amount": {"amount": amount},
        "sender": {"bank": {"id": "004"}, "account": {"name": {"th": "นาย ทดสอบ ใ"}}},
        "receiver": {"bank": {"id": "014"}, "account": {"name": {"th": "นาย ผู้พัฒนา ท"}, "proxy": {"type": "MSISDN", "account": account}}},
    }}


def test_duplicate_slip_is_rejected_without_any_service(client, make_user):
    _, admin = _admin(make_user)
    _enable(client, admin)
    _, user = make_user("free")
    img = _slip_image(_slip_payload("DUPREF0001"))
    r = client.post("/donations", headers=user, data={"amount": "100", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    files={"slip": ("s.png", img, "image/png")})
    assert r.status_code == 200 and r.json()["verify_status"] is None
    item = next(i for i in client.get("/admin/donations", headers=admin).json()["items"] if i["id"] == r.json()["id"])
    assert item["slip_ref"] == "DUPREF0001" and item["slip_bank"] == "004" and item["can_verify"]
    r2 = client.post("/donations", headers=user, data={"amount": "100", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                     files={"slip": ("s.png", img, "image/png")})
    assert r2.status_code == 400 and "แจ้งไปแล้ว" in r2.json()["detail"]
    # สลิปที่อ่าน QR ไม่ได้ → แจ้งได้ แต่บอกแอดมินว่าอ่านไม่ได้
    r3 = client.post("/donations", headers=user, data={"amount": "100", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                     files={"slip": ("s.png", _slip_png(), "image/png")})
    assert r3.json()["verify_status"] == "unreadable"


def test_verified_slip_is_auto_approved_with_real_amount(client, make_user, monkeypatch):
    calls = []
    monkeypatch.setattr(slip_verify, "call_easyslip", lambda payload, key: (calls.append((payload, key)) or _easyslip_ok(amount=150)))
    _, admin = _admin(make_user)
    r = client.put("/admin/donations/config", headers=admin, json={"enabled": True, "promptpay_id": PP, "receiver_name": "ผู้พัฒนา",
                   "tiers": [{"min_amount": 50, "plan": "pro", "days": 30}], "verify_provider": "easyslip", "auto_approve": True})
    assert r.status_code == 400  # ยังไม่มี key
    cfg = _enable(client, admin, verify_provider="easyslip", verify_key="test-key-123", auto_approve=True)
    assert cfg["verify_key_set"] and "verify_key" not in cfg and "test-key-123" not in str(cfg)
    assert _enable(client, admin, verify_provider="easyslip", auto_approve=True)["verify_key_set"]  # ไม่ส่ง key = คงเดิม
    uid, user = make_user("free")
    r = client.post("/donations", headers=user, data={"amount": "100", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    files={"slip": ("s.png", _slip_image(_slip_payload("AUTOREF001")), "image/png")})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "approved" and body["verify_status"] == "verified"
    assert body["amount"] == 150 and body["granted_plan"] == "pro"
    assert calls and calls[0][1] == "test-key-123" and "AUTOREF001" in calls[0][0]
    with SessionLocal() as db:
        assert db.get(User, uid).plan_type == "pro"
        assert db.query(Notification).filter_by(kind="donation_new").filter(Notification.title.contains("150")).count() == 0


@pytest.mark.parametrize("response,status,problem", [
    (_easyslip_ok(amount=20), "mismatch", "น้อยกว่าที่แจ้ง"),
    (_easyslip_ok(account="xxx-xxx-9999"), "mismatch", "ผู้รับเงิน"),
    ((404, {"message": "slip_pending"}), "retry", "ลองตรวจอีกครั้ง"),
    ((400, {"message": "duplicate_slip", "data": {}}), "mismatch", "ใช้ซ้ำ"),
    ((403, {"message": "quota_exceeded"}), "error", "โควต้า"),
])
def test_failed_verification_stays_pending_for_admin(client, make_user, monkeypatch, response, status, problem):
    monkeypatch.setattr(slip_verify, "call_easyslip", lambda payload, key: response)
    _, admin = _admin(make_user)
    _enable(client, admin, verify_provider="easyslip", verify_key="k", auto_approve=True)
    _, user = make_user("free")
    ref = f"FAIL{status}{len(problem)}{abs(hash(problem)) % 10000}"
    r = client.post("/donations", headers=user, data={"amount": "100", "transferred_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    files={"slip": ("s.png", _slip_image(_slip_payload(ref)), "image/png")})
    assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["verify_status"] == status
    item = next(i for i in client.get("/admin/donations", headers=admin).json()["items"] if i["id"] == r.json()["id"])
    assert any(problem in p for p in item["verify_detail"]["problems"])
    # แอดมินกดตรวจอีกครั้งได้ เมื่อบริการตอบผ่าน → อนุมัติอัตโนมัติ
    monkeypatch.setattr(slip_verify, "call_easyslip", lambda payload, key: _easyslip_ok(amount=100))
    again = client.post(f"/admin/donations/{r.json()['id']}/verify", headers=admin)
    assert again.status_code == 200 and again.json()["status"] == "approved"


def test_receiver_name_fallback_and_bank_account():
    acc = {"name": {"th": "นาย ผู้พัฒนา ท"}, "bank": {"type": "BANKAC", "account": "xxx-x-x5234-x"}}
    assert slip_verify.receiver_matches(acc, PP, "", "ผู้พัฒนา ทดสอบ")
    assert not slip_verify.receiver_matches(acc, PP, "", "คนอื่น ทดสอบ")
    assert slip_verify.receiver_matches({"bank": {"account": "xxx-x-x5234-x"}}, PP, "123-4-55234-6")  # เลขบัญชีที่ผูกพร้อมเพย์
    assert not slip_verify.receiver_matches({"bank": {"account": "xxx-x-x5234-x"}}, PP, "")
