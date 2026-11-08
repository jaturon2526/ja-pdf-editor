// ระบบที่ยังไม่ได้ตั้ง AI (ไม่มี AI_API_KEY และผู้ใช้ไม่มี key ส่วนตัว): ไม่แสดงกล่องโควต้า AI, ตัวเลือก/ข้อความที่พูดถึง AI
// ตอนแปลงเป็น Word ถูกซ่อน และเมนู ตั้งค่า AI ซ่อนเมื่อผู้ดูแลปิด key ส่วนตัวด้วย
// (จำลอง GET /api/auth/ai-quota — ฝั่ง backend ทดสอบใน backend/tests/test_ai_providers.py)
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

function mockAiQuota(page, overrides) {
  return page.route("**/api/auth/ai-quota", (route) => route.fulfill({
    json: {
      requests_today: 0, system_requests_today: 0, system_daily_limit: 2,
      system_ai: false, system_provider: null, system_provider_label: null, system_model: null, system_key_preview: null,
      user_keys_enabled: false, providers: [], personal_provider: null, personal_model: null, personal_base_url: null,
      personal_key_preview: null, ai_available: false, ai_ocr: false, ...overrides,
    },
  }));
}

test("ไม่ได้ตั้ง AI: ซ่อนกล่องโควต้า เมนูตั้งค่า AI และข้อความ AI ตอนแปลงเป็น Word", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await mockAiQuota(page, {});
  await page.goto("/dashboard");
  await expect(page.getByText("พื้นที่ใช้งานของคุณ")).toBeVisible();
  await expect(page.getByText("โควต้าแปลงไฟล์ฟรี (AI)")).toHaveCount(0);
  await page.getByRole("button", { name: "เมนูบัญชี" }).click();
  await expect(page.getByText("ความปลอดภัย", { exact: true })).toBeVisible();
  await expect(page.getByText("ตั้งค่า AI (API Key)")).toHaveCount(0);
  await page.getByRole("button", { name: "เมนูบัญชี" }).click();

  await page.getByRole("button", { name: "เมนูไฟล์" }).first().click();
  await page.getByRole("menuitem", { name: "แปลงเป็น Word" }).click();
  const editable = page.getByRole("button", { name: /แก้ไขข้อความได้อิสระ/ });
  await expect(editable).toBeVisible();
  await expect(editable).not.toContainText("AI");
  await expect(page.getByRole("button", { name: /รักษาหน้าตาเหมือนต้นฉบับ/ })).not.toContainText("AI");
});

test("มี AI ของระบบ: แสดงกล่องโควต้าและเมนูตั้งค่า AI · ตัวเลือกแปลงพูดถึง AI", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await mockAiQuota(page, { system_ai: true, system_provider: "anthropic", system_provider_label: "Anthropic Claude", ai_available: true });
  await page.goto("/dashboard");
  await expect(page.getByText("โควต้าแปลงไฟล์ฟรี (AI)")).toBeVisible();
  await page.getByRole("button", { name: "เมนูบัญชี" }).click();
  await expect(page.getByText("ตั้งค่า AI (API Key)")).toBeVisible();
  await page.getByRole("button", { name: "เมนูบัญชี" }).click();
  await page.getByRole("button", { name: "เมนูไฟล์" }).first().click();
  await page.getByRole("menuitem", { name: "แปลงเป็น Word" }).click();
  await expect(page.getByRole("button", { name: /แก้ไขข้อความได้อิสระ/ })).toContainText("AI ช่วยแก้คำไทย");
});

test("ไม่มี AI ของระบบแต่เปิดให้ใช้ key ส่วนตัว: ไม่มีกล่องโควต้า แต่ยังเข้าเมนูตั้งค่า AI ได้", async ({ page }) => {
  await login(page);
  await mockAiQuota(page, { user_keys_enabled: true, providers: [{ value: "gemini", label: "Google Gemini" }] });
  await page.goto("/dashboard");
  await expect(page.getByText("พื้นที่ใช้งานของคุณ")).toBeVisible();
  await expect(page.getByText("โควต้าแปลงไฟล์ฟรี (AI)")).toHaveCount(0);
  await page.getByRole("button", { name: "เมนูบัญชี" }).click();
  await expect(page.getByText("ตั้งค่า AI (API Key)")).toBeVisible();
});
