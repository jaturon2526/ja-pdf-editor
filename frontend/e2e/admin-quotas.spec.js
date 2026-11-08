// หน้าแอดมิน: การ์ดโควต้า/เครดิต (LINE, อีเมล, Gemini, ดิสก์) + กราฟ 30 วัน + ปุ่มดึงข้อมูลล่าสุด
// ผู้ใช้ e2e ไม่ใช่แอดมิน และ CI ไม่มี LINE/Brevo จริง → จำลอง /api/auth/me และ /api/admin/* ในเบราว์เซอร์
// (การคำนวณฝั่ง backend ทดสอบใน backend/tests/test_quotas.py)
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

function history() {
  const out = [];
  const start = new Date();
  start.setDate(start.getDate() - 29);
  for (let i = 0; i < 30; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    out.push({ date: d.toISOString().slice(0, 10), ai: i % 5, email: i === 29 ? 12 : 3, line: i % 2 });
  }
  return out;
}

const QUOTAS = {
  alert_percent: 80,
  checked_at: new Date().toISOString(),
  history: history(),
  items: [
    { key: "line", name: "LINE (ข้อความ push)", used: 250, limit: 300, remaining: 50, unit: "ข้อความ", period: "month",
      percent: 83.3, status: "warn", source: "api", resets_at: "2026-11-30T15:00:00+00:00", link: "https://manager.line.biz/",
      note: "ระบบส่งเอง 248", error: null, extra: {} },
    { key: "email", name: "อีเมล (Brevo)", used: 12, limit: 300, remaining: 288, unit: "ฉบับ", period: "day",
      percent: 4, status: "ok", source: "api", resets_at: null, link: "https://app.brevo.com/", note: "แพ็กเกจฟรี",
      error: null, extra: {} },
    { key: "ai", name: "Gemini AI (คำขอวันนี้)", used: 4, limit: null, remaining: null, unit: "คำขอ", period: "day",
      percent: null, status: "info", source: "internal", resets_at: null, link: "https://aistudio.google.com/usage",
      note: "ดูยอดจริงที่ AI Studio", error: null, extra: {} },
    { key: "disk", name: "พื้นที่ดิสก์เซิร์ฟเวอร์", used: 40 * 1024 ** 3, limit: 45 * 1024 ** 3, remaining: 5 * 1024 ** 3,
      unit: "bytes", period: "-", percent: 88.9, status: "warn", source: "system", resets_at: null, link: null,
      note: null, error: null, extra: {} },
    { key: "backup", name: "สำรองข้อมูลล่าสุด (ในเครื่อง)", used: 50, limit: null, remaining: null, unit: "ชม. ที่แล้ว",
      period: "-", percent: null, status: "warn", status_label: "ขาดหาย", source: "system", resets_at: null, link: null,
      note: "ครั้งล่าสุด 05/11/2026 03:00 น.", error: null, extra: {} },
  ],
};

async function mockAdmin(page) {
  const calls = [];
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: { id: 1, email: "admin@example.com", is_admin: true, is_active: true, plan_type: "premium" } }));
  await page.route("**/api/admin/**", (route) => {
    const url = new URL(route.request().url());
    calls.push(url.pathname + url.search);
    if (url.pathname.endsWith("/admin/stats")) return route.fulfill({ json: { total_users: 3, total_files: 5, total_storage: 1024, ai_requests_today: 4 } });
    if (url.pathname.endsWith("/admin/users")) return route.fulfill({ json: { users: [] } });
    if (url.pathname.endsWith("/admin/plans")) return route.fulfill({ json: [] });
    if (url.pathname.endsWith("/admin/quotas")) return route.fulfill({ json: QUOTAS });
    return route.fulfill({ status: 404, json: { detail: "not mocked" } });
  });
  return calls;
}

test("แอดมินเห็นโควต้า ใช้ไป/เหลือ/สถานะ กราฟ 30 วัน และกดดึงข้อมูลล่าสุดได้", async ({ page }) => {
  await login(page);
  const calls = await mockAdmin(page);
  await page.goto("/admin");
  const panel = page.getByTestId("quota-panel");
  await expect(panel.getByRole("heading", { name: "โควต้าบริการภายนอกและสถานะเซิร์ฟเวอร์" })).toBeVisible();
  await expect(panel).toContainText("ต้องดู 3 รายการ");

  const line = panel.getByTestId("quota-line");
  await expect(line).toContainText("ใกล้เต็ม");
  await expect(line).toContainText("250 ข้อความ");
  await expect(line).toContainText("เหลือ 50 ข้อความ");
  await expect(line.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "83.3");
  await expect(panel.getByTestId("quota-email")).toContainText("ปกติ");
  await expect(panel.getByTestId("quota-ai")).toContainText("ดูยอดจริงที่ AI Studio");
  await expect(panel.getByTestId("quota-disk")).toContainText("40.0 GB");
  await expect(panel.getByTestId("quota-backup")).toContainText("ขาดหาย");
  await expect(panel.getByTestId("quota-backup")).toContainText("50 ชม. ที่แล้ว");

  const chart = panel.getByTestId("quota-chart");
  await expect(chart.locator("rect")).toHaveCount(30);
  await chart.getByRole("tab", { name: "อีเมล" }).click();
  await expect(chart).toContainText("สูงสุด 12 ฉบับ/วัน");

  await panel.getByRole("button", { name: "ดึงข้อมูลล่าสุด" }).click();
  await expect.poll(() => calls.filter((c) => c.includes("refresh=true")).length).toBe(1);
});
