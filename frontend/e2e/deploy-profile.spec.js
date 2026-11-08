// รูปแบบการติดตั้ง onprem: หน้า Login ซ่อนปุ่ม Google/LINE, บอกโดเมนอีเมลที่สมัครได้, ปิดการสมัครเอง
// จำลอง GET /api/config/public (ค่าจริงมาจาก .env ของ backend — ทดสอบใน backend/tests/test_deploy_profile.py)
import { expect, test } from "@playwright/test";

function mockConfig(page, overrides) {
  return page.route("**/api/config/public", (route) =>
    route.fulfill({
      json: {
        app_name: "JA PDF Editor", profile: "onprem", google_client_id: null, line_login: false,
        self_registration: true, allowed_email_domains: ["corp.co.th"], ...overrides,
      },
    }));
}

test("onprem: ไม่มีปุ่ม Google/LINE และสมัครได้เฉพาะโดเมนองค์กร", async ({ page }) => {
  await mockConfig(page, {});
  let registerCalls = 0;
  await page.route("**/api/auth/register", (route) => { registerCalls += 1; return route.fulfill({ status: 500, json: {} }); });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "เข้าสู่ระบบ" })).toBeVisible();
  await expect(page.getByTestId("social-login")).toHaveCount(0);
  await expect(page.getByTestId("line-login-button")).toHaveCount(0);

  await page.getByRole("button", { name: "สมัครสมาชิกใหม่" }).click();
  await expect(page.getByTestId("register-domain-hint")).toContainText("@corp.co.th");
  await page.locator('input[type="email"]').fill("someone@gmail.com");
  const pw = page.locator('input[type="password"]');
  await pw.nth(0).fill("Passw0rd-123");
  await pw.nth(1).fill("Passw0rd-123");
  await page.getByRole("button", { name: "สมัครใช้งาน" }).click();
  await expect(page.getByText("สมัครได้เฉพาะอีเมลขององค์กร (@corp.co.th)")).toBeVisible();
  expect(registerCalls).toBe(0);
});

test("onprem ปิดการสมัครเอง: ไม่มีปุ่มสมัคร แต่ลิงก์เชิญลงนามยังสมัครได้", async ({ page }) => {
  await mockConfig(page, { self_registration: false });
  await page.goto("/login");
  await expect(page.getByTestId("register-closed")).toBeVisible();
  await expect(page.getByRole("button", { name: "สมัครสมาชิกใหม่" })).toHaveCount(0);

  await page.goto("/login?register=1&email=partner%40vendor.example");
  await expect(page.getByRole("heading", { name: "สร้างบัญชีใหม่" })).toBeVisible();
  await expect(page.getByTestId("register-domain-hint")).toHaveCount(0);
});

test("ลิงก์ซอร์สโค้ด (AGPL-3.0) ชี้ตาม SOURCE_CODE_URL ของเครื่องนั้น", async ({ page }) => {
  await mockConfig(page, { source_url: "https://git.corp.co.th/pdf-editor" });
  await page.goto("/login");
  await expect(page.getByTestId("source-code-link")).toHaveAttribute("href", "https://git.corp.co.th/pdf-editor");
});
