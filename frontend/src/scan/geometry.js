// เรขาคณิตของการสแกน (ใช้ทั้งใน worker และหน้าจอ) — มุมเป็นพิกัดสัดส่วน 0..1 ของภาพ [{x,y} x4] เรียง tl, tr, br, bl

export const A4_LONG_PX = 2339; // ด้านยาว A4 ที่ 200 dpi (ค่าเดียวกับ SCAN_DPI ฝั่ง backend)

/** เรียงจุด 4 จุดเป็น บนซ้าย, บนขวา, ล่างขวา, ล่างซ้าย */
export function orderCorners(points) {
  const pts = points.map((p) => ({ x: p.x, y: p.y }));
  const cx = pts.reduce((s, p) => s + p.x, 0) / 4;
  const cy = pts.reduce((s, p) => s + p.y, 0) / 4;
  pts.sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx)); // เรียงตามมุม เริ่มจากซ้ายบนวนตามเข็ม
  // หาจุดบนซ้าย (x+y น้อยสุด) แล้วหมุนให้อยู่ตัวแรก
  let start = 0;
  pts.forEach((p, i) => { if (p.x + p.y < pts[start].x + pts[start].y) start = i; });
  return [0, 1, 2, 3].map((i) => pts[(start + i) % 4]);
}

export const FULL_FRAME = [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }];
export const INSET_FRAME = [{ x: 0.08, y: 0.08 }, { x: 0.92, y: 0.08 }, { x: 0.92, y: 0.92 }, { x: 0.08, y: 0.92 }];

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/** ขนาดภาพหลังดัด (px) จากมุมในพิกัดภาพจริง — ด้านยาวไม่เกิน A4 @200dpi และไม่ขยายเกิน 1.5 เท่า */
export function warpSize(cornersPx, longSide = A4_LONG_PX) {
  const [tl, tr, br, bl] = cornersPx;
  const w = Math.max(dist(tl, tr), dist(bl, br));
  const h = Math.max(dist(tl, bl), dist(tr, br));
  const scale = Math.min(1.5, longSide / Math.max(w, h, 1));
  return { width: Math.max(1, Math.round(w * scale)), height: Math.max(1, Math.round(h * scale)) };
}

/** พื้นที่ของรูป 4 เหลี่ยม (สัดส่วนของภาพ) — ใช้ตัดสินว่าเจอเอกสารจริง */
export function quadArea(c) {
  let s = 0;
  for (let i = 0; i < 4; i++) {
    const a = c[i];
    const b = c[(i + 1) % 4];
    s += a.x * b.y - b.x * a.y;
  }
  return Math.abs(s) / 2;
}

/** ค่าเฉลี่ยถ่วงน้ำหนักของมุม (ทำให้กรอบสดนิ่ง ไม่สั่นตามเฟรม) */
export function smoothCorners(prev, next, alpha = 0.5) {
  if (!prev) return next;
  return next.map((p, i) => ({ x: prev[i].x + (p.x - prev[i].x) * alpha, y: prev[i].y + (p.y - prev[i].y) * alpha }));
}

/** ชื่อไฟล์แบบกล้องมือถือ: Scan_20261025_152133 (เวลาเครื่องผู้ใช้) */
export function scanFilename(date = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `Scan_${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}_${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`;
}
