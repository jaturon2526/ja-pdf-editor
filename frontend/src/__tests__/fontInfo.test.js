import { describe, expect, it } from "vitest";
import { embedLabel, embedTone, pagesLabel, sizeLabel, styleLabel } from "../utils/fontInfo.js";

describe("fontInfo", () => {
  it("ย่อช่วงหน้า", () => {
    expect(pagesLabel([1, 2, 3, 5, 7, 8, 9])).toBe("1–3, 5, 7–9");
    expect(pagesLabel([4])).toBe("4");
    expect(pagesLabel([])).toBe("");
  });
  it("สถานะการฝัง", () => {
    expect(embedLabel({ embedded: true, subset: true })).toContain("เฉพาะตัวอักษรที่ใช้");
    expect(embedLabel({ embedded: false, base14: true })).toContain("ฟอนต์มาตรฐาน");
    expect(embedTone({ embedded: false, base14: false })).toBe("warn");
  });
  it("ขนาดและสไตล์", () => {
    expect(sizeLabel(10.5)).toBe("10.5 pt");
    expect(sizeLabel(12)).toBe("12 pt");
    expect(styleLabel({ bold: true, italic: true })).toBe("ตัวหนาเอียง");
  });
});
