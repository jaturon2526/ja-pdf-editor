// ฟังก์ชันคำนวณระยะตัดขอบหน้ากระดาษ (Crop Page, v1.44.0) — แปลง มม. ↔ pt, คุมขอบขั้นต่ำ, คำนวณการลากจุดจับ
import { parsePageRange } from "./pageRange.js";

export const PT_PER_MM = 72 / 25.4;
export const MIN_CROP_PT = 36; // 0.5 นิ้ว ≈ 12.7 มม.

export function ptToMm(pt) {
  return Math.round((pt / PT_PER_MM) * 10) / 10;
}

export function mmToPt(mm) {
  const n = Number(mm);
  if (!Number.isFinite(n) || n < 0) return 0;
  return n * PT_PER_MM;
}

export function clampMargins(margins, pageWidthPt, pageHeightPt) {
  const maxW = Math.max(0, pageWidthPt - MIN_CROP_PT);
  const maxH = Math.max(0, pageHeightPt - MIN_CROP_PT);

  let left = Math.max(0, Math.min(Number(margins.left) || 0, maxW));
  let right = Math.max(0, Math.min(Number(margins.right) || 0, maxW - left));
  let top = Math.max(0, Math.min(Number(margins.top) || 0, maxH));
  let bottom = Math.max(0, Math.min(Number(margins.bottom) || 0, maxH - top));

  return {
    left: Math.round(left * 100) / 100,
    top: Math.round(top * 100) / 100,
    right: Math.round(right * 100) / 100,
    bottom: Math.round(bottom * 100) / 100,
  };
}

/**
 * อัปเดตระยะขอบเมื่อผู้ใช้ลากจุดจับ ("n"|"s"|"e"|"w"|"nw"|"ne"|"sw"|"se")
 * ด้วยระยะเปลี่ยนแปลง (dxPt, dyPt) จากจุดเริ่มต้นตอนกด
 */
export function applyHandleDrag(startMargins, handle, dxPt, dyPt, pageWidthPt, pageHeightPt) {
  const next = { ...startMargins };
  if (handle.includes("w")) {
    const maxLeft = Math.max(0, pageWidthPt - startMargins.right - MIN_CROP_PT);
    next.left = Math.max(0, Math.min(startMargins.left + dxPt, maxLeft));
  }
  if (handle.includes("e")) {
    const maxRight = Math.max(0, pageWidthPt - startMargins.left - MIN_CROP_PT);
    next.right = Math.max(0, Math.min(startMargins.right - dxPt, maxRight));
  }
  if (handle.includes("n")) {
    const maxTop = Math.max(0, pageHeightPt - startMargins.bottom - MIN_CROP_PT);
    next.top = Math.max(0, Math.min(startMargins.top + dyPt, maxTop));
  }
  if (handle.includes("s")) {
    const maxBottom = Math.max(0, pageHeightPt - startMargins.top - MIN_CROP_PT);
    next.bottom = Math.max(0, Math.min(startMargins.bottom - dyPt, maxBottom));
  }
  return clampMargins(next, pageWidthPt, pageHeightPt);
}

/**
 * แปลงขอบเขตที่ผู้ใช้เลือกเป็นรายการเลขหน้า 0-based
 * คืน { pages: number[], error: string | null }
 */
export function resolveCropPages(scope, currentPage, pageCount, rangeText) {
  if (!pageCount || pageCount < 1) return { pages: [], error: "ไม่พบหน้าเอกสาร" };
  if (scope === "current") return { pages: [currentPage], error: null };
  if (scope === "all") return { pages: Array.from({ length: pageCount }, (_, i) => i), error: null };
  const parsed = parsePageRange(rangeText, pageCount);
  if (!parsed || parsed.length === 0) {
    return { pages: [], error: `กรุณาระบุช่วงหน้าให้ถูกต้อง (1–${pageCount}) เช่น 1-3, 5` };
  }
  return { pages: parsed.map((p) => p - 1), error: null };
}
