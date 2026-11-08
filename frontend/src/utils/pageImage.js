// ภาพหน้าเอกสารจาก backend เป็น base64 — JPEG (ค่าเริ่มต้น เร็วกว่า) หรือ PNG ดูจากหัวไฟล์ ("/9j/" = JPEG)
export function pageImageSrc(b64) {
  if (!b64) return "";
  return `data:${b64.startsWith("/9j/") ? "image/jpeg" : "image/png"};base64,${b64}`;
}
