// continuousScroll.js — คำนวณตำแหน่งหน้า, ช่วงหน้าที่มองเห็นในจอ (Virtual Scroll), และ LRU cache สำหรับภาพหน้า

export const PAGE_GAP_PX = 16;
export const CANVAS_TOP_PADDING_PX = 28;

/**
 * คำนวณพิกัดแนวตั้ง (top/bottom) และขนาดแสดงผล (px) ของทุกหน้าในโหมดเลื่อนต่อเนื่อง
 * @param {Array<[number, number]>} pageSizes — [[widthPt, heightPt], ...]
 * @param {number} zoom
 * @param {number} [gap=PAGE_GAP_PX]
 */
export function computePageLayouts(pageSizes, zoom, gap = PAGE_GAP_PX) {
  const safeZoom = Number.isFinite(zoom) && zoom > 0 ? zoom : 1;
  const layouts = [];
  let cursorY = 0;
  for (let i = 0; i < (pageSizes?.length || 0); i += 1) {
    const [wPt, hPt] = pageSizes[i] || [595, 842];
    const width = Math.max(1, (wPt > 1 ? wPt : 595) * safeZoom);
    const height = Math.max(1, (hPt > 1 ? hPt : 842) * safeZoom);
    const top = cursorY;
    const bottom = top + height;
    layouts.push({ index: i, width, height, top, bottom });
    cursorY = bottom + gap;
  }
  const totalHeight = layouts.length > 0 ? layouts.at(-1).bottom : 0;
  return { layouts, totalHeight };
}

/**
 * หาช่วงหน้า (start..end) ที่ซ้อนกับ viewport ปัจจุบัน (+ overscan รอบข้าง)
 * และ dominantPage = หน้าที่มีพื้นที่ปรากฏในจอมากที่สุด (ใช้อัปเดต currentPage อัตโนมัติตอนเลื่อน)
 */
export function findVisiblePageRange(layouts, scrollTop, viewportHeight, overscan = 1) {
  if (!layouts || layouts.length === 0) {
    return { start: 0, end: -1, dominantPage: 0 };
  }
  const viewTop = Math.max(0, scrollTop - CANVAS_TOP_PADDING_PX);
  const viewBottom = viewTop + Math.max(1, viewportHeight);

  let firstVisible = -1;
  let lastVisible = -1;
  let dominantPage = 0;
  let bestOverlap = -1;

  for (let i = 0; i < layouts.length; i += 1) {
    const p = layouts[i];
    if (p.bottom < viewTop) continue;
    if (p.top > viewBottom) break;
    if (firstVisible === -1) firstVisible = i;
    lastVisible = i;
    const overlap = Math.min(p.bottom, viewBottom) - Math.max(p.top, viewTop);
    if (overlap > bestOverlap) {
      bestOverlap = overlap;
      dominantPage = i;
    }
  }

  if (firstVisible === -1) {
    // scroll อยู่เลยหน้าสุดท้ายหรือก่อนหน้าแรก
    const idx = viewTop >= layouts.at(-1).bottom ? layouts.length - 1 : 0;
    firstVisible = idx;
    lastVisible = idx;
    dominantPage = idx;
  }

  return {
    start: Math.max(0, firstVisible - overscan),
    end: Math.min(layouts.length - 1, lastVisible + overscan),
    dominantPage,
  };
}

/**
 * LRU Cache ขนาดจำกัดสำหรับภาพหน้า PDF ในหน่วยความจำเบราว์เซอร์
 * กันใช้ RAM เยอะเกินไปเมื่อเปิดไฟล์ยาวหลายร้อยหน้า
 */
export function createPageCache(maxEntries = 15) {
  const map = new Map();
  return {
    get(key) {
      if (!map.has(key)) return undefined;
      const val = map.get(key);
      map.delete(key);
      map.set(key, val);
      return val;
    },
    set(key, value) {
      if (map.has(key)) map.delete(key);
      map.set(key, value);
      while (map.size > maxEntries) {
        const oldestKey = map.keys().next().value;
        map.delete(oldestKey);
      }
    },
    has(key) {
      return map.has(key);
    },
    delete(key) {
      map.delete(key);
    },
    clear() {
      map.clear();
    },
    toObject() {
      return Object.fromEntries(map.entries());
    },
    get size() {
      return map.size;
    },
  };
}
