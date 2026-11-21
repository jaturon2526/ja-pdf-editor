import { describe, expect, it, vi } from "vitest";
import {
  STAMP_ANGLES,
  STAMP_COLORS,
  STAMP_OPACITIES,
  STAMP_PRESETS,
  drawStamp,
  formatThaiDate,
} from "../utils/stampRenderer.js";

describe("stampRenderer", () => {
  it("formats Thai Buddhist Era date correctly", () => {
    expect(formatThaiDate(new Date(2026, 0, 5))).toBe("5 ม.ค. 2569");
    expect(formatThaiDate(new Date(2026, 10, 21))).toBe("21 พ.ย. 2569");
    expect(formatThaiDate(new Date(2025, 11, 31))).toBe("31 ธ.ค. 2568");
  });

  it("exposes expected Thai office stamp presets and style options", () => {
    const labels = STAMP_PRESETS.map((p) => p.label);
    expect(labels).toContain("สำเนาถูกต้อง");
    expect(labels).toContain("อนุมัติแล้ว");
    expect(labels).toContain("จ่ายแล้ว");
    expect(labels).toContain("ลับ");
    expect(labels).toContain("ด่วนที่สุด");
    expect(labels).toContain("ร่าง (DRAFT)");
    expect(STAMP_COLORS.length).toBeGreaterThanOrEqual(5);
    expect(STAMP_ANGLES.map((a) => a.value)).toEqual([0, -12, -20]);
    expect(STAMP_OPACITIES.map((o) => o.value)).toEqual([0.7, 0.85, 1]);
  });

  it("draws stamp border and text onto canvas context without throwing", () => {
    const ctx = {
      clearRect: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      translate: vi.fn(),
      rotate: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      quadraticCurveTo: vi.fn(),
      closePath: vi.fn(),
      stroke: vi.fn(),
      fillText: vi.fn(),
      measureText: vi.fn((t) => ({ width: t.length * 14 })),
      globalAlpha: 1,
      strokeStyle: "",
      fillStyle: "",
      lineWidth: 1,
      font: "",
      textAlign: "",
      textBaseline: "",
    };

    drawStamp(ctx, 720, 380, {
      text: "สำเนาถูกต้อง",
      subText: "21 พ.ย. 2569",
      color: "#1d4ed8",
      angleDeg: -12,
      opacity: 0.85,
    });

    expect(ctx.clearRect).toHaveBeenCalledWith(0, 0, 720, 380);
    expect(ctx.fillText).toHaveBeenCalledWith("สำเนาถูกต้อง", 0, expect.any(Number));
    expect(ctx.fillText).toHaveBeenCalledWith("21 พ.ย. 2569", 0, expect.any(Number));
    expect(ctx.stroke).toHaveBeenCalledTimes(3); // outer border + inner border + divider
  });

  it("clears canvas and skips drawing when text is blank", () => {
    const ctx = {
      clearRect: vi.fn(),
      save: vi.fn(),
      fillText: vi.fn(),
    };
    drawStamp(ctx, 480, 220, { text: "   " });
    expect(ctx.clearRect).toHaveBeenCalledWith(0, 0, 480, 220);
    expect(ctx.save).not.toHaveBeenCalled();
    expect(ctx.fillText).not.toHaveBeenCalled();
  });
});
