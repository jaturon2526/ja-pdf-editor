// ค่าคอนฟิกสาธารณะจาก backend (GET /config/public — ไม่ต้อง login): ปุ่ม Google/LINE, การสมัครสมาชิก, โดเมนอีเมลที่สมัครได้
// image เดียวกันใช้ได้ทั้งเว็บสาธารณะ (public) และติดตั้งในองค์กร (onprem) — ค่ามาจาก .env ของ backend ไม่ได้ฝังตอน build
import { BASE, handlePublic } from "./client.js";

let cached = null;

/** คืน config (cache ตลอดอายุหน้า) — ถ้าเรียกไม่สำเร็จ คืน null ให้ผู้เรียกใช้ค่าสำรอง */
export function getPublicConfig() {
  if (!cached) {
    cached = fetch(`${BASE}/config/public`)
      .then(handlePublic)
      .catch(() => {
        cached = null; // ครั้งหน้าลองใหม่
        return null;
      });
  }
  return cached;
}

/** อีเมลนี้สมัครได้ตามโดเมนที่กำหนดไหม (ว่าง = ทุกโดเมน) — backend ตรวจซ้ำเสมอ */
export function emailDomainAllowed(email, domains) {
  if (!domains || domains.length === 0) return true;
  const domain = String(email || "").trim().toLowerCase().split("@").pop();
  return domains.includes(domain);
}
