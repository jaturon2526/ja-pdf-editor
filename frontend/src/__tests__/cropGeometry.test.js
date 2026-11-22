import { describe, expect, it } from "vitest";
import {
  MIN_CROP_PT,
  applyHandleDrag,
  clampMargins,
  mmToPt,
  ptToMm,
  resolveCropPages,
} from "../utils/cropGeometry.js";

describe("cropGeometry", () => {
  it("converts between mm and pt accurately", () => {
    expect(ptToMm(72)).toBeCloseTo(25.4, 1);
    expect(mmToPt(25.4)).toBeCloseTo(72, 1);
    expect(mmToPt(-5)).toBe(0);
    expect(mmToPt("abc")).toBe(0);
  });

  it("clamps margins so remaining page is at least MIN_CROP_PT", () => {
    const clamped = clampMargins({ left: 400, top: 500, right: 300, bottom: 500 }, 595, 842);
    expect(595 - clamped.left - clamped.right).toBeGreaterThanOrEqual(MIN_CROP_PT - 0.01);
    expect(842 - clamped.top - clamped.bottom).toBeGreaterThanOrEqual(MIN_CROP_PT - 0.01);
  });

  it("applies handle drags on corners and edges", () => {
    const start = { left: 20, top: 20, right: 20, bottom: 20 };
    const afterNw = applyHandleDrag(start, "nw", 15, 10, 595, 842);
    expect(afterNw.left).toBeCloseTo(35, 1);
    expect(afterNw.top).toBeCloseTo(30, 1);
    expect(afterNw.right).toBeCloseTo(20, 1);
    expect(afterNw.bottom).toBeCloseTo(20, 1);

    const afterSe = applyHandleDrag(start, "se", -10, -25, 595, 842);
    expect(afterSe.right).toBeCloseTo(30, 1);
    expect(afterSe.bottom).toBeCloseTo(45, 1);
  });

  it("resolves current, all, and custom page ranges", () => {
    expect(resolveCropPages("current", 1, 5, "")).toEqual({ pages: [1], error: null });
    expect(resolveCropPages("all", 0, 3, "")).toEqual({ pages: [0, 1, 2], error: null });
    expect(resolveCropPages("range", 0, 5, "1-2, 4")).toEqual({ pages: [0, 1, 3], error: null });
    expect(resolveCropPages("range", 0, 5, "99").error).toBeTruthy();
  });
});
