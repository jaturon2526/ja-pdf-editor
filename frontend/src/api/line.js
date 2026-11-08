// LINE: แจ้งเตือน (สถานะ / ขอรหัสผูก / เปิด-ปิด / ยกเลิก — backend: /line/*) + เข้าสู่ระบบด้วย LINE (/auth/line/*)
import { BASE, fetchWithAuth, handle, handlePublic } from "./client.js";

export async function getLineStatus() {
  return handle(await fetchWithAuth(`${BASE}/line/status`));
}

export async function createLineLinkCode() {
  return handle(await fetchWithAuth(`${BASE}/line/link-code`, { method: "POST" }));
}

export async function setLineNotifications(enabled) {
  return handle(
    await fetchWithAuth(`${BASE}/line/preferences`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notifications: enabled }),
    }),
  );
}

export async function unlinkLine() {
  return handle(await fetchWithAuth(`${BASE}/line/link`, { method: "DELETE" }));
}

// ---- เข้าสู่ระบบด้วย LINE (backend: /auth/line/*) ----

const LINE_STATE_KEY = "line_login_state";
const LINE_PENDING_KEY = "line_login_pending";

async function postPublic(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return handlePublic(res);
}

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export async function getLineLoginConfig() {
  return handlePublic(await fetch(`${BASE}/auth/line/config`));
}

// เก็บ state ไว้ในเบราว์เซอร์นี้ — หน้า callback ตรวจว่าตรงกัน (กันถูกหลอกให้ล็อกอินเข้าบัญชีคนอื่น)
function goToLine({ url, state }, mode) {
  storage()?.setItem(LINE_STATE_KEY, JSON.stringify({ state, mode }));
  window.location.assign(url);
}

export async function startLineLogin() {
  goToLine(await postPublic("/auth/line/start"), "login");
}

export async function startLineLoginLink() {
  goToLine(await handle(await fetchWithAuth(`${BASE}/auth/line/link-start`, { method: "POST" })), "link");
}

// {state, mode} ที่เก็บไว้ตอนกดปุ่ม (ใช้ได้ครั้งเดียว) — ไม่มี = ไม่ได้เริ่มจากเบราว์เซอร์นี้
export function takeLineLoginState() {
  const s = storage();
  let value;
  try {
    value = JSON.parse(s?.getItem(LINE_STATE_KEY) || "null");
  } catch {
    value = null;
  }
  s?.removeItem(LINE_STATE_KEY);
  return value || { state: "", mode: "login" };
}

export async function completeLineLogin(code, state) {
  const result = await postPublic("/auth/line/callback", { code, state });
  if (result.status === "need_email") storage()?.setItem(LINE_PENDING_KEY, result.pending);
  return result;
}

export async function requestLineLoginEmail(email) {
  const pending = storage()?.getItem(LINE_PENDING_KEY) || "";
  return postPublic("/auth/line/email", { pending, email });
}

export async function confirmLineLoginEmail(token) {
  const pending = storage()?.getItem(LINE_PENDING_KEY) || "";
  const result = await postPublic("/auth/line/confirm", { token, pending });
  storage()?.removeItem(LINE_PENDING_KEY);
  return result;
}

export async function unlinkLineLogin() {
  return handle(await fetchWithAuth(`${BASE}/auth/line/link`, { method: "DELETE" }));
}
