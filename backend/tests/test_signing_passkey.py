"""ยืนยันตัวตนด้วย passkey ก่อนลงนาม — ผู้ส่งบังคับได้รายคน · บันทึกลงคำขอ/เหตุการณ์/หนังสือรับรอง"""
import json

import fitz

from tests.test_passkey import SoftAuthenticator, _register
from tests.test_passkey import _rp as _rp  # noqa: F401 — fixture ตั้ง RP ID = localhost
from tests.test_signing import _email, _png
from tests.test_signing_phase3 import _box, _create


def _sign(client, headers, rid, passkey=None):
    data = {"sign_type": "electronic"}
    if passkey is not None:
        auth, flow_id = passkey
        opts = client.post(f"/signing/requests/{rid}/passkey/options", headers=headers)
        assert opts.status_code == 200, opts.text
        body = opts.json()
        data["passkey_flow_id"] = flow_id or body["flow_id"]
        data["passkey_credential"] = json.dumps(auth.get(body["options"]))
    return client.post(f"/signing/requests/{rid}/sign", headers=headers, data=data,
                       files={"signature_image": ("sig.png", _png(), "image/png")})


def _request(client, owner, signer, upload, require=True):
    r = _create(client, owner, upload, [{"email": _email(client, signer), "sign_type": "electronic",
                                          "require_passkey": require, **_box(0)}])
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_required_passkey_blocks_plain_signing_then_allows_with_passkey(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    auth = SoftAuthenticator()
    assert _register(client, signer, auth, "iPhone").status_code == 200
    rid = _request(client, owner, signer, upload)

    detail = client.get(f"/signing/requests/{rid}", headers=signer).json()
    assert detail["my_require_passkey"] is True and detail["steps"][0]["require_passkey"] is True

    r = _sign(client, signer, rid)
    assert r.status_code == 403 and "passkey" in r.json()["detail"]

    r = _sign(client, signer, rid, passkey=(auth, None))
    assert r.status_code == 200, r.text
    step = client.get(f"/signing/requests/{rid}", headers=owner).json()["steps"][0]
    assert step["status"] == "signed" and step["verified_method"] == "passkey" and step["verified_detail"] == "iPhone"

    # หนังสือรับรองระบุการยืนยันตัวตน
    ev = client.get(f"/signing/requests/{rid}/evidence", headers=owner)
    assert ev.status_code == 200
    text = "".join(p.get_text() for p in fitz.open("pdf", ev.content))
    assert "Passkey" in text and "iPhone" in text


def test_optional_passkey_is_recorded_when_used(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    auth = SoftAuthenticator()
    assert _register(client, signer, auth, "Mac").status_code == 200
    rid = _request(client, owner, signer, upload, require=False)
    assert _sign(client, signer, rid, passkey=(auth, None)).status_code == 200
    events = client.get(f"/signing/requests/{rid}", headers=owner).json()["events"]
    assert any("ยืนยันตัวตนด้วย passkey (Mac)" in (e["detail"] or "") for e in events if e["action"] == "signed")


def test_not_required_still_signs_without_passkey(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    rid = _request(client, owner, signer, upload, require=False)
    assert _sign(client, signer, rid).status_code == 200
    step = client.get(f"/signing/requests/{rid}", headers=owner).json()["steps"][0]
    assert step["verified_method"] is None


def test_signer_without_passkey_gets_clear_error(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    rid = _request(client, owner, signer, upload)
    r = client.post(f"/signing/requests/{rid}/passkey/options", headers=signer)
    assert r.status_code == 400 and "ยังไม่มี passkey" in r.json()["detail"]


def test_someone_elses_passkey_or_flow_is_rejected(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    _, other = make_user()
    mine, theirs = SoftAuthenticator(), SoftAuthenticator()
    assert _register(client, signer, mine).status_code == 200
    assert _register(client, other, theirs).status_code == 200
    rid = _request(client, owner, signer, upload)

    # passkey ของคนอื่น (เช่น ยืมเครื่องคนอื่นสแกน) ใช้ยืนยันแทนไม่ได้
    assert _sign(client, signer, rid, passkey=(theirs, None)).status_code == 403
    # คนที่ไม่ใช่ผู้ลงนามขอ challenge ไม่ได้
    assert client.post(f"/signing/requests/{rid}/passkey/options", headers=other).status_code in (403, 404)
    # flow ของการเข้าสู่ระบบ ใช้กับการลงนามไม่ได้
    login = client.post("/auth/passkeys/login/options").json()
    r = client.post(f"/signing/requests/{rid}/sign", headers=signer, data={
        "sign_type": "electronic", "passkey_flow_id": login["flow_id"],
        "passkey_credential": json.dumps(mine.get(login["options"]))},
        files={"signature_image": ("sig.png", _png(), "image/png")})
    assert r.status_code == 403
    assert _sign(client, signer, rid, passkey=(mine, None)).status_code == 200


def test_bad_credential_json_is_400(client, make_user, upload):
    _, owner = make_user()
    _, signer = make_user()
    rid = _request(client, owner, signer, upload, require=False)
    r = client.post(f"/signing/requests/{rid}/sign", headers=signer,
                    data={"sign_type": "electronic", "passkey_credential": "not-json"},
                    files={"signature_image": ("sig.png", _png(), "image/png")})
    assert r.status_code == 400
