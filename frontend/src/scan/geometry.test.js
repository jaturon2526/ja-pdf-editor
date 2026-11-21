import { describe, expect, it } from "vitest";
import { A4_LONG_PX, nearestCornerIndex, orderCorners, quadArea, scanFilename, shiftCorner, smoothCorners, warpSize } from "./geometry.js";

describe("orderCorners", () => {
  it("เรียงเป็น บนซ้าย บนขวา ล่างขวา ล่างซ้าย ไม่ว่าลำดับเข้ามาเป็นอย่างไร", () => {
    const tl = { x: 0.1, y: 0.12 }, tr = { x: 0.9, y: 0.1 }, br = { x: 0.95, y: 0.9 }, bl = { x: 0.05, y: 0.88 };
    expect(orderCorners([br, tl, bl, tr])).toEqual([tl, tr, br, bl]);
    expect(orderCorners([bl, br, tr, tl])).toEqual([tl, tr, br, bl]);
  });
});

describe("warpSize", () => {
  it("ด้านยาวเท่า A4 @200dpi และคงสัดส่วน", () => {
    const s = warpSize([{ x: 0, y: 0 }, { x: 2100, y: 0 }, { x: 2100, y: 2970 }, { x: 0, y: 2970 }]);
    expect(s.height).toBe(A4_LONG_PX);
    expect(s.width / s.height).toBeCloseTo(2100 / 2970, 2);
  });
  it("ภาพเล็กขยายไม่เกิน 1.5 เท่า", () => {
    const s = warpSize([{ x: 0, y: 0 }, { x: 400, y: 0 }, { x: 400, y: 300 }, { x: 0, y: 300 }]);
    expect(s).toEqual({ width: 600, height: 450 });
  });
});

it("quadArea ของทั้งภาพ = 1", () => {
  expect(quadArea([{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }])).toBe(1);
});

it("smoothCorners เข้าใกล้ค่าใหม่ตาม alpha", () => {
  const a = [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }];
  const b = a.map((p) => ({ x: p.x + 0.2, y: p.y }));
  expect(smoothCorners(a, b, 0.5)[0]).toEqual({ x: 0.1, y: 0 });
  expect(smoothCorners(null, b)).toBe(b);
});

it("scanFilename ตามเวลาเครื่องแบบกล้องมือถือ", () => {
  expect(scanFilename(new Date(2026, 9, 25, 15, 21, 3))).toBe("Scan_20261025_152103");
});

describe("nearestCornerIndex & shiftCorner", () => {
  const pts = [{ x: 28, y: 28 }, { x: 320, y: 28 }, { x: 320, y: 480 }, { x: 28, y: 480 }];

  it("แตะถัดเข้ามาในจอห่างจากมุมบนซ้าย 60px ยังจับมุมบนซ้ายได้โดยไม่ต้องจิ้มตรงจุด", () => {
    expect(nearestCornerIndex(pts, { x: 85, y: 45 }, 140)).toBe(0);
    expect(nearestCornerIndex(pts, { x: 200, y: 250 }, 50)).toBe(-1);
  });

  it("shiftCorner เลื่อนมุมตามระยะนิ้วลากโดยไม่กระโดดไปตำแหน่งนิ้ว และจำกัดอยู่ใน 0..1", () => {
    const layout = { ox: 28, oy: 28, w: 300, h: 400 };
    const moved = shiftCorner({ x: 0.1, y: 0.1 }, { dx: -15, dy: 40 }, layout);
    expect(moved.x).toBeCloseTo(0.05, 5);
    expect(moved.y).toBeCloseTo(0.2, 5);
    const clamped = shiftCorner({ x: 0.05, y: 0.95 }, { dx: -100, dy: 100 }, layout);
    expect(clamped).toEqual({ x: 0, y: 1 });
  });
});
