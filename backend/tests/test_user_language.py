"""เทสต์การตั้งค่าภาษาของผู้ใช้ในโปรไฟล์ (GET /auth/me, PUT /auth/profile)"""


def test_user_language_default_and_update(client, make_user):
    _, headers = make_user()

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["language"] == "th"

    upd = client.put("/auth/profile", headers=headers, json={"language": "en"})
    assert upd.status_code == 200, upd.text
    assert upd.json()["language"] == "en"

    me2 = client.get("/auth/me", headers=headers)
    assert me2.status_code == 200
    assert me2.json()["language"] == "en"

    back = client.put("/auth/profile", headers=headers, json={"language": "TH"})
    assert back.status_code == 200
    assert back.json()["language"] == "th"


def test_user_language_rejects_unsupported_code(client, make_user):
    _, headers = make_user()
    res = client.put("/auth/profile", headers=headers, json={"language": "xx"})
    assert res.status_code == 422
