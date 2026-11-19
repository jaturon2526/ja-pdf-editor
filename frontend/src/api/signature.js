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
// pfxFile = ไฟล์ .p12/.pfx (File) หรือ { certificateId } = ใบรับรองที่บันทึกไว้บนระบบ
function appendCertificate(form, pfxFile) {
  if (pfxFile && typeof pfxFile === "object" && "certificateId" in pfxFile) form.append("certificate_id", pfxFile.certificateId);
  else form.append("file", pfxFile);
}

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
  appendCertificate(form, pfxFile);
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
  appendCertificate(form, pfxFile);
  const res = await fetchWithAuth(`${BASE}/signature/check-certificate`, { method: "POST", body: form });
  return handle(res);
}

// ---------- ใบรับรองที่บันทึกไว้บนระบบ (ระบบไม่เก็บรหัสผ่าน — ต้องกรอกทุกครั้งที่ใช้/ลบ) ----------
export async function listCertificates() {
  return handle(await fetchWithAuth(`${BASE}/signature/certificates`));
}

export async function uploadCertificate(file, password, label) {
  const form = new FormData();
  form.append("file", file);
  form.append("password", password);
  if (label) form.append("label", label);
  return handle(await fetchWithAuth(`${BASE}/signature/certificates`, { method: "POST", body: form }));
}

export async function deleteCertificate(id, password) {
  const res = await fetchWithAuth(`${BASE}/signature/certificates/${id}/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (res.status === 204) return;
  return handle(res);
}

// ---------- ปลดล็อกใบรับรองด้วย passkey (utils/certPasskey.js เข้ารหัสรหัสผ่านในเบราว์เซอร์ — server ถอดไม่ได้) ----------
export async function prepareCertificatePasskey(id) {
  const res = await fetchWithAuth(`${BASE}/signature/certificates/${id}/passkeys/options`, { method: "POST" });
  return { ...(await handle(res)), at: Date.now() };
}

export async function bindCertificatePasskey(id, payload) {
  return handle(await fetchWithAuth(`${BASE}/signature/certificates/${id}/passkeys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

export async function unbindCertificatePasskey(id, bindingId) {
  return handle(await fetchWithAuth(`${BASE}/signature/certificates/${id}/passkeys/${bindingId}`, { method: "DELETE" }));
}
