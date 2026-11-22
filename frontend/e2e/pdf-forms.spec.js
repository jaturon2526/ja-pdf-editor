// กรอกแบบฟอร์ม PDF (AcroForm, v1.45.0): Text · Checkbox · Dropdown · บันทึก · เลิกทำได้
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

const FORM_PDF = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "form.pdf");

async function uploadFormFixture(page) {
  await page.setInputFiles("input[type=file][accept*='.pdf']", FORM_PDF);
  await page.waitForURL("**/editor/**");
  await expect(page.locator("img.page-image[src^='data:image/']")).toBeVisible();
}

test("กรอกแบบฟอร์ม PDF: กรอกข้อความไทย · ติ๊กถูก · เลือกรายการ · บันทึก · เลิกทำได้", async ({ page }) => {
  await login(page);
  await uploadFormFixture(page);

  await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
  await page.getByRole("button", { name: /^กรอกแบบฟอร์ม\.\.\./ }).click();

  const panel = page.getByRole("complementary", { name: "แผงกรอกแบบฟอร์ม PDF" });
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("3 ช่อง", { timeout: 10_000 });
  await expect(page.getByTestId("form-fill-layer")).toBeVisible();

  // กรอกผ่านแผงด้านขวา (เชื่อม 2 ทางกับช่องบนหน้า)
  await panel.getByLabel("ชื่อ-นามสกุล").fill("สมชาย ใจดี");
  await panel.getByLabel("ยอมรับเงื่อนไข").check();
  await panel.getByLabel("แผนก").selectOption("ไอที");

  const saveBtn = panel.getByRole("button", { name: "บันทึกแบบฟอร์ม (3)" });
  await expect(saveBtn).toBeEnabled();
  await saveBtn.click();
  await expect(page.getByText(/บันทึกแบบฟอร์มเรียบร้อยแล้ว \(3 ช่อง\)/).first()).toBeVisible({ timeout: 15_000 });

  // เลิกทำ (Undo) → ค่าช่องชื่อกลับเป็นว่าง
  await page.getByTitle("เลิกทำ (Ctrl+Z)").click();
  await expect(panel.getByLabel("ชื่อ-นามสกุล")).toHaveValue("", { timeout: 10_000 });
});

test("มือถือ (390×844): เปิดกรอกแบบฟอร์มจากเมนูหลักแล้วกรอกและบันทึกได้", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await uploadFormFixture(page);

  await page.getByTitle("เมนูหลัก").click();
  await page.getByRole("button", { name: /^กรอกแบบฟอร์ม\.\.\./ }).click();

  const panel = page.getByRole("complementary", { name: "แผงกรอกแบบฟอร์ม PDF" });
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("3 ช่อง", { timeout: 10_000 });

  await panel.getByLabel("ชื่อ-นามสกุล").fill("สมหญิง ทดสอบ");
  await panel.getByRole("button", { name: "บันทึกแบบฟอร์ม (1)" }).click();
  await expect(page.getByText(/บันทึกแบบฟอร์มเรียบร้อยแล้ว \(1 ช่อง\)/).first()).toBeVisible({ timeout: 15_000 });
});
