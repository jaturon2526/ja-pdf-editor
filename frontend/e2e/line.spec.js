// แจ้งเตือนทาง LINE — หน้าความปลอดภัย: ขอรหัส → (ผู้ใช้ส่งรหัสใน LINE) → หน้าอัปเดตเป็น "เชื่อมต่อแล้ว" → เปิด/ปิด → ยกเลิก
// จำลอง /api/line/* ในเบราว์เซอร์ (CI ไม่มี LINE channel จริง) — ฝั่ง backend/webhook ทดสอบใน backend/tests/test_line.py
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

const BASE_STATUS = {
  enabled: true,
  linked: false,
  display_name: null,
  linked_at: null,
  notifications: true,
  add_friend_url: "https://line.me/R/ti/p/%40227hmohv",
};
const QR = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>');

async function mockLine(page) {
  const state = { status: { ...BASE_STATUS }, linkAfterPolls: null, calls: [] };
  await page.route("**/api/line/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace(/^\/api/, "");
    state.calls.push(`${req.method()} ${path}`);
    if (path === "/line/status") {
      if (state.linkAfterPolls !== null && --state.linkAfterPolls <= 0) {
        state.status = { ...state.status, linked: true, display_name: "คุณทดสอบ", linked_at: new Date().toISOString() };
        state.linkAfterPolls = null;
      }
      return route.fulfill({ json: state.status });
    }
    if (path === "/line/link-code") {
      state.linkAfterPolls = 2; // ผู้ใช้ส่งรหัสใน LINE ระหว่างที่หน้าเว็บ poll อยู่
      return route.fulfill({
        json: { code: "JA-ABC234", expires_in: 600, chat_url: "https://line.me/R/oaMessage/%40227hmohv/?JA-ABC234", qr_svg: QR },
      });
    }
    if (path === "/line/preferences") {
      state.status = { ...state.status, notifications: req.postDataJSON().notifications };
      return route.fulfill({ json: state.status });
    }
    if (path === "/line/link" && req.method() === "DELETE") {
      state.status = { ...BASE_STATUS };
      return route.fulfill({ json: state.status });
    }
    return route.fulfill({ status: 404, json: { detail: "not mocked" } });
  });
  return state;
}

test("เชื่อมต่อ LINE ด้วยรหัส → หน้าอัปเดตเองเมื่อส่งรหัสแล้ว → ปิดรับ → ยกเลิกการเชื่อมต่อ", async ({ page }) => {
  await login(page);
  const state = await mockLine(page);
  await page.goto("/security");
  const section = page.getByTestId("line-section");
  await expect(section.getByRole("heading", { name: "แจ้งเตือนทาง LINE" })).toBeVisible();

  await section.getByRole("button", { name: "เชื่อมต่อ LINE" }).click();
  await expect(section.getByTestId("line-code")).toHaveText("JA-ABC234");
  await expect(section.getByRole("link", { name: "เปิด LINE แล้วส่งรหัส" })).toHaveAttribute("href", /oaMessage\/%40227hmohv\/\?JA-ABC234$/);
  await expect(section.getByAltText(/QR/)).toBeVisible();
  await expect(section).toContainText("หมดอายุใน");

  // poll ทุก 3 วินาที — พอ backend บอกว่าผูกแล้ว หน้าเปลี่ยนเอง
  await expect(section.getByTestId("line-linked")).toBeVisible({ timeout: 12_000 });
  await expect(section).toContainText('เชื่อมต่อ LINE "คุณทดสอบ" แล้ว');

  const toggle = section.getByLabel(/รับแจ้งเตือนการลงนามทาง LINE/);
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  await expect(toggle).not.toBeChecked();
  expect(state.status.notifications).toBe(false);

  await section.getByRole("button", { name: "ยกเลิกการเชื่อมต่อ LINE" }).click();
  await section.getByRole("button", { name: "ยกเลิกการเชื่อมต่อ", exact: true }).click();
  await expect(section).toContainText("ยกเลิกการเชื่อมต่อ LINE แล้ว");
  await expect(section.getByRole("button", { name: "เชื่อมต่อ LINE" })).toBeVisible();
  expect(state.calls).toContain("DELETE /line/link");
});

test("ระบบยังไม่เปิด LINE → ไม่แสดงส่วนเชื่อมต่อ และหน้าการลงนามไม่มีลิงก์ LINE", async ({ page }) => {
  await login(page);
  await page.route("**/api/line/status", (route) => route.fulfill({ json: { ...BASE_STATUS, enabled: false } }));
  await page.goto("/security");
  await expect(page.getByTestId("passkey-section")).toBeVisible();
  await expect(page.getByTestId("line-section")).toHaveCount(0);
  await page.goto("/signing");
  await expect(page.getByRole("tab").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /LINE/ })).toHaveCount(0);
});

test("หน้าการลงนามมีลิงก์ไปตั้งค่า LINE เมื่อระบบเปิดใช้", async ({ page }) => {
  await login(page);
  await mockLine(page);
  await page.goto("/signing");
  await page.getByRole("link", { name: "รับแจ้งเตือนทาง LINE แทน →" }).click();
  await page.waitForURL("**/security");
  await expect(page.getByTestId("line-section")).toBeVisible();
});
