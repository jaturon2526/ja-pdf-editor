// ส่งเอกสารให้ลงนามตามลำดับ + แจ้งเตือนในระบบ (backend: app/api/routes_signing.py)
import { BASE, fetchBlob, fetchWithAuth, handle } from "./client.js";

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// คืนผู้ใช้ หรือ null ถ้ายังไม่มีบัญชี (ส่งคำเชิญทางอีเมลแทนได้)
export async function lookupSigner(email) {
  const res = await fetchWithAuth(`${BASE}/signing/users/lookup?email=${encodeURIComponent(email)}`);
  if (res.status === 404) return null;
  return handle(res);
}

export async function downloadSigningEvidence(id, fallbackName = "evidence.pdf") {
  return fetchBlob(`${BASE}/signing/requests/${id}/evidence`, fallbackName);
}

export async function getSigningSourceInfo(fileId) {
  return handle(await fetchWithAuth(`${BASE}/signing/files/${fileId}/info`));
}

export function signingSourcePageUrl(fileId, page, zoom = 1) {
  return `${BASE}/signing/files/${fileId}/pages/${page}?zoom=${zoom}`;
}

export function signingRequestPageUrl(requestId, page, zoom = 1, version = 0) {
  // version ทำให้ URL เปลี่ยนเมื่อมีคนลงนามเพิ่ม (รูปหน้าใหม่ไม่ติด cache)
  return `${BASE}/signing/requests/${requestId}/pages/${page}?zoom=${zoom}&v=${version}`;
}

// dueAt: ISO 8601 (มี timezone) หรือ null = ไม่กำหนด
export async function createSigningRequest({ fileId, title, message, steps, dueAt = null }) {
  return handle(
    await fetchWithAuth(`${BASE}/signing/requests`, json({ file_id: fileId, title, message, steps, due_at: dueAt })),
  );
}

export async function listSigningRequests(box = "all") {
  return handle(await fetchWithAuth(`${BASE}/signing/requests?box=${box}`));
}

export async function getSigningRequest(id) {
  return handle(await fetchWithAuth(`${BASE}/signing/requests/${id}`));
}

export async function verifySigningRequest(id) {
  return handle(await fetchWithAuth(`${BASE}/signing/requests/${id}/verify`));
}

export async function downloadSigningDocument(id, fallbackName = "document.pdf") {
  return fetchBlob(`${BASE}/signing/requests/${id}/document`, fallbackName);
}

// challenge สำหรับยืนยันตัวตนด้วย passkey ก่อนลงนาม → { flow_id, options }
export async function getSigningPasskeyOptions(id) {
  return handle(await fetchWithAuth(`${BASE}/signing/requests/${id}/passkey/options`, { method: "POST" }));
}

// electronic: { signatureBlob } · digital: { pfxFile, password, signatureBlob? } · passkey: { flowId, credential } (ไม่บังคับ)
export async function signSigningRequest(id, { signType, signatureBlob, pfxFile, password, reason, passkey }) {
  const form = new FormData();
  form.append("sign_type", signType);
  if (passkey) {
    form.append("passkey_flow_id", passkey.flowId);
    form.append("passkey_credential", JSON.stringify(passkey.credential));
  }
  if (reason) form.append("reason", reason);
  if (signatureBlob) form.append("signature_image", signatureBlob, "signature.png");
  if (pfxFile) form.append("pfx_file", pfxFile, pfxFile.name || "certificate.p12");
  if (password) form.append("pfx_password", password);
  return handle(await fetchWithAuth(`${BASE}/signing/requests/${id}/sign`, { method: "POST", body: form }));
}

export async function rejectSigningRequest(id, reason) {
  return handle(await fetchWithAuth(`${BASE}/signing/requests/${id}/reject`, json({ reason })));
}

export async function cancelSigningRequest(id) {
  return handle(await fetchWithAuth(`${BASE}/signing/requests/${id}/cancel`, { method: "POST" }));
}

export async function remindSigningRequest(id) {
  return handle(await fetchWithAuth(`${BASE}/signing/requests/${id}/remind`, { method: "POST" }));
}

export async function getSigningPreferences() {
  return handle(await fetchWithAuth(`${BASE}/signing/preferences`));
}

export async function setSigningPreferences({ emailNotifications }) {
  return handle(
    await fetchWithAuth(`${BASE}/signing/preferences`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email_notifications: emailNotifications }),
    }),
  );
}

export async function getNotifications() {
  return handle(await fetchWithAuth(`${BASE}/notifications`));
}

export async function markNotificationsRead(ids = null) {
  return handle(await fetchWithAuth(`${BASE}/notifications/read`, json({ ids })));
}
