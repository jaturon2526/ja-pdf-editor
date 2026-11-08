// ดันเมนู/popup ที่วางแบบ position: fixed ตามตำแหน่งเมาส์ ให้อยู่ในหน้าจอเสมอ
// (เดิมคลิกขวาใกล้ขอบล่าง/ขวา เมนูจะล้นออกนอกจอ — Safari เลื่อนกล่องหลักของแอปซึ่งเป็น overflow:hidden
// ตามไปด้วย ทำให้แถบเมนูด้านบนถูกดันหายไปครึ่งหนึ่งและแถบสถานะด้านล่างหลุดออกนอกจอ)
export function clampToViewport(rect, viewportWidth, viewportHeight, margin = 8) {
  let { left, top } = rect;
  if (left + rect.width > viewportWidth - margin) left = viewportWidth - margin - rect.width;
  if (top + rect.height > viewportHeight - margin) top = viewportHeight - margin - rect.height;
  return { left: Math.max(margin, left), top: Math.max(margin, top) };
}

export function keepInViewport(el, margin = 8) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  const { left, top } = clampToViewport(
    { left: r.left, top: r.top, width: r.width, height: r.height },
    window.innerWidth,
    window.innerHeight,
    margin,
  );
  if (left !== r.left) el.style.left = `${left}px`;
  if (top !== r.top) el.style.top = `${top}px`;
}

// คืนค่า scroll ของกล่องหลักที่ตั้งใจให้เลื่อนไม่ได้ (overflow: hidden/clip) กลับเป็น 0 ทันทีถ้าถูกเลื่อน
export function resetUnintendedScroll(e) {
  const el = e.currentTarget;
  if (el.scrollTop !== 0) el.scrollTop = 0;
  if (el.scrollLeft !== 0) el.scrollLeft = 0;
}

// หน้าตาแบบมือถือ: จอแคบกว่า 768px หรือจอสัมผัสที่เตี้ย (มือถือแนวนอน กว้าง 800–930px แต่สูงแค่ ~390px)
// ต้องตรงกับ @custom-variant phone / desk ใน tailwind.css
export const PHONE_LAYOUT_QUERY = "(max-width: 767px), (pointer: coarse) and (max-height: 500px)";

export function isPhoneLayout() {
  if (typeof window === "undefined") return false;
  if (typeof window.matchMedia === "function") return window.matchMedia(PHONE_LAYOUT_QUERY).matches;
  return window.innerWidth < 768;
}
