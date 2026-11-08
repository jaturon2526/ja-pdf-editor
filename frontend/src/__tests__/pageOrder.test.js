import { describe, expect, it } from "vitest";
import { newPositions, reorderedPages } from "../utils/pageOrder.js";

describe("reorderedPages (ตรงกับ backend reorder_pages)", () => {
  it("drag one page before another", () => {
    expect(reorderedPages(5, [4], { targetPage: 1 })).toEqual([0, 4, 1, 2, 3]);
  });
  it("drop at end", () => {
    expect(reorderedPages(4, [0], { targetPage: null })).toEqual([1, 2, 3, 0]);
  });
  it("move non-contiguous group down as a block", () => {
    expect(reorderedPages(6, [1, 3], { direction: "down" })).toEqual([0, 2, 1, 3, 4, 5]);
  });
  it("selection follows moved pages", () => {
    const pages = [2];
    const order = reorderedPages(5, pages, { direction: "down" });
    expect(newPositions(order, pages)).toEqual([3]);
    expect(newPositions(reorderedPages(5, [3], { direction: "down" }), [3])).toEqual([4]);
  });
});
