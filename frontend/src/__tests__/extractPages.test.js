import { describe, expect, it } from "vitest";
import { parsePageRange, rangeLabel } from "../components/ExtractPagesModal.jsx";

describe("parsePageRange", () => {
  it.each([
    ["1,2,4-6", [1, 2, 4, 5, 6]],
    ["5, 1-3", [5, 1, 2, 3]],
    ["6-4", [6, 5, 4]],
    ["1-3,2", [1, 2, 3]],
    ["2–4", [2, 3, 4]],
    ["-3", [1, 2, 3]],
    ["10-", [10, 11, 12]],
    ["๑-๓", [1, 2, 3]],
  ])("%s", (text, pages) => {
    expect(parsePageRange(text, 12)).toEqual({ pages });
  });
  it.each(["0", "13", "abc", "1-3-5", "-", "1.5", "", " , "])("rejects %j", (text) => {
    expect(parsePageRange(text, 12).error).toBeTruthy();
  });
  it("says which page is missing", () => {
    expect(parsePageRange("1, 20", 12).error).toBe("ไม่มีหน้า 20 (เอกสารมี 12 หน้า)");
  });
});

describe("rangeLabel", () => {
  it("compresses runs", () => {
    expect(rangeLabel([1, 2, 3, 5, 9, 8])).toBe("1-3, 5, 9, 8");
  });
});
