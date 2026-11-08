// รับบริจาค PromptPay (/donations/*, /admin/donations/*) — ดู backend/app/api/routes_donations.py
import { BASE, fetchWithAuth, handle, handlePublic } from "./client.js";

export async function getDonationInfo() {
  return handlePublic(await fetch(`${BASE}/donations/info`));
}

export function donationQrUrl(amount) {
  const a = Number(amount);
  return `${BASE}/donations/qr.svg${a > 0 ? `?amount=${encodeURIComponent(a.toFixed(2))}` : ""}`;
}

export async function getSupporters() {
  return handlePublic(await fetch(`${BASE}/donations/board`));
}

/** แจ้งโอน: { amount, transferredAt (Date), anonymous, showOnBoard, displayName, message, slip (File|null) } */
export async function reportDonation({ amount, transferredAt, anonymous, showOnBoard, displayName, message, slip }) {
  const form = new FormData();
  form.append("amount", String(amount));
  form.append("transferred_at", transferredAt.toISOString());
  form.append("anonymous", anonymous ? "true" : "false");
  form.append("show_on_board", showOnBoard ? "true" : "false");
  if (displayName) form.append("display_name", displayName);
  if (message) form.append("message", message);
  if (slip) form.append("slip", slip);
  return handle(await fetchWithAuth(`${BASE}/donations`, { method: "POST", body: form }));
}

export async function getMyDonations() {
  return handle(await fetchWithAuth(`${BASE}/donations/mine`));
}

// ---------- แอดมิน ----------
export async function getDonationConfig() {
  return handle(await fetchWithAuth(`${BASE}/admin/donations/config`));
}

export async function saveDonationConfig(config) {
  return handle(await fetchWithAuth(`${BASE}/admin/donations/config`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config),
  }));
}

export async function getAdminDonations(status = "pending") {
  return handle(await fetchWithAuth(`${BASE}/admin/donations?status=${status}`));
}

/** สลิปเป็น object URL (ต้องแนบ token — ใช้ <img src> ตรง ๆ ไม่ได้) · ผู้เรียก revokeObjectURL เอง */
export async function getDonationSlipUrl(id) {
  const res = await fetchWithAuth(`${BASE}/admin/donations/${id}/slip`);
  if (!res.ok) throw new Error("โหลดสลิปไม่สำเร็จ");
  return URL.createObjectURL(await res.blob());
}

export async function approveDonation(id, body = {}) {
  return handle(await fetchWithAuth(`${BASE}/admin/donations/${id}/approve`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }));
}

export async function rejectDonation(id, note) {
  return handle(await fetchWithAuth(`${BASE}/admin/donations/${id}/reject`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note: note || null }),
  }));
}

export async function setDonationOnBoard(id, showOnBoard) {
  return handle(await fetchWithAuth(`${BASE}/admin/donations/${id}/board`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ show_on_board: showOnBoard }),
  }));
}

export async function verifyDonation(id) {
  return handle(await fetchWithAuth(`${BASE}/admin/donations/${id}/verify`, { method: "POST" }));
}
