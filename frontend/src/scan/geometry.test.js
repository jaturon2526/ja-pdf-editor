import { describe, expect, it } from "vitest";
import { A4_LONG_PX, orderCorners, quadArea, scanFilename, smoothCorners, warpSize } from "./geometry.js";

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
