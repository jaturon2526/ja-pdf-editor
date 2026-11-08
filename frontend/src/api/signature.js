// ลายเซ็น Electronic/Digital (/signature/{session})
import { BASE, fetchWithAuth, handle } from "./client.js";

// Electronic Sign — image_base64 คือรูปลายเซ็นที่ frontend เรนเดอร์เองแล้ว (พิมพ์ข้อความ/อัปโหลดรูป/
// วาดจากหน้าจอ — ดู ElectronicSignModal.jsx) ไม่ใส่ prefix "data:image/png;base64," (ตัดออกก่อนส่ง)
export async function electronicSign(sessionId, pageNumber, rect, imageBase64) {
  const res = await fetchWithAuth(`${BASE}/signature/${sessionId}/electronic`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_number: pageNumber, rect, image_base64: imageBase64 }),
  });
  return handle(res);
}

// Digital Sign — ต้องแนบไฟล์ p12/pfx จริง จึงส่งเป็น multipart (เหมือน insertImage ด้านบน) rect ส่งเป็น
// form field แยก x0/y0/x1/y1 คืน {status, is_signed, signature_type, signer_name} (ชื่อผู้เซ็นจาก certificate)
export async function digitalSign(sessionId, pageNumber, rect, pfxFile, password, reason, location, contact, name, imageFile) {
  const form = new FormData();
  form.append("page_number", pageNumber);
  form.append("x0", rect.x0);
  form.append("y0", rect.y0);
  form.append("x1", rect.x1);
  form.append("y1", rect.y1);
  form.append("password", password);
  if (reason) form.append("reason", reason);
  if (location) form.append("location", location);
  if (contact) form.append("contact", contact);
  if (name) form.append("name", name);
  form.append("file", pfxFile);
  if (imageFile) form.append("signature_image", imageFile);
  const res = await fetchWithAuth(`${BASE}/signature/${sessionId}/digital`, {
    method: "POST",
    body: form,
  });
  return handle(res);
}

// ตรวจไฟล์ใบรับรอง + รหัสผ่านก่อนวางตำแหน่ง — คืน { common_name, issuer, valid_to, warnings }
export async function checkCertificate(pfxFile, password) {
  const form = new FormData();
  form.append("password", password);
  form.append("file", pfxFile);
  const res = await fetchWithAuth(`${BASE}/signature/check-certificate`, { method: "POST", body: form });
  return handle(res);
}
