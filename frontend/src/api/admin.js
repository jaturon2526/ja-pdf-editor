// Admin (/admin)
import { BASE, fetchWithAuth, handle } from "./client.js";

// ---------- Admin APIs ----------
export async function getAdminStats() {
  const res = await fetchWithAuth(`${BASE}/admin/stats`);
  return handle(res);
}

export async function getAdminUsers() {
  const res = await fetchWithAuth(`${BASE}/admin/users`);
  return handle(res);
}

export async function updateAdminUserPlan(userId, plan_type) {
  const res = await fetchWithAuth(`${BASE}/admin/users/${userId}/plan`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan_type, expire_date: null })
  });
  return handle(res);
}

export async function updateAdminUserStatus(userId, is_active, is_admin) {
  const res = await fetchWithAuth(`${BASE}/admin/users/${userId}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active, is_admin })
  });
  return handle(res);
}

export async function getAdminPlans() {
  const res = await fetchWithAuth(`${BASE}/admin/plans`);
  if (!res.ok) throw new Error("Failed to fetch plans");
  return res.json();
}

export async function updateAdminPlanConfig(planType, maxSessions, maxStorageMb) {
  const res = await fetchWithAuth(`${BASE}/admin/plans/${planType}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_sessions: maxSessions, max_storage_mb: maxStorageMb })
  });
  if (!res.ok) throw new Error("Failed to update plan");
  return res.json();
}

// โควต้า/เครดิตของบริการภายนอก + สถิติ 30 วัน (refresh = ดึงจาก API ใหม่ ไม่ใช้ cache ฝั่ง server)
export async function getAdminQuotas(refresh = false) {
  const res = await fetchWithAuth(`${BASE}/admin/quotas${refresh ? "?refresh=true" : ""}`);
  return handle(res);
}
