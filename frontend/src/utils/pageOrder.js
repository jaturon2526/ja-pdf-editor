// ลำดับหน้าหลังย้าย — ตรงกับ backend pdf_service.reorder_pages (หน้าที่ไม่ย้ายเป็นแกน แทรกกลุ่มที่ย้ายเป็นก้อนเดียว)
// คืน array ที่ index = ตำแหน่งใหม่, ค่า = เลขหน้าเดิม (0-based)
export function reorderedPages(pageCount, pageNumbers, { targetPage = null, direction = null } = {}) {
  const moving = [...new Set(pageNumbers)].filter((p) => p >= 0 && p < pageCount).sort((a, b) => a - b);
  if (!moving.length) return Array.from({ length: pageCount }, (_, i) => i);
  const set = new Set(moving);
  const remaining = Array.from({ length: pageCount }, (_, i) => i).filter((i) => !set.has(i));
  let pos;
  if (direction) pos = remaining.filter((r) => r < moving[0]).length + (direction === "down" ? 1 : -1);
  else if (targetPage != null) pos = remaining.filter((r) => r < targetPage).length;
  else pos = remaining.length;
  pos = Math.max(0, Math.min(pos, remaining.length));
  return [...remaining.slice(0, pos), ...moving, ...remaining.slice(pos)];
}

/** ตำแหน่งใหม่ของหน้าที่ย้าย (ใช้ย้าย selection ในแผงหน้าเอกสารตามไปด้วย) */
export function newPositions(order, pages) {
  return pages.map((p) => order.indexOf(p)).filter((i) => i >= 0);
}
