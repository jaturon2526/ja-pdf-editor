"""Tests for Crop Page feature (v1.44.0): POST /pdf/{session_id}/pages/crop."""
import fitz


def _make_pdf_bytes(num_pages: int = 3, width: float = 595.0, height: float = 842.0, rotate: int = 0) -> bytes:
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page(width=width, height=height)
        page.insert_text((100, 100), f"Page {i + 1}")
        if rotate:
            page.set_rotation(rotate)
    data = doc.tobytes()
    doc.close()
    return data


def test_crop_single_page_and_undo_redo(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_pdf_bytes(num_pages=2))

    resp = client.post(
        f"/pdf/{sid}/pages/crop",
        json={"page_numbers": [0], "left_pt": 50, "top_pt": 40, "right_pt": 30, "bottom_pt": 20},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "cropped_pages": 1}

    info = client.get(f"/pdf/{sid}/info", headers=h).json()
    w0, h0 = info["page_sizes"][0]
    w1, h1 = info["page_sizes"][1]
    assert abs(w0 - 515.0) < 0.5
    assert abs(h0 - 782.0) < 0.5
    assert abs(w1 - 595.0) < 0.5
    assert abs(h1 - 842.0) < 0.5

    # Cropping a second time shrinks from the already-cropped box accurately
    resp2 = client.post(
        f"/pdf/{sid}/pages/crop",
        json={"page_numbers": [0], "left_pt": 15, "top_pt": 10, "right_pt": 0, "bottom_pt": 12},
        headers=h,
    )
    assert resp2.status_code == 200, resp2.text
    info2 = client.get(f"/pdf/{sid}/info", headers=h).json()
    assert abs(info2["page_sizes"][0][0] - 500.0) < 0.5
    assert abs(info2["page_sizes"][0][1] - 760.0) < 0.5

    # Undo restores first crop, second Undo restores original size
    client.post(f"/pdf/{sid}/undo", headers=h)
    info_u1 = client.get(f"/pdf/{sid}/info", headers=h).json()
    assert abs(info_u1["page_sizes"][0][0] - 515.0) < 0.5
    client.post(f"/pdf/{sid}/undo", headers=h)
    info_u2 = client.get(f"/pdf/{sid}/info", headers=h).json()
    assert abs(info_u2["page_sizes"][0][0] - 595.0) < 0.5
    assert abs(info_u2["page_sizes"][0][1] - 842.0) < 0.5


def test_crop_rotated_page_uses_visual_edges(client, make_user, upload):
    # A4 rotated 90° → visual size is 842 × 595
    _, h = make_user()
    sid = upload(h, _make_pdf_bytes(num_pages=1, rotate=90))

    info0 = client.get(f"/pdf/{sid}/info", headers=h).json()
    assert abs(info0["page_sizes"][0][0] - 842.0) < 0.5
    assert abs(info0["page_sizes"][0][1] - 595.0) < 0.5

    resp = client.post(
        f"/pdf/{sid}/pages/crop",
        json={"page_numbers": [0], "left_pt": 100, "top_pt": 50, "right_pt": 42, "bottom_pt": 45},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    info1 = client.get(f"/pdf/{sid}/info", headers=h).json()
    assert abs(info1["page_sizes"][0][0] - 700.0) < 0.5
    assert abs(info1["page_sizes"][0][1] - 500.0) < 0.5


def test_crop_validation_and_noop(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_pdf_bytes(num_pages=2))

    # All zero margins → no_change
    r_noop = client.post(
        f"/pdf/{sid}/pages/crop",
        json={"page_numbers": [0, 1], "left_pt": 0, "top_pt": 0, "right_pt": 0, "bottom_pt": 0},
        headers=h,
    )
    assert r_noop.status_code == 200
    assert r_noop.json() == {"status": "no_change", "cropped_pages": 0}

    # Too small remaining width (< 36 pt) → 400
    r_small = client.post(
        f"/pdf/{sid}/pages/crop",
        json={"page_numbers": [0], "left_pt": 300, "top_pt": 0, "right_pt": 280, "bottom_pt": 0},
        headers=h,
    )
    assert r_small.status_code == 400

    # Out of range page → 400
    r_oor = client.post(
        f"/pdf/{sid}/pages/crop",
        json={"page_numbers": [5], "left_pt": 20, "top_pt": 20, "right_pt": 20, "bottom_pt": 20},
        headers=h,
    )
    assert r_oor.status_code == 400
