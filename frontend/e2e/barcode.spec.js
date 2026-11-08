// แทรกบาร์โค้ด: เลือกประเภท → ตรวจข้อมูล (หน้าเว็บ + backend) → ตัวอย่าง → ตกลง → กล่องลากวางบนหน้า → บันทึกเป็นเวกเตอร์
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

test("แทรก QR ภาษาไทย + ตรวจข้อมูล EAN-13 ก่อนกดตกลง", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.getByRole("button", { name: "แทรก", exact: true }).click();
  await page.getByText("บาร์โค้ด / QR Code...").click();
  const form = page.getByRole("dialog", { name: "แทรกบาร์โค้ด" });
  const ok = form.getByRole("button", { name: "ตกลง", exact: true });

  // EAN-13: เลขตรวจสอบผิด → backend แจ้งเหตุผล กดตกลงไม่ได้ · 12 หลัก → เติมเลขตรวจสอบให้
  await form.getByLabel("ประเภท").selectOption("ean13");
  await form.getByLabel("ข้อมูล").fill("885000000001");
  await expect(form.getByTestId("barcode-adjusted")).toContainText("8850000000010", { timeout: 15_000 });
  await form.getByLabel("ข้อมูล").fill("8850000000019");
  await expect(form.getByRole("alert")).toContainText("เลขตรวจสอบ", { timeout: 15_000 });
  await expect(ok).toBeDisabled();
  // ภาษาไทยในประเภท 1 มิติ → แจ้งทันที
  await form.getByLabel("ประเภท").selectOption("code128");
  await form.getByLabel("ข้อมูล").fill("ไทย");
  await expect(form.getByRole("alert")).toContainText("QR Code");

  await form.getByLabel("ประเภท").selectOption("qrcode");
  await form.getByLabel("ข้อมูล").fill("ใบแจ้งหนี้ เลขที่ ๑๒๓");
  await expect(form.getByTestId("barcode-preview").locator("img")).toBeVisible({ timeout: 15_000 });
  await expect(ok).toBeEnabled();
  await ok.click();

  // กล่องลากวางบนหน้า (โหมดแก้ไขรูป) → ตกลง → บันทึกการแก้ไข
  const box = page.locator(".page-sheet img[src^='blob:']").first();
  await expect(box).toBeVisible();
  await page.locator(".page-sheet").getByRole("button", { name: "ตกลง", exact: true }).click();
  await page.getByTitle("บันทึกการแก้ไขทั้งหมดลงไฟล์จริง").click();
  await expect(page.getByText(/บันทึกการแก้ไขทั้งหมดสำเร็จ \(1 จุด\)/).first()).toBeVisible({ timeout: 20_000 });
});
