// ตั้งค่า AI: เลือกผู้ให้บริการ (Gemini / Claude / OpenAI) สำหรับ API key ส่วนตัว — backend ทดสอบ key จริงก่อนบันทึก
// (จำลอง POST /api/auth/api-key — CI ไม่มี key จริง · การเรียกผู้ให้บริการทดสอบใน backend/tests/test_ai_providers.py)
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

test("เลือก Claude แล้วทดสอบและบันทึก key · OpenAI ต้องระบุรุ่น · key ใช้ไม่ได้แจ้งสาเหตุ", async ({ page }) => {
  await login(page);
  const posted = [];
  let fail = false;
  await page.route("**/api/auth/api-key", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON();
    posted.push(body);
    if (fail) return route.fulfill({ status: 400, json: { detail: "ทดสอบ API key ไม่ผ่าน: API key ไม่ถูกต้อง หรือไม่มีสิทธิ์ใช้รุ่นนี้" } });
    return route.fulfill({ json: { status: "success", provider: body.provider, model: body.model || "claude-haiku-5-5" } });
  });
  await page.goto("/ai-config");
  await expect(page.getByRole("heading", { name: /ตั้งค่า AI/ })).toBeVisible();
  await expect(page.getByTestId("system-ai")).toBeVisible();

  const provider = page.getByLabel("ผู้ให้บริการ AI");
  await expect(provider.locator("option")).toHaveText(["Google Gemini", "Anthropic Claude", "OpenAI / API แบบ OpenAI"]);
  await provider.selectOption("anthropic");
  await expect(page.getByRole("link", { name: "Claude Console" })).toBeVisible();
  await page.getByLabel("API Key", { exact: true }).fill("sk-ant-test-key");
  await page.getByRole("button", { name: "ทดสอบและบันทึก" }).click();
  await expect(page.getByText(/ทดสอบผ่านและบันทึกแล้ว — ใช้ Anthropic Claude \(claude-haiku-5-5\)/)).toBeVisible();
  expect(posted[0]).toEqual({ api_key: "sk-ant-test-key", provider: "anthropic", model: "", base_url: "" });

  await provider.selectOption("openai");
  await expect(page.getByLabel(/URL ของ API/)).toBeVisible();
  await page.getByLabel(/API Key/).fill("sk-oa");
  await page.getByRole("button", { name: "ทดสอบและบันทึก" }).click();
  await expect(page.getByRole("alert")).toHaveText("กรุณาระบุชื่อรุ่น (model)");
  expect(posted).toHaveLength(1);

  fail = true;
  await page.getByLabel(/รุ่น \(model\)/).fill("gpt-dept");
  await page.getByLabel(/URL ของ API/).fill("https://dept.openai.azure.com/openai/v1");
  await page.getByRole("button", { name: "ทดสอบและบันทึก" }).click();
  await expect(page.getByRole("alert")).toContainText("API key ไม่ถูกต้อง");
  expect(posted[1]).toMatchObject({ provider: "openai", model: "gpt-dept", base_url: "https://dept.openai.azure.com/openai/v1" });
});
