// ตัวกลางเรียก backend: BASE, fetchWithAuth (แนบ CSRF token + จัดการ 401), handle, ดาวน์โหลด Blob
// ระหว่าง dev เรียกผ่าน /api ซึ่ง vite proxy ไป backend ให้ (ดู vite.config.js)
//
// การยืนยันตัวตน (SEC-04): access token อยู่ใน HttpOnly cookie `ja_session` — JavaScript อ่านไม่ได้ เบราว์เซอร์แนบให้เอง
// คำขอที่แก้ข้อมูลต้องส่ง cookie `ja_csrf` กลับมาใน header X-CSRF-Token (double-submit — backend app/core/auth_cookies.py)
// "มี ja_csrf" = น่าจะ login อยู่ (ใช้เลือกลิงก์/ปุ่ม) — ตัวจริงตรวจที่ backend ทุกคำขอ

export const BASE = "/api";

const CSRF_COOKIE = "ja_csrf";
const LEGACY_TOKEN_KEY = "token";

// ส่งตอน login ทุกแบบ → backend ใส่ token ใน cookie แทนการส่งกลับใน body
export const COOKIE_AUTH_HEADERS = Object.freeze({ "X-Auth-Mode": "cookie" });

function readCookie(name) {
  if (typeof document === "undefined" || !document.cookie) return "";
  for (const part of document.cookie.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return "";
}

export function csrfToken() {
  return readCookie(CSRF_COOKIE);
}

export function isLoggedIn() {
  return Boolean(csrfToken());
}

// ลืมสถานะ login ในเครื่อง (cookie ja_session เป็น HttpOnly — ลบได้ที่ backend /auth/logout เท่านั้น)
export function clearLocalSession() {
  if (typeof document !== "undefined") document.cookie = `${CSRF_COOKIE}=; Max-Age=0; path=/; SameSite=Lax`;
  try {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    /* storage ถูกปิด */
  }
}

// header สำหรับ fetch/XHR ที่ไม่ได้ผ่าน fetchWithAuth
export function authHeaders(extra = {}) {
  const headers = new Headers(extra);
  const csrf = csrfToken();
  if (csrf) headers.set("X-CSRF-Token", csrf);
  return headers;
}

function redirectToLogin() {
  clearLocalSession();
  window.location.href = "/login?expired=1";
}

export async function fetchWithAuth(url, options = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...options, headers: authHeaders(options.headers || {}) });

  // Global 401 Interceptor
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("Unauthorized");
  }

  return res;
}

// หน้าเว็บรุ่นก่อน v1.35.5 เก็บ token ใน localStorage — ย้ายเป็น cookie ครั้งเดียว (ผู้ใช้ไม่ต้อง login ใหม่) แล้วลบทิ้ง
export async function migrateLegacyToken() {
  let token;
  try {
    token = localStorage.getItem(LEGACY_TOKEN_KEY);
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    return;
  }
  if (!token) return;
  try {
    await fetch(`${BASE}/auth/session/cookie`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  } catch {
    /* ออฟไลน์/หมดอายุ — ให้ login ใหม่ตามปกติ */
  }
}

// endpoint ที่ใช้ตอนยังไม่ login (login, สมัคร, ลืมรหัสผ่าน ฯลฯ): 401 = อีเมล/รหัสผ่านผิด หรือยังไม่ยืนยันอีเมล
// ไม่ใช่ "เซสชันหมดอายุ" — ต้องแสดงข้อความจาก backend ตรงๆ ห้ามเด้งไปหน้า login?expired
export async function handlePublic(res) {
  return handle(res, { sessionRedirect: false });
}

export async function handle(res, { sessionRedirect = true } = {}) {
  if (!res.ok) {
    if (res.status === 401 && sessionRedirect) {
      redirectToLogin();
      throw new Error("Unauthorized");
    }
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    const err = new Error(detail);
    err.status = res.status; // ให้ผู้เรียกแยกกรณีได้ (เช่น 409 ตารางทับข้อความ → ถามยืนยัน)
    throw err;
  }
  return res.json();
}

export function filenameFromDisposition(header, fallback) {
  if (!header) return fallback;
  const star = /filename\*=(?:UTF-8|utf-8)''([^;]+)/.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* ignore */
    }
  }
  const plain = /filename="?([^";]+)"?/.exec(header);
  return plain ? plain[1] : fallback;
}

export async function fetchBlob(url, fallbackName = "download") {
  const res = await fetchWithAuth(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  return { blob, filename: filenameFromDisposition(res.headers.get("Content-Disposition"), fallbackName) };
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
