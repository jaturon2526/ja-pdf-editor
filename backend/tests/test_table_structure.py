"""Tests for Table Structure Editing (v1.46.0): insert/delete row & col, merge/split cells + Undo."""
import fitz


def _make_table_pdf() -> bytes:
    """Create a synthetic 3x3 bordered table PDF with text in each cell."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    xs = [60.0, 180.0, 300.0, 420.0]
    ys = [100.0, 140.0, 180.0, 220.0]
    shape = page.new_shape()
    for r in range(3):
        for c in range(3):
            shape.draw_rect(fitz.Rect(xs[c], ys[r], xs[c + 1], ys[r + 1]))
    shape.finish(color=(0, 0, 0), width=1.0)
    shape.commit()
    for r in range(3):
        for c in range(3):
            page.insert_text((xs[c] + 10, ys[r] + 24), f"R{r + 1}C{c + 1}", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _get_first_table(client, sid, headers):
    r = client.get(f"/edit/{sid}/page/0/tables", headers=headers)
    assert r.status_code == 200, r.text
    tables = r.json()["tables"]
    assert len(tables) == 1
    return tables[0]


def test_insert_and_delete_row_and_col_with_undo(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_table_pdf())

    t0 = _get_first_table(client, sid, h)
    assert len(t0["ys"]) == 4  # 3 rows
    assert len(t0["xs"]) == 4  # 3 cols

    # 1) Insert row below row 0 → 4 rows
    r1 = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t0["bbox"], "op": "insert_row", "r0": 0, "c0": 0, "position": "below"},
        headers=h,
    )
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert len(b1["ys"]) == 5
    assert len(b1["cells"]) == 12

    # 2) Delete the inserted row (row 1) → back to 3 rows
    t1 = _get_first_table(client, sid, h)
    r2 = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t1["bbox"], "op": "delete_row", "r0": 1, "c0": 0},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    assert len(r2.json()["ys"]) == 4

    # 3) Insert column right of col 0 → 4 cols
    t2 = _get_first_table(client, sid, h)
    r3 = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t2["bbox"], "op": "insert_col", "r0": 0, "c0": 0, "position": "right"},
        headers=h,
    )
    assert r3.status_code == 200, r3.text
    assert len(r3.json()["xs"]) == 5

    # 4) Delete column 1 → back to 3 cols
    t3 = _get_first_table(client, sid, h)
    r4 = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t3["bbox"], "op": "delete_col", "r0": 0, "c0": 1},
        headers=h,
    )
    assert r4.status_code == 200, r4.text
    assert len(r4.json()["xs"]) == 4

    # 5) Undo restores 4 cols
    client.post(f"/pdf/{sid}/undo", headers=h)
    t_undo = _get_first_table(client, sid, h)
    assert len(t_undo["xs"]) == 5


def test_merge_and_split_cells(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_table_pdf())

    t0 = _get_first_table(client, sid, h)
    assert len(t0["cells"]) == 9

    # Merge 2x2 block (r0=0, c0=0 .. r1=1, c1=1) → 1 merged cell + 5 remaining = 6 cells
    r_merge = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t0["bbox"], "op": "merge_cells", "r0": 0, "c0": 0, "r1": 1, "c1": 1},
        headers=h,
    )
    assert r_merge.status_code == 200, r_merge.text
    cells_merged = r_merge.json()["cells"]
    assert len(cells_merged) == 6
    merged = next(c for c in cells_merged if c["r"] == 0 and c["c"] == 0)
    assert merged["rowspan"] == 2 and merged["colspan"] == 2

    # Split merged cell (unmerge) → back to 9 cells (1x1 each)
    t1 = _get_first_table(client, sid, h)
    r_unmerge = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t1["bbox"], "op": "split_cell", "r0": 0, "c0": 0},
        headers=h,
    )
    assert r_unmerge.status_code == 200, r_unmerge.text
    assert len(r_unmerge.json()["cells"]) == 9

    # Split a single 1x1 cell (r0=0, c0=0) into 2 columns → xs grows to 5, cells = 10, other rows' col 0 get colspan=2
    t2 = _get_first_table(client, sid, h)
    r_split_col = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t2["bbox"], "op": "split_cell", "r0": 0, "c0": 0, "direction": "cols"},
        headers=h,
    )
    assert r_split_col.status_code == 200, r_split_col.text
    b_split = r_split_col.json()
    assert len(b_split["xs"]) == 5
    assert len(b_split["cells"]) == 10
    row1_col0 = next(c for c in b_split["cells"] if c["r"] == 1 and c["c"] == 0)
    assert row1_col0["colspan"] == 2


def test_table_structure_validation_guards(client, make_user, upload):
    _, h = make_user()
    sid = upload(h, _make_table_pdf())
    t0 = _get_first_table(client, sid, h)

    # Merging a single cell fails with 400
    r_single = client.post(
        f"/edit/{sid}/page/0/table/structure",
        json={"bbox": t0["bbox"], "op": "merge_cells", "r0": 0, "c0": 0, "r1": 0, "c1": 0},
        headers=h,
    )
    assert r_single.status_code == 400
