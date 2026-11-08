"""ส่งเอกสารให้ลงนามตามลำดับ: คิว สิทธิ์ ฟิลด์ลายเซ็น และความถูกต้องของลายเซ็นทุกคนตอนจบ"""
import io

import fitz
import pytest
from PIL import Image, ImageDraw

from tests.conftest import make_pdf_bytes
from tests.signing_helpers import make_p12


def _email(client, headers):
    return client.get("/auth/me", headers=headers).json()["email"]


def _file_id(client, headers, sid):
    files = client.get("/pdf/files", headers=headers).json()["files"]
    return next(f["id"] for f in files if f["session_id"] == sid)


def _png() -> bytes:
    img = Image.new("RGB", (300, 100), "white")
    ImageDraw.Draw(img).line([(10, 80), (100, 20), (200, 70), (290, 30)], fill="navy", width=6)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def three_signers(client, make_user, upload):
    """ผู้ส่ง + ผู้ลงนาม 3 คน: ดิจิทัล → อิเล็กทรอนิกส์ → ให้เลือกเอง"""
    _, owner = make_user()
    signers = [make_user()[1] for _ in range(3)]
    sid = upload(owner, make_pdf_bytes(pages=2, text="Contract"))
    steps = [
        {"email": _email(client, signers[0]), "sign_type": "digital", "page": 1, "x0": 50, "y0": 600, "x1": 200, "y1": 660},
        {"email": _email(client, signers[1]), "sign_type": "electronic", "page": 1, "x0": 220, "y0": 600, "x1": 370, "y1": 660},
        {"email": _email(client, signers[2]), "sign_type": "either", "page": 1, "x0": 390, "y0": 600, "x1": 540, "y1": 660},
    ]
    r = client.post("/signing/requests", headers=owner,
                    json={"file_id": _file_id(client, owner, sid), "title": "Contract", "steps": steps})
    assert r.status_code == 200, r.text
    return owner, signers, r.json()["id"]


def _sign_digital(client, headers, rid, name="Signer One", email="one@example.com"):
    return client.post(f"/signing/requests/{rid}/sign", headers=headers,
                       data={"sign_type": "digital", "pfx_password": "p12-pass"},
                       files={"pfx_file": ("me.p12", make_p12(name, email), "application/x-pkcs12")})


def _sign_electronic(client, headers, rid):
    return client.post(f"/signing/requests/{rid}/sign", headers=headers, data={"sign_type": "electronic"},
                       files={"signature_image": ("sig.png", _png(), "image/png")})


def test_full_sequence_returns_signed_file_to_owner(client, three_signers):
    owner, signers, rid = three_signers

    # สร้างฟิลด์ของทุกคนไว้ล่วงหน้า ชื่อไม่ซ้ำ
    doc = fitz.open("pdf", client.get(f"/signing/requests/{rid}/document", headers=owner).content)
    names = sorted(w.field_name for w in doc[1].widgets())
    assert names == [f"SR{rid}_S1", f"SR{rid}_S2", f"SR{rid}_S3"]

    # คนที่ 2/3 ยังเซ็นไม่ได้
    assert _sign_electronic(client, signers[1], rid).status_code == 409
    assert client.get("/signing/requests?box=to_sign", headers=signers[1]).json() == []
    assert [r["id"] for r in client.get("/signing/requests?box=to_sign", headers=signers[0]).json()] == [rid]

    # ประเภทลายเซ็นต้องตรงที่ผู้ส่งกำหนด
    assert _sign_electronic(client, signers[0], rid).status_code == 400
    r = _sign_digital(client, signers[0], rid)
    assert r.status_code == 200, r.text
    assert r.json()["warning"]  # อีเมลในใบรับรองไม่ตรงกับบัญชี → เตือน
    assert _sign_digital(client, signers[0], rid).status_code == 409  # เซ็นซ้ำไม่ได้

    assert _sign_electronic(client, signers[1], rid).status_code == 200
    r = _sign_electronic(client, signers[2], rid)
    assert r.status_code == 200 and r.json()["status"] == "completed"

    detail = client.get(f"/signing/requests/{rid}", headers=owner).json()
    assert detail["status"] == "completed"
    assert [s["status"] for s in detail["steps"]] == ["signed"] * 3
    assert [e["action"] for e in detail["events"]].count("signed") == 3

    # ลายเซ็นทุกคน intact + valid + ไม่มีการแก้ไขที่ไม่อนุญาต
    report = client.get(f"/signing/requests/{rid}/verify", headers=signers[2]).json()["signatures"]
    assert len(report) == 3
    assert all(s["signed"] and s["intact"] and s["valid"] and s["modification_ok"] for s in report)

    # ไฟล์กลับไปอยู่ในรายการไฟล์ของผู้ส่ง
    files = client.get("/pdf/files", headers=owner).json()["files"]
    assert any(f["id"] == detail["result_file_id"] and "ลงนามครบแล้ว" in f["filename"] for f in files)

    # แจ้งเตือน: ผู้ส่งได้รับว่าลงนามครบ
    kinds = [n["kind"] for n in client.get("/notifications", headers=owner).json()["items"]]
    assert "sign_completed" in kinds


def test_outsiders_cannot_see_or_sign(client, make_user, three_signers):
    _, _, rid = three_signers
    _, outsider = make_user()
    assert client.get(f"/signing/requests/{rid}", headers=outsider).status_code == 404
    assert client.get(f"/signing/requests/{rid}/document", headers=outsider).status_code == 404
    assert _sign_electronic(client, outsider, rid).status_code == 404


def test_reject_stops_the_sequence_and_owner_can_not_cancel_after(client, three_signers):
    owner, signers, rid = three_signers
    assert client.post(f"/signing/requests/{rid}/reject", headers=signers[1], json={"reason": "x"}).status_code == 409
    assert client.post(f"/signing/requests/{rid}/reject", headers=signers[0], json={"reason": "ข้อมูลผิด"}).status_code == 200
    detail = client.get(f"/signing/requests/{rid}", headers=owner).json()
    assert detail["status"] == "rejected" and detail["steps"][0]["comment"] == "ข้อมูลผิด"
    assert _sign_digital(client, signers[0], rid).status_code == 409
    assert client.post(f"/signing/requests/{rid}/cancel", headers=owner).status_code == 409
    assert any(n["kind"] == "sign_rejected" for n in client.get("/notifications", headers=owner).json()["items"])


def test_cancel_only_by_owner(client, three_signers):
    owner, signers, rid = three_signers
    assert client.post(f"/signing/requests/{rid}/cancel", headers=signers[0]).status_code == 403
    assert client.post(f"/signing/requests/{rid}/cancel", headers=owner).status_code == 200
    assert _sign_digital(client, signers[0], rid).status_code == 409


def test_create_validates_signers_and_boxes(client, make_user, upload):
    _, owner = make_user()
    sid = upload(owner, make_pdf_bytes(pages=1))
    fid = _file_id(client, owner, sid)
    _, other = make_user()
    good = {"email": _email(client, other), "sign_type": "either", "page": 0, "x0": 50, "y0": 50, "x1": 200, "y1": 110}
    cases = [
        [{**good, "email": "not-an-email"}],          # อีเมลผิดรูปแบบ (อีเมลที่ยังไม่มีบัญชี = เชิญ ดู test_signing_phase3)
        [good, good],                                 # คนเดียวกันซ้ำ
        [good, {**good, "email": good["email"].upper()}],  # ซ้ำแบบตัวพิมพ์ต่างกัน
        [{**good, "page": 3}],                         # นอกหน้า
        [{**good, "x1": 60}],                          # กล่องเล็กเกิน
        [],
    ]
    for steps in cases:
        r = client.post("/signing/requests", headers=owner, json={"file_id": fid, "steps": steps})
        assert r.status_code == 400, (steps, r.text)
    # ไฟล์ของคนอื่นใช้ไม่ได้
    assert client.post("/signing/requests", headers=other, json={"file_id": fid, "steps": [good]}).status_code == 404


def test_notifications_mark_read(client, three_signers):
    _, signers, _ = three_signers
    data = client.get("/notifications", headers=signers[0]).json()
    assert data["unread"] == 1 and data["items"][0]["kind"] == "sign_turn"
    client.post("/notifications/read", headers=signers[0], json={})
    assert client.get("/notifications", headers=signers[0]).json()["unread"] == 0


def test_opening_signed_result_keeps_signatures_on_download(client, three_signers):
    owner, signers, rid = three_signers
    _sign_digital(client, signers[0], rid)
    _sign_electronic(client, signers[1], rid)
    _sign_electronic(client, signers[2], rid)
    result_id = client.get(f"/signing/requests/{rid}", headers=owner).json()["result_file_id"]
    sid = next(f["session_id"] for f in client.get("/pdf/files", headers=owner).json()["files"] if f["id"] == result_id)
    r = client.post(f"/pdf/{sid}/open", headers=owner)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    data = client.get(f"/pdf/{sid}/download", headers=owner).content
    from app.services.signing_pdf import signature_report

    report = signature_report(data)
    assert len(report) == 3 and all(s["intact"] and s["valid"] for s in report)


def test_lookup_is_exact_match_only(client, make_user):
    _, headers = make_user()
    assert client.get("/signing/users/lookup", params={"email": "%"}, headers=headers).status_code == 404
    assert client.get("/signing/users/lookup", params={"email": "user_@example.com"}, headers=headers).status_code == 404
    email = _email(client, headers)
    r = client.get("/signing/users/lookup", params={"email": email.upper()}, headers=headers)
    assert r.status_code == 200 and r.json()["email"] == email
