"""วิเคราะห์ภาพหน้าสแกน: เส้นตาราง/กรอบ, ส่วนที่ไม่ใช่ข้อความ (โลโก้ ลายเซ็น บาร์โค้ด), จุดไข่ปลา, รอยขอบกระดาษ

ทุกพิกัดเป็นพิกเซลของภาพหน้าที่ deskew แล้ว (x0, y0, x1, y1)
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from app.services import ocr_thai

Box = tuple[int, int, int, int]


@dataclass
class Cell:
    row: int
    col: int
    box: Box
    row_span: int = 1
    col_span: int = 1


@dataclass
class Grid:
    """ตาราง (หลายช่อง) หรือกรอบ (ช่องเดียว) ที่วาดด้วยเส้น"""
    box: Box
    cols: list[int]            # ตำแหน่งเส้นแนวตั้ง x (เรียงจากซ้าย) — len = จำนวนคอลัมน์ + 1
    rows: list[int]            # ตำแหน่งเส้นแนวนอน y — len = จำนวนแถว + 1
    cells: list[Cell] = field(default_factory=list)

    @property
    def is_box(self) -> bool:
        return len(self.cells) == 1


@dataclass
class Graphic:
    box: Box
    kind: str                  # "image" (โลโก้/ลายเซ็น/ตรา/รูป) | "barcode"


@dataclass
class Leader:
    box: Box                   # แถวจุดไข่ปลา/เส้นประ


@dataclass
class PageAnalysis:
    gray: Image.Image          # ภาพเทา (deskew แล้ว)
    color: Image.Image         # ภาพสี (deskew แล้ว) — ใช้ตัดรูป
    text_gray: Image.Image     # ภาพที่ลบเส้น/รูป/จุดไข่ปลาออกแล้ว — ส่งให้ OCR
    char_h: float              # ความสูงตัวอักษรโดยประมาณ (px)
    grids: list[Grid]
    graphics: list[Graphic]
    leaders: list[Leader]
    rules: list[Box]           # เส้นแนวนอนเดี่ยว (เส้นใต้/เส้นให้เขียน) ที่ไม่ได้เป็นส่วนของตาราง
    content: Box               # กรอบเนื้อหาทั้งหน้า (ไม่รวมรอยขอบ)
    checkboxes: list[Box] = field(default_factory=list)   # ช่องสี่เหลี่ยมให้ติ๊ก (☐)
    inverted: list[Box] = field(default_factory=list)     # พื้นที่ตัวอักษรขาวบนพื้นเข้ม (กลับสีแล้ว)
    angle: float = 0.0                                    # มุมที่หมุนแก้เอียง (องศา)
    layer_lines: list | None = None                       # คำจากชั้นข้อความ OCR เดิมของไฟล์ (px) — ใช้แทนการอ่านใหม่


# ---------------------------------------------------------------- เครื่องมือ

def _components(mask: np.ndarray):
    n, labels, stats, cent = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return n, labels, stats, cent


def _box_of(stat) -> Box:
    x, y, w, h = (int(v) for v in stat[:4])
    return x, y, x + w, y + h


def overlap(a: Box, b: Box) -> int:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0


def area(b: Box) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def inside(inner: Box, outer: Box, frac: float = 0.6) -> bool:
    return overlap(inner, outer) >= frac * max(1, area(inner))


def union(a: Box, b: Box) -> Box:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def estimate_char_height(mask: np.ndarray) -> float:
    """ความสูงตัวอักษรหลัก: ฐานนิยมของความสูงก้อนหมึกขนาดตัวอักษร (ตัด จุด/วรรณยุกต์ และก้อนใหญ่ทิ้ง)"""
    n, _l, stats, _c = _components(mask)
    hs = stats[1:, cv2.CC_STAT_HEIGHT]
    ws = stats[1:, cv2.CC_STAT_WIDTH]
    H = mask.shape[0]
    ok = hs[(hs >= max(6, H * 0.004)) & (hs <= H * 0.05) & (ws <= hs * 3)]
    if len(ok) < 10:
        return max(12.0, H * 0.012)
    hist = np.bincount(ok)
    # ฐานนิยมแบบเรียบ (หน้าต่าง 3 px) — ตัวอักษรไทยส่วนใหญ่สูงเท่ากัน (ไม่นับหาง/สระบน)
    smooth = np.convolve(hist, np.ones(3), mode="same")
    return float(np.argmax(smooth))


# ---------------------------------------------------------------- deskew

def deskew(gray: Image.Image, color: Image.Image) -> tuple[Image.Image, Image.Image, float]:
    mask = np.asarray(gray) <= ocr_thai.otsu_threshold(np.asarray(gray))
    angle = ocr_thai.deskew_angle(mask)
    if not angle:
        return gray, color, 0.0
    g = gray.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
    c = color.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
    return g, c, angle


# ---------------------------------------------------------------- เส้น / ตาราง

def _line_masks(mask: np.ndarray, char_h: float) -> tuple[np.ndarray, np.ndarray]:
    """เส้นแนวนอน/แนวตั้งยาว — ขยายหมึกตามขวางก่อน (เส้นที่เอียงเล็กน้อยจากการถ่าย/สแกนจะเป็นขั้นบันได
    ถ้าไม่ขยาย MORPH_OPEN ด้วยเคอร์เนลกว้าง 1 px จะหาไม่เจอ) แล้วตัดกลับให้เหลือเฉพาะพิกเซลหมึกจริง"""
    m = mask.astype(np.uint8)
    hl = int(max(4 * char_h, 30))
    vl = int(max(2.2 * char_h, 24))
    t = max(2, int(round(char_h * 0.22)))
    mh = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_RECT, (1, t)))
    mv = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_RECT, (t, 1)))
    # เส้นแนวตั้งบาง/จางที่สแกนออกมาเป็นช่วง ๆ — เชื่อมรอยขาดสั้น ๆ ก่อน
    mv = cv2.morphologyEx(mv, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(3, int(0.45 * char_h)))))
    horiz = cv2.morphologyEx(mh, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (hl, 1)))
    vert = cv2.morphologyEx(mv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vl)))
    return (_thin(horiz.astype(bool) & (mh > 0), mask, char_h, axis=1),
            _thin(vert.astype(bool) & (mv > 0), mask, char_h, axis=0))


def _thin(lines: np.ndarray, mask: np.ndarray, char_h: float, axis: int) -> np.ndarray:
    """เก็บเฉพาะก้อนที่ยาว บาง และโดดเดี่ยว (เส้นจริง) — ก้อนหนา หรือก้อนที่จมอยู่ในหมึกหนาแน่น
    คือส่วนของโลโก้/ตรา/บาร์โค้ดที่ดูเหมือนเส้นหลังขยาย"""
    n, labels, stats, _c = _components(lines)
    keep = np.zeros(n, dtype=bool)
    pad = max(2, int(0.3 * char_h))
    H, W = mask.shape
    for i in range(1, n):
        x, y, w, h, cnt = (int(v) for v in stats[i])
        length, thick = (w, h) if axis == 1 else (h, w)
        if thick > max(0.5 * char_h, 0.1 * length):
            continue
        if axis == 1:
            region = mask[max(0, y - pad):min(H, y + h + pad), x:x + w]
        else:
            region = mask[y:y + h, max(0, x - pad):min(W, x + w + pad)]
        keep[i] = cnt >= 0.45 * max(1, int(region.sum()))
    return keep[labels]


def _positions(proj: np.ndarray, min_val: float) -> list[int]:
    """ตำแหน่งกึ่งกลางของช่วงที่ค่า projection ≥ min_val (เส้นหนาหลายพิกเซลรวมเป็นตำแหน่งเดียว)"""
    on = proj >= min_val
    out, i, n = [], 0, len(on)
    while i < n:
        if on[i]:
            j = i
            while j + 1 < n and on[j + 1]:
                j += 1
            out.append((i + j) // 2)
            i = j + 1
        else:
            i += 1
    return out


def _line_positions(lines: np.ndarray, min_len: float, axis: int, offset: int) -> list[int]:
    """ตำแหน่งเส้น (ค่ากลางตามแนวขวาง) จากก้อนเส้นที่ยาว ≥ min_len — ทนต่อเส้นเอียงเล็กน้อย
    axis=1: เส้นแนวนอน → ตำแหน่ง y · axis=0: เส้นแนวตั้ง → ตำแหน่ง x"""
    n, labels, st, cent = _components(lines)
    out = []
    for i in range(1, n):
        length = st[i, cv2.CC_STAT_WIDTH] if axis == 1 else st[i, cv2.CC_STAT_HEIGHT]
        if length >= min_len:
            out.append(offset + int(round(cent[i][1] if axis == 1 else cent[i][0])))
    # เส้นที่ขาดเป็นช่วง ๆ: รวมความยาวของก้อนที่อยู่แนวเดียวกัน
    if not out:
        proj = lines.sum(axis=1 if axis == 1 else 0)
        out = [offset + p for p in _positions(proj, min_len)]
    return out


def _merge_close(pos: list[int], tol: int) -> list[int]:
    out: list[int] = []
    for p in sorted(pos):
        if out and p - out[-1] <= tol:
            out[-1] = (out[-1] + p) // 2
        else:
            out.append(p)
    return out


def find_grids(horiz: np.ndarray, vert: np.ndarray, char_h: float) -> list[Grid]:
    """กลุ่มเส้นที่ต่อกันเป็นตาราง/กรอบ → แถว/คอลัมน์/ช่อง (รองรับช่องผสาน)"""
    # ปิดรอยขาดของเส้นที่พิมพ์ไม่ต่อเนื่อง (ตามแนวเส้น) แล้วเชื่อมมุมตาราง
    hc = cv2.morphologyEx(horiz.astype(np.uint8), cv2.MORPH_CLOSE,
                          cv2.getStructuringElement(cv2.MORPH_RECT, (int(3 * char_h), 1)))
    vc = cv2.morphologyEx(vert.astype(np.uint8), cv2.MORPH_CLOSE,
                          cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(2.5 * char_h))))
    both = hc | vc
    k = max(3, int(char_h * 0.9))
    joined = cv2.dilate(both, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    n, labels, stats, _c = _components(joined)
    horiz_c, vert_c = hc.astype(bool), vc.astype(bool)
    grids: list[Grid] = []
    for i in range(1, n):
        bx0, by0, bx1, by1 = _box_of(stats[i])
        comp = (labels[by0:by1, bx0:bx1] == i) & (both[by0:by1, bx0:bx1] > 0)
        ys, xs = np.nonzero(comp)
        if not len(xs):
            continue
        x0, y0, x1, y1 = bx0 + int(xs.min()), by0 + int(ys.min()), bx0 + int(xs.max()) + 1, by0 + int(ys.max()) + 1
        if (x1 - x0) < 4 * char_h or (y1 - y0) < 1.2 * char_h:
            continue
        sub_h = horiz_c[y0:y1, x0:x1]
        sub_v = vert_c[y0:y1, x0:x1]
        if not sub_h.any() or not sub_v.any():
            continue
        tol = max(3, int(char_h * 0.6))
        w, h = x1 - x0, y1 - y0
        rows = _merge_close(_line_positions(sub_h, max(3 * char_h, 0.12 * w), axis=1, offset=y0), tol)
        cols = _merge_close(_line_positions(sub_v, max(1.5 * char_h, 0.12 * h), axis=0, offset=x0), tol)
        if len(rows) >= 2 and len(cols) == 1:
            # กรอบที่เส้นข้างหนึ่งจางจนหายไปตอนสแกน: ใช้ปลายเส้นบน/ล่างแทนเส้นข้างที่หาย
            xs = np.nonzero(sub_h.any(axis=0))[0]
            if len(xs):
                ex0, ex1 = x0 + int(xs.min()), x0 + int(xs.max())
                c = cols[0]
                cols = sorted([c, ex1 if c - ex0 < ex1 - c else ex0])
        if len(rows) < 2 or len(cols) < 2:
            continue
        # ตารางสองชุดที่วางชิดกัน (ช่องว่างแคบระหว่างเส้นล่างของตารางบนกับเส้นบนของตารางล่าง ไม่มีเส้นแนวตั้งผ่าน)
        # → แยกเป็นคนละตาราง
        parts: list[list[int]] = [[rows[0]]]
        for ya, yb in zip(rows, rows[1:]):
            mid = (ya + yb) // 2
            crossed = any(vert[mid, max(0, c - tol):c + tol + 1].any() for c in cols)
            if yb - ya < 1.4 * char_h and not crossed:
                parts.append([yb])
            else:
                parts[-1].append(yb)
        for part in parts:
            if len(part) < 2:
                continue
            gy0, gy1 = part[0], part[-1]
            # คอลัมน์ของส่วนนี้: เส้นแนวตั้งที่มีหมึกในช่วงนี้จริง
            pc = [c for c in cols if vert_c[gy0:gy1, max(0, c - tol):c + tol + 1].any(axis=1).mean() >= 0.3]
            if len(pc) == 1 and len(cols) == 2:
                pc = cols   # เส้นข้างที่หายไป (เติมจากปลายเส้นแนวนอนด้านบน)
            if len(pc) < 2 or pc[-1] - pc[0] < 4 * char_h or gy1 - gy0 < 1.2 * char_h:
                continue
            g = Grid((pc[0], gy0, pc[-1], gy1), pc, part)
            g.cells = _cells(g, horiz_c, vert_c, tol)
            if g.cells:
                grids.append(g)
    return grids


def _cells(g: Grid, horiz: np.ndarray, vert: np.ndarray, tol: int) -> list[Cell]:
    """ช่องตาราง: เริ่มจากตารางเต็ม แล้วผสานช่องที่ไม่มีเส้นคั่นจริง (เส้นต้องมีหมึก ≥ 60% ของความยาวขอบ)"""
    R, C = len(g.rows) - 1, len(g.cols) - 1

    def has_v(x: int, ya: int, yb: int) -> bool:
        a = vert[ya + tol:max(ya + tol + 1, yb - tol), max(0, x - tol):x + tol + 1].any(axis=1)
        return a.size > 0 and a.mean() >= 0.6

    def has_h(y: int, xa: int, xb: int) -> bool:
        a = horiz[max(0, y - tol):y + tol + 1, xa + tol:max(xa + tol + 1, xb - tol)].any(axis=0)
        return a.size > 0 and a.mean() >= 0.6

    owner = [[None] * C for _ in range(R)]
    cells: list[Cell] = []
    for r in range(R):
        for c in range(C):
            if owner[r][c] is not None:
                continue
            # ขยายไปทางขวาเมื่อไม่มีเส้นแนวตั้งคั่น
            cs = 1
            while c + cs < C and not has_v(g.cols[c + cs], g.rows[r], g.rows[r + 1]):
                cs += 1
            # ขยายลงเมื่อไม่มีเส้นแนวนอนคั่น (ตลอดความกว้างของช่องที่ผสานแล้ว)
            rs = 1
            while r + rs < R and not has_h(g.rows[r + rs], g.cols[c], g.cols[c + cs]) \
                    and all(owner[r + rs][cc] is None for cc in range(c, c + cs)):
                rs += 1
            cell = Cell(r, c, (g.cols[c], g.rows[r], g.cols[c + cs], g.rows[r + rs]), rs, cs)
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    owner[rr][cc] = cell
            cells.append(cell)
    return cells


def lone_rules(horiz: np.ndarray, grids: list[Grid], char_h: float) -> list[Box]:
    n, _l, stats, _c = _components(horiz)
    out = []
    for i in range(1, n):
        b = _box_of(stats[i])
        if b[2] - b[0] < 4 * char_h:
            continue
        if any(inside(b, g.box, 0.5) for g in grids):
            continue
        out.append(b)
    return out


# ---------------------------------------------------------------- จุดไข่ปลา

def find_leaders(mask: np.ndarray, char_h: float) -> list[Leader]:
    """แถวจุดไข่ปลา: จุดเล็กเกือบจัตุรัสเรียงระดับเดียวกัน ≥ 6 จุด (เกณฑ์เดียวกับ ocr_thai.remove_dot_leaders)"""
    n, _l, stats, cent = _components(mask)
    lim = max(3.0, 0.3 * char_h)
    dots = [i for i in range(1, n)
            if stats[i, cv2.CC_STAT_WIDTH] <= lim and stats[i, cv2.CC_STAT_HEIGHT] <= lim
            and 0.4 <= stats[i, cv2.CC_STAT_WIDTH] / max(1, stats[i, cv2.CC_STAT_HEIGHT]) <= 2.5]
    if len(dots) < 6:
        return []
    dots.sort(key=lambda i: (round(cent[i][1] / max(2.0, lim)), cent[i][0]))
    out: list[Leader] = []
    run = [dots[0]]

    def flush(r):
        if len(r) >= 6:
            gaps = np.diff([cent[i][0] for i in r])
            if gaps.max() <= 3 * np.median(gaps):
                b = _box_of(stats[r[0]])
                for i in r[1:]:
                    b = union(b, _box_of(stats[i]))
                out.append(Leader(b))

    for i in dots[1:]:
        j = run[-1]
        if abs(cent[i][1] - cent[j][1]) <= lim * 0.6 and 0 < cent[i][0] - cent[j][0] <= 4 * lim:
            run.append(i)
        else:
            flush(run)
            run = [i]
    flush(run)
    return out


# ---------------------------------------------------------------- ส่วนที่ไม่ใช่ข้อความ

BARCODE_ROW_MATCH = 0.92      # แถวพิกเซลในบาร์โค้ดเหมือนกันแทบทุกแถว (ข้อความจริงได้ ≤ 0.89 ในไฟล์ทดสอบ)
BARCODE_TRANSITIONS = 3.0     # จำนวนขอบขาว/ดำ ต่อความกว้างหนึ่งตัวอักษร


def find_barcodes(mask: np.ndarray, char_h: float) -> list[Box]:
    """บาร์โค้ด 1 มิติ (แนวนอนหรือหมุน 90°): ก้อนที่ทุกแถว (ตามแนวแท่ง) มีลวดลายเดียวกัน และขอบถี่"""
    out: list[Box] = []
    for axis in (0, 1):
        m = mask if axis == 0 else mask.T
        k = max(4, int(0.9 * char_h))
        dil = cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
        n, _l, st, _c = _components(dil)
        for i in range(1, n):
            x, y, w, h = (int(v) for v in st[i][:4])
            if w < 3 * char_h or h < 0.7 * char_h:
                continue
            # กรอบจากภาพที่ขยายแล้วกว้างเกินจริงครึ่งเคอร์เนลทั้งสองข้าง
            x, w = x + k // 2, max(1, w - 2 * (k // 2))
            sub = m[y + h // 10:y + h - h // 10, x:x + w]
            if sub.shape[0] < 3:
                continue
            ref = sub.mean(axis=0) > 0.5
            score = float((sub == ref).mean())
            trans = np.count_nonzero(np.diff(ref.astype(np.int8))) / (w / char_h)
            if score >= BARCODE_ROW_MATCH and trans >= BARCODE_TRANSITIONS:
                out.append((x, y, x + w, y + h) if axis == 0 else (y, x, y + h, x + w))
    return out


def find_graphics(mask: np.ndarray, char_h: float, exclude: list[Box]) -> list[Graphic]:
    """โลโก้/ตรา/ลายเซ็น/บาร์โค้ด: ก้อนหมึกที่ใหญ่กว่าตัวอักษรมาก หรือแท่งบาร์โค้ดหลายแท่งเรียงกัน
    แล้วรวมกับก้อนข้างเคียงที่อยู่ติดกัน (ส่วนประกอบของโลโก้/ลายเซ็นเดียวกัน)"""
    n, labels, stats, _c = _components(mask)
    seeds: list[Box] = []
    for i in range(1, n):
        b = _box_of(stats[i])
        w, h = b[2] - b[0], b[3] - b[1]
        if any(inside(b, e, 0.5) for e in exclude):
            continue
        fill = stats[i, cv2.CC_STAT_AREA] / max(1, w * h)
        if (w < 0.3 * char_h and h > 2 * char_h) or (h < 0.3 * char_h and w > 2 * char_h):
            if fill > 0.5:
                continue         # เศษเส้นตาราง/กรอบที่เอียง — ไม่ใช่รูป
        if h > 2.6 * char_h or (w > 2.6 * char_h and h > 1.9 * char_h):
            seeds.append(b)
    graphics: list[Graphic] = [Graphic(b, "barcode") for b in find_barcodes(mask, char_h)]
    for group in _cluster(seeds, gap=0.8 * char_h):
        b = group[0]
        for g in group[1:]:
            b = union(b, g)
        if any(inside(b, g.box, 0.5) for g in graphics):
            continue
        graphics.append(Graphic(b, "image"))
    # ดึงก้อนเล็กรอบ ๆ (จุด หัวตัวอักษรของลายเซ็น ตัวเลขใต้บาร์โค้ด) เข้ามาในกรอบ
    out = []
    for g in graphics:
        x0, y0, x1, y1 = g.box
        pad = int(0.35 * char_h)
        sub = labels[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
        b = g.box
        for lab in np.unique(sub):
            if lab == 0:
                continue
            cb = _box_of(stats[lab])
            if area(cb) < area(g.box) and (cb[3] - cb[1]) < 2.6 * char_h:
                if overlap(cb, (x0 - pad, y0 - pad, x1 + pad, y1 + pad)) >= 0.8 * area(cb):
                    b = union(b, cb)
        out.append(Graphic(b, g.kind))
    return _merge_neighbours(_merge_overlapping(out), char_h)


def _aligned_bars(group: list[Box]) -> bool:
    """แท่งบาร์โค้ดยาวเท่า ๆ กันและเรียงเป็นแถวเดียว (ตัวอักษร l/I หลายตัวในข้อความไม่เข้าเงื่อนไขนี้)"""
    vertical = sum(1 for b in group if b[3] - b[1] > b[2] - b[0]) > len(group) / 2
    if vertical:
        lens = [b[3] - b[1] for b in group]
        tops = [b[1] for b in group]
    else:
        lens = [b[2] - b[0] for b in group]
        tops = [b[0] for b in group]
    med = statistics.median(lens)
    same = sum(1 for v in lens if abs(v - med) <= 0.2 * med)
    return same >= 0.7 * len(group) and (max(tops) - min(tops)) <= 0.5 * med


def _cluster(boxes: list[Box], gap: float) -> list[list[Box]]:
    """จับกลุ่มกรอบที่ห่างกันไม่เกิน gap (union-find)"""
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                parent[find(i)] = find(j)
    groups: dict[int, list[Box]] = {}
    for i, b in enumerate(boxes):
        groups.setdefault(find(i), []).append(b)
    return list(groups.values())


def _merge_overlapping(gs: list[Graphic]) -> list[Graphic]:
    changed = True
    while changed:
        changed = False
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                if overlap(gs[i].box, gs[j].box):
                    big = gs[i] if area(gs[i].box) >= area(gs[j].box) else gs[j]
                    kind = big.kind
                    gs[i] = Graphic(union(gs[i].box, gs[j].box), kind)
                    del gs[j]
                    changed = True
                    break
            if changed:
                break
    return gs


def _merge_neighbours(gs: list[Graphic], char_h: float) -> list[Graphic]:
    """ชิ้นส่วนของโลโก้เดียวกันที่วางเรียงกันในแถวเดียว (เช่น ตัวอักษรของโลโก้แยกเป็นก้อน) → รวมเป็นรูปเดียว"""
    gap = 2.5 * char_h
    changed = True
    while changed:
        changed = False
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                a, b = gs[i].box, gs[j].box
                vo = min(a[3], b[3]) - max(a[1], b[1])
                hgap = max(a[0], b[0]) - min(a[2], b[2])
                lim = 4 * char_h if gs[i].kind == gs[j].kind == "barcode" else gap
                if vo > 0.6 * min(a[3] - a[1], b[3] - b[1]) and hgap <= lim:
                    bar = sum(area(g.box) for g in (gs[i], gs[j]) if g.kind == "barcode")
                    kind = "barcode" if bar >= 0.4 * (area(a) + area(b)) else "image"
                    gs[i] = Graphic(union(a, b), kind)
                    del gs[j]
                    changed = True
                    break
            if changed:
                break
    return gs


# ---------------------------------------------------------------- ช่องติ๊ก

def find_checkboxes(mask: np.ndarray, char_h: float) -> list[Box]:
    """ช่องสี่เหลี่ยมกลวงขนาดราวตัวอักษร (☐ ในแบบฟอร์ม) — OCR อ่านเป็น "[ๆ]", "C1", "O" """
    n, labels, st, _c = _components(mask)
    out = []
    for i in range(1, n):
        x, y, w, h, cnt = (int(v) for v in st[i])
        if not (0.55 * char_h <= w <= 2.2 * char_h and 0.55 * char_h <= h <= 2.2 * char_h):
            continue
        if abs(w - h) > 0.25 * max(w, h) or cnt / (w * h) > 0.5:
            continue
        sub = labels[y:y + h, x:x + w] == i
        iy, ix = max(1, h // 4), max(1, w // 4)
        inner = sub[iy:h - iy, ix:w - ix]
        t = max(2, int(0.15 * min(w, h)))
        # ขอบครบทั้งสี่ด้าน (ตัวอักษรไทยกลวงอย่าง ก ถ ภ มีด้านที่เปิด)
        sides = (sub[:t].any(axis=0).mean(), sub[-t:].any(axis=0).mean(),
                 sub[:, :t].any(axis=1).mean(), sub[:, -t:].any(axis=1).mean())
        if inner.size and inner.mean() < 0.04 and min(sides) > 0.85:
            out.append((x, y, x + w, y + h))
    return out


# ---------------------------------------------------------------- รอยขอบกระดาษ

def edge_marks(mask: np.ndarray, char_h: float) -> list[Box]:
    """รอยที่ขอบซ้าย/ขวาของกระดาษ (เส้นสั้นจากเครื่องพิมพ์/รอยพับ/เงาขอบ) — ไม่ใช่เนื้อหา"""
    H, W = mask.shape
    band = int(W * 0.06)
    n, _l, stats, _c = _components(mask)
    out = []
    for i in range(1, n):
        b = _box_of(stats[i])
        if b[2] <= band or b[0] >= W - band:
            if (b[3] - b[1]) < 1.6 * char_h or (b[2] - b[0]) < 0.5 * char_h:
                out.append(b)
    return out


# ---------------------------------------------------------------- รวม

def find_solid_fills(mask: np.ndarray, char_h: float) -> list[Box]:
    """แถบทึบสีเข้มที่มีตัวอักษรสีขาวอยู่ข้างใน (หัวตารางพื้นดำ/แถบหัวข้อ) — ต้องกลับสีก่อนอ่าน"""
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((max(3, int(0.5 * char_h)),) * 2, np.uint8))
    n, labels, st, _c = _components(m)
    out = []
    for i in range(1, n):
        x, y, w, h, cnt = (int(v) for v in st[i])
        if w < 4 * char_h or h < 1.2 * char_h:
            continue
        sub = mask[y:y + h, x:x + w]
        fill = sub.mean()
        # ทึบ แต่มีรูขาว (ตัวอักษร) — รูปถ่าย/โลโก้ทึบมักไม่มีรูเรียงเป็นแถวแบบนี้
        if 0.55 <= fill <= 0.97 and (~sub).any(axis=1).mean() > 0.2:
            out.append((x, y, x + w, y + h))
    return out


def analyze(gray: Image.Image, color: Image.Image) -> PageAnalysis:
    gray, color, angle = deskew(gray, color)
    a = np.asarray(gray)
    mask = a <= ocr_thai.otsu_threshold(a)
    char_h = estimate_char_height(mask)

    # ตัวอักษรขาวบนพื้นเข้ม: กลับสีพื้นที่นั้น + วาดกรอบเส้นแทนขอบแถบ (ให้เส้นตารางยังต่อกัน)
    inverted = find_solid_fills(mask, char_h)
    if inverted:
        a = a.copy()
        for x0, y0, x1, y1 in inverted:
            a[y0:y1, x0:x1] = 255 - a[y0:y1, x0:x1]
            lw = max(2, int(0.12 * char_h))
            a[y0:y0 + lw, x0:x1] = 0
            a[y1 - lw:y1, x0:x1] = 0
            a[y0:y1, x0:x0 + lw] = 0
            a[y0:y1, x1 - lw:x1] = 0
        gray = Image.fromarray(a)
        mask = a <= ocr_thai.otsu_threshold(a)

    marks = edge_marks(mask, char_h)
    clean = mask.copy()
    for x0, y0, x1, y1 in marks:
        clean[y0:y1, x0:x1] = False

    horiz, vert = _line_masks(clean, char_h)
    grids = find_grids(horiz, vert, char_h)
    rules = lone_rules(horiz, grids, char_h)
    lines = horiz | vert
    grown = cv2.dilate(lines.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    no_lines = clean & ~grown

    leaders = find_leaders(no_lines, char_h)
    checkboxes = find_checkboxes(no_lines, char_h)
    for x0, y0, x1, y1 in checkboxes:
        no_lines[y0:y1, x0:x1] = False
    graphics = find_graphics(no_lines, char_h, exclude=[])

    text = a.copy()
    for x0, y0, x1, y1 in marks:
        text[y0:y1, x0:x1] = 255
    text[grown] = 255
    gp = int(0.3 * char_h)
    for g in graphics:
        x0, y0, x1, y1 = g.box
        text[max(0, y0 - gp):y1 + gp, max(0, x0 - gp):x1 + gp] = 255
    for ld in leaders:
        x0, y0, x1, y1 = ld.box
        text[max(0, y0 - 1):y1 + 1, max(0, x0 - 1):x1 + 1] = 255
    for x0, y0, x1, y1 in checkboxes:
        text[max(0, y0 - 1):y1 + 1, max(0, x0 - 1):x1 + 1] = 255

    ys, xs = np.nonzero(no_lines | lines)
    if len(xs):
        content = (int(np.percentile(xs, 0.2)), int(np.percentile(ys, 0.2)), int(np.percentile(xs, 99.8)), int(np.percentile(ys, 99.8)))
    else:
        content = (0, 0, a.shape[1], a.shape[0])
    return PageAnalysis(gray, color, Image.fromarray(text), char_h, grids, graphics, leaders, rules, content, checkboxes,
                        inverted, angle)


def median(values, default: float = 0.0) -> float:
    values = list(values)
    return statistics.median(values) if values else default
