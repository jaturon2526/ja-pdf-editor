import { describe, expect, it } from "vitest";
import {
  computePageLayouts,
  createPageCache,
  findVisiblePageRange,
  PAGE_GAP_PX,
} from "../utils/continuousScroll.js";

describe("continuousScroll utilities", () => {
  it("computes stacked page layouts with zoom and gaps", () => {
    const { layouts, totalHeight } = computePageLayouts([[500, 700], [500, 800], [600, 400]], 1.5, 16);
    expect(layouts).toHaveLength(3);
    expect(layouts[0]).toEqual({ index: 0, width: 750, height: 1050, top: 0, bottom: 1050 });
    expect(layouts[1]).toEqual({ index: 1, width: 750, height: 1200, top: 1066, bottom: 2266 });
    expect(layouts[2]).toEqual({ index: 2, width: 900, height: 600, top: 2282, bottom: 2882 });
    expect(totalHeight).toBe(2882);
  });

  it("finds visible page range with ±1 overscan and dominant page", () => {
    const sizes = Array.from({ length: 10 }, () => [600, 800]);
    const { layouts } = computePageLayouts(sizes, 1, PAGE_GAP_PX);

    // At top of document (viewport 900px) → page 0 dominates, overscan includes page 1
    const r0 = findVisiblePageRange(layouts, 0, 900, 1);
    expect(r0.dominantPage).toBe(0);
    expect(r0.start).toBe(0);
    expect(r0.end).toBe(2); // page 0 + top of page 1 visible → overscan +1 = page 2

    // Scrolled squarely onto page 4 (top ~ 4 * 816 = 3264)
    const r4 = findVisiblePageRange(layouts, 3300, 800, 1);
    expect(r4.dominantPage).toBe(4);
    expect(r4.start).toBe(3);
    expect(r4.end).toBe(5);
  });

  it("evicts least-recently-used pages when LRU cache exceeds maxEntries", () => {
    const cache = createPageCache(3);
    cache.set(0, "p0");
    cache.set(1, "p1");
    cache.set(2, "p2");
    expect(cache.get(0)).toBe("p0"); // touch 0 so 1 becomes oldest
    cache.set(3, "p3");
    expect(cache.size).toBe(3);
    expect(cache.has(1)).toBe(false);
    expect(cache.has(0)).toBe(true);
    expect(cache.has(2)).toBe(true);
    expect(cache.has(3)).toBe(true);
  });
});
