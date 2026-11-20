import { describe, expect, it } from "vitest";
import { MIN_CELL_PT, equalize, mmToPt, moveInnerLine, ptToMm, scaleTo, setSize, sizes, translate } from "../utils/tableGeometry.js";

describe("tableGeometry", () => {
  const xs = [50, 100, 250, 350];
  it("ลากเส้นด้านใน: ความกว้างรวมเท่าเดิม และไม่แคบกว่าขั้นต่ำ", () => {
    expect(moveInnerLine(xs, 1, 80)).toEqual([50, 80, 250, 350]);
    expect(moveInnerLine(xs, 1, 10)).toEqual([50, 50 + MIN_CELL_PT, 250, 350]);
    expect(moveInnerLine(xs, 0, 10)).toBe(xs);
  });
  it("ย่อขยายทั้งตารางตามสัดส่วน", () => {
    expect(scaleTo(xs, 650)).toEqual([50, 150, 450, 650]);
    expect(sizes(scaleTo(xs, 0)).every((s) => s >= MIN_CELL_PT - 1e-9)).toBe(true);
  });
  it("ตั้งขนาดช่อง / เท่ากัน / เลื่อน", () => {
    expect(setSize(xs, 1, 200)).toEqual([50, 100, 300, 400]);
    expect(equalize(xs)).toEqual([50, 150, 250, 350]);
    expect(translate(xs, 10)).toEqual([60, 110, 260, 360]);
  });
  it("แปลงหน่วย", () => {
    expect(ptToMm(72)).toBeCloseTo(25.4, 5);
    expect(Math.round(mmToPt(25.4))).toBe(72);
  });
});
