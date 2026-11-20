// คำนวณตำแหน่งเส้นแบ่งตาราง (pt) ระหว่างแก้ — ใช้ทั้งแกน x (คอลัมน์) และแกน y (แถว) · backend วาดจริง (edit_service/tables.py)
export const MIN_CELL_PT = 6;
const MM_PER_PT = 25.4 / 72;

export const ptToMm = (pt) => Math.round(pt * MM_PER_PT * 10) / 10;
export const mmToPt = (mm) => mm / MM_PER_PT;

export const translate = (lines, d) => lines.map((v) => v + d);

/** ลากเส้นด้านใน i: ช่องสองข้างเปลี่ยน ความกว้างรวมเท่าเดิม (ช่องละไม่น้อยกว่า MIN_CELL_PT) */
export function moveInnerLine(lines, i, value) {
  if (i <= 0 || i >= lines.length - 1) return lines;
  const v = Math.min(lines[i + 1] - MIN_CELL_PT, Math.max(lines[i - 1] + MIN_CELL_PT, value));
  return lines.map((x, k) => (k === i ? v : x));
}

/** ลากขอบนอกด้านปลาย: ขยาย/ย่อทุกช่องตามสัดส่วนเดิม (จุดเริ่มอยู่ที่เดิม) */
export function scaleTo(lines, end) {
  const start = lines[0];
  const span = lines.at(-1) - start;
  const kMin = MIN_CELL_PT / Math.min(...sizes(lines)); // ช่องที่แคบสุดต้องไม่ต่ำกว่าขั้นต่ำ
  const k = Math.max((end - start) / span, kMin);
  return lines.map((v) => start + (v - start) * k);
}

/** ตั้งขนาดช่อง i (pt) — ช่องถัดไปเลื่อนตาม (ความกว้างรวมเปลี่ยน) */
export function setSize(lines, i, size) {
  const d = Math.max(MIN_CELL_PT, size) - (lines[i + 1] - lines[i]);
  return lines.map((v, k) => (k > i ? v + d : v));
}

/** ทุกช่องเท่ากัน (ขอบนอกอยู่ที่เดิม) */
export function equalize(lines) {
  const n = lines.length - 1;
  const step = (lines.at(-1) - lines[0]) / n;
  return lines.map((_, k) => lines[0] + step * k);
}

export const sizes = (lines) => lines.slice(1).map((v, k) => v - lines[k]);
