// ตัวกลางเรียก backend: BASE, fetchWithAuth (แนบ token + จัดการ 401), handle, ดาวน์โหลด Blob
// Wrapper บาง ๆ คุยกับ backend (FastAPI) ทุก endpoint ที่ทำไว้ในเฟสก่อนหน้า
// ระหว่าง dev เรียกผ่าน /api ซึ่ง vite proxy ไป http://localhost:8000 ให้ (ดู vite.config.js)

export const BASE = "/api";

export function getToken() {
  return localStorage.getItem("token");
}

export async function fetchWithAuth(url, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  
  const newOptions = { ...options, headers };
  const res = await fetch(url, newOptions);
  
  // Global 401 Interceptor
  if (res.status === 401) {
    localStorage.removeItem("token");
    
    window.location.href = "/login?expired=1";
    throw new Error("Unauthorized");
  }
  
  return res;
}

// endpoint ที่ใช้ตอนยังไม่ login (login, สมัคร, ลืมรหัสผ่าน ฯลฯ): 401 = อีเมล/รหัสผ่านผิด หรือยังไม่ยืนยันอีเมล
// ไม่ใช่ "เซสชันหมดอายุ" — ต้องแสดงข้อความจาก backend ตรงๆ ห้ามเด้งไปหน้า login?expired
export async function handlePublic(res) {
  return handle(res, { sessionRedirect: false });
}

export async function handle(res, { sessionRedirect = true } = {}) {
  if (!res.ok) {
    if (res.status === 401 && sessionRedirect) {
      localStorage.removeItem("token");
      
      window.location.href = "/login?expired=1";
      throw new Error("Unauthorized");
    }
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
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
