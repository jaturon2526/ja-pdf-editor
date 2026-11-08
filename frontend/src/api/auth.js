// Auth & ผู้ใช้: login/register/Google, โปรไฟล์, รหัสผ่าน, Gemini API key, ToS
import { BASE, fetchWithAuth, handle, handlePublic } from "./client.js";

// ---------- Auth & User APIs ----------
export async function authLogin(email, password) {
  const form = new FormData();
  form.append("username", email);
  form.append("password", password);
  const res = await fetch(`${BASE}/auth/login`, { method: "POST", body: form });
  return handlePublic(res);
}

export async function authRegister(email, password) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  return handlePublic(res);
}

export async function getMe() {
  const res = await fetchWithAuth(`${BASE}/auth/me`);
  return handle(res);
}

export async function updateProfile(data) {
  const res = await fetchWithAuth(`${BASE}/auth/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handle(res);
}

export async function changePassword(oldPassword, newPassword) {
  const res = await fetchWithAuth(`${BASE}/auth/change-password`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
  return handle(res);
}

export async function forgotPassword(email) {
  const res = await fetch(`${BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return handlePublic(res);
}

export async function resetPassword(token, newPassword) {
  const res = await fetch(`${BASE}/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  return handlePublic(res);
}

export async function authGoogleLogin(credential) {
  const res = await fetch(`${BASE}/auth/google`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential })
  });
  return handlePublic(res);
}

export async function resendVerification(email) {
  const res = await fetch(`${BASE}/auth/resend-verification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email })
  });
  return handlePublic(res);
}

export async function getAiQuota() {
  const res = await fetchWithAuth(`${BASE}/auth/ai-quota`);
  return handle(res);
}

/** บันทึก API key ส่วนตัว — { apiKey, provider: gemini|anthropic|openai, model, baseUrl } (สตริงอย่างเดียว = Gemini แบบเดิม)
 *  backend ลองเรียกจริงก่อน ใช้ไม่ได้ = ไม่บันทึก (error บอกสาเหตุ) */
export async function saveApiKey(input) {
  const v = typeof input === "string" ? { apiKey: input } : input;
  const res = await fetchWithAuth(`${BASE}/auth/api-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: v.apiKey || "", provider: v.provider || "gemini", model: v.model || "", base_url: v.baseUrl || "" }),
  });
  return handle(res);
}

export async function removeApiKey() {
  const res = await fetchWithAuth(`${BASE}/auth/api-key`, {
    method: "DELETE",
  });
  return handle(res);
}

// Authentication & Profile Extensions
export async function acceptToS() {
  const res = await fetchWithAuth(`${BASE}/auth/accept-tos`, {
    method: "POST"
  });
  return handle(res);
}

// ---------- ลบบัญชี (หน้าโปรไฟล์) ----------
export async function getAccountDeletionSummary() {
  return handle(await fetchWithAuth(`${BASE}/auth/account/deletion-summary`));
}

// Safari ต้องเรียก WebAuthn ทันทีตอนกดปุ่ม — ขอ options ไว้ก่อนตอนเปิดหน้าต่างยืนยัน
export async function getDeleteAccountPasskeyOptions() {
  const res = await fetchWithAuth(`${BASE}/auth/account/delete/passkey-options`, { method: "POST" });
  return { ...(await handle(res)), at: Date.now() };
}

// ยืนยันด้วยรหัสผ่าน หรือ passkey ({ flowId, credential }) อย่างใดอย่างหนึ่ง
export async function deleteAccount({ confirmEmail, password, passkey }) {
  const body = { confirm_email: confirmEmail };
  if (passkey) {
    body.passkey_flow_id = passkey.flowId;
    body.passkey_credential = passkey.credential;
  } else {
    body.password = password;
  }
  const res = await fetchWithAuth(`${BASE}/auth/account/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle(res, { sessionRedirect: false });
}

// ออกจากระบบฝั่งเซิร์ฟเวอร์ด้วย (token เดิมใช้ต่อไม่ได้) — ไม่ผ่าน fetchWithAuth: token หมดอายุแล้วก็ไม่ต้องเด้งหน้า login
export async function logout() {
  const token = localStorage.getItem("token");
  if (!token) return;
  try {
    await fetch(`${BASE}/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  } catch {
    /* ออฟไลน์ — ลบ token ในเครื่องอย่างเดียว */
  }
}

// ---------- รูปโปรไฟล์ (หน้าโปรไฟล์) ----------
export async function getAvatarEmojis() {
  return handle(await fetchWithAuth(`${BASE}/auth/avatar/emojis`));
}

/** ภาพตัวอย่างอีโมจิ → blob URL (ผู้เรียกต้อง revoke) */
export async function avatarEmojiPreviewUrl(face, faceColor, bgColor, size = 96) {
  const q = new URLSearchParams({ face, face_color: faceColor, bg_color: bgColor, size: String(size) });
  const res = await fetchWithAuth(`${BASE}/auth/avatar/emoji-preview?${q}`);
  if (!res.ok) await handle(res);
  return URL.createObjectURL(await res.blob());
}

export async function setAvatarEmoji(face, faceColor, bgColor) {
  return handle(await fetchWithAuth(`${BASE}/auth/avatar/emoji`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ face, face_color: faceColor, bg_color: bgColor }),
  }));
}

export async function uploadAvatar(blob, filename = "avatar.png") {
  const form = new FormData();
  form.append("file", blob, filename);
  return handle(await fetchWithAuth(`${BASE}/auth/avatar/upload`, { method: "POST", body: form }));
}

export async function deleteAvatar() {
  return handle(await fetchWithAuth(`${BASE}/auth/avatar`, { method: "DELETE" }));
}
