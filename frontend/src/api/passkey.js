// Passkey (WebAuthn): ลงทะเบียน / เข้าสู่ระบบ / จัดการ — ส่วนเข้ารหัสทำโดยเบราว์เซอร์ผ่าน @simplewebauthn/browser
import { browserSupportsWebAuthn, browserSupportsWebAuthnAutofill, startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { BASE, fetchWithAuth, handle, handlePublic } from "./client.js";

export { browserSupportsWebAuthn, browserSupportsWebAuthnAutofill };

// แปลง error จากเบราว์เซอร์เป็นข้อความภาษาไทย — คืน null เมื่อผู้ใช้กดยกเลิก/ถูกยกเลิกเอง (ไม่ต้องแสดง)
export function passkeyErrorMessage(err, { registering = false } = {}) {
  const name = err?.name || "";
  const code = err?.code || "";
  if (name === "AbortError" || code === "ERROR_CEREMONY_ABORTED") return null;
  if (name === "NotAllowedError") return registering ? null : "ยกเลิกแล้ว หรือไม่พบ passkey ของเว็บไซต์นี้ในอุปกรณ์";
  if (name === "InvalidStateError" || code === "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED") {
    return "อุปกรณ์/ผู้จัดการรหัสผ่านนี้มี passkey ของบัญชีนี้อยู่แล้ว";
  }
  if (name === "SecurityError") return "เบราว์เซอร์ไม่อนุญาตให้ใช้ passkey กับที่อยู่เว็บนี้";
  return err?.message || "ใช้ passkey ไม่สำเร็จ";
}

export async function listPasskeys() {
  const res = await fetchWithAuth(`${BASE}/auth/passkeys`);
  return (await handle(res)).passkeys;
}

// Safari ต้องเรียก WebAuthn ทันทีจากการกดปุ่ม (ห้ามมี fetch คั่น) — จึงขอ options ไว้ก่อน แล้วส่ง prepared เข้ามาตอนกด
// challenge มีอายุ 5 นาทีที่ server ใช้ได้ครั้งเดียว — prepared ที่เก่ากว่า 4 นาทีจะขอใหม่
const FRESH_MS = 4 * 60 * 1000;
const isFresh = (p) => p && Date.now() - p.at < FRESH_MS;

export async function preparePasskeyRegistration() {
  const res = await fetchWithAuth(`${BASE}/auth/passkeys/register/options`, { method: "POST" });
  return { ...(await handle(res)), at: Date.now() };
}

export async function preparePasskeyLogin() {
  const res = await fetch(`${BASE}/auth/passkeys/login/options`, { method: "POST" });
  return { ...(await handlePublic(res)), at: Date.now() };
}

export async function registerPasskey(name, prepared = null) {
  const { flow_id, options } = isFresh(prepared) ? prepared : await preparePasskeyRegistration();
  const credential = await startRegistration({ optionsJSON: options });
  const verify = await fetchWithAuth(`${BASE}/auth/passkeys/register/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flow_id, credential, name }),
  });
  return handle(verify);
}

// ยืนยันตัวตนด้วย passkey ด้วย options ที่ขอไว้แล้ว (เรียกตรงจากการกดปุ่ม — Safari) → credential JSON
export async function assertPasskey(options) {
  return startAuthentication({ optionsJSON: options });
}

// autofill=true: แนะนำ passkey ในช่องอีเมล (ช่องต้องมี autocomplete="username webauthn") — รอจนผู้ใช้เลือก
export async function loginWithPasskey({ autofill = false, prepared = null } = {}) {
  const { flow_id, options } = isFresh(prepared) ? prepared : await preparePasskeyLogin();
  const credential = await startAuthentication({ optionsJSON: options, useBrowserAutofill: autofill });
  const verify = await fetch(`${BASE}/auth/passkeys/login/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flow_id, credential }),
  });
  return handlePublic(verify);
}

export async function renamePasskey(id, name) {
  const res = await fetchWithAuth(`${BASE}/auth/passkeys/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return handle(res);
}

export async function deletePasskey(id) {
  const res = await fetchWithAuth(`${BASE}/auth/passkeys/${id}`, { method: "DELETE" });
  return handle(res);
}

// ชื่อเริ่มต้นตามอุปกรณ์ที่ใช้อยู่ เช่น "iPhone", "Mac", "Windows"
export function guessDeviceName() {
  const ua = navigator.userAgent || "";
  if (/iPhone/.test(ua)) return "iPhone";
  if (/iPad/.test(ua)) return "iPad";
  if (/Android/.test(ua)) return "Android";
  if (/Macintosh|Mac OS X/.test(ua)) return "Mac";
  if (/Windows/.test(ua)) return "Windows";
  if (/Linux/.test(ua)) return "Linux";
  return "Passkey";
}
