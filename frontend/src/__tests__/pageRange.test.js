import { describe, expect, it } from "vitest";
import { formatPageRange, parsePageRange } from "../utils/pageRange.js";

describe("pageRange", () => {
  it("แปลงช่วงหน้า", () => {
    expect(parsePageRange("1-3, 5", 9)).toEqual([1, 2, 3, 5]);
    expect(parsePageRange("8-", 9)).toEqual([8, 9]);
    expect(parsePageRange("-2", 9)).toEqual([1, 2]);
    expect(parsePageRange("๓–๑", 9)).toEqual([3, 2, 1]);
    expect(parsePageRange("", 9)).toEqual([]);
  });
  it("รูปแบบผิด/เกินจำนวนหน้า → null", () => {
    expect(parsePageRange("10", 9)).toBeNull();
    expect(parsePageRange("a", 9)).toBeNull();
    expect(parsePageRange("-", 9)).toBeNull();
  });
  it("ย่อชุดเลขหน้าเป็นช่วง", () => {
    expect(formatPageRange([5, 1, 2, 3, 9, 8])).toBe("1-3, 5, 8-9");
    expect(formatPageRange([])).toBe("");
  });
});
