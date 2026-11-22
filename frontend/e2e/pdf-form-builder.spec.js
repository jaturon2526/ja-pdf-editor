// สร้างเอกสารเปล่า + ออกแบบแบบฟอร์ม PDF (v1.47.0): สร้างหน้าเปล่า → วางช่องฟอร์ม → กรอกและบันทึก → ลบ → Undo
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

test("สร้างเอกสารเปล่าจากหน้าแรก → วางช่องข้อความ → กรอกไทยและบันทึก → ลบช่อง → Undo คืนได้", async ({ page }) => {
  await login(page);

  await page.getByTestId("tool-card-create-blank").click();
  const dialog = page.getByRole("dialog", { name: "สร้างเอกสารเปล่า" });
  await expect(dialog).toBeVisible();

  await dialog.getByLabel("ชื่อไฟล์").fill("ใบสมัคร E2E.pdf");
  await dialog.getByRole("button", { name: "สร้างเอกสาร", exact: true }).click();

  await page.waitForURL("**/editor/**");
  await expect(page.locator("img.page-image[src^='data:image/']")).toBeVisible();

  // เปิดแผงออกแบบแบบฟอร์มให้อัตโนมัติ
  const panel = page.getByRole("complementary", { name: "แผงกรอกแบบฟอร์ม PDF" });
  await expect(panel).toBeVisible({ timeout: 10_000 });
  await expect(panel).toContainText("เพิ่มช่องแบบฟอร์มใหม่");

  // วางช่องข้อความ "ชื่อ-นามสกุล"
  await panel.getByLabel("ป้ายชื่อช่อง").fill("ชื่อ-นามสกุล");
  await panel.getByRole("button", { name: "+ วางช่องบนหน้า", exact: true }).click();
  await expect(page.getByTestId("form-draft-box")).toBeVisible();
  await panel.getByRole("button", { name: "ยืนยันวางช่อง", exact: true }).click();
  await expect(panel).toContainText("1 ช่อง", { timeout: 15_000 });

  // สลับไปแท็บ "กรอกฟอร์ม" → กรอกข้อความไทยและบันทึก
  await panel.getByRole("button", { name: "กรอกฟอร์ม", exact: true }).click();
  await panel.getByLabel("ชื่อ-นามสกุล").fill("สมชาย ทดสอบ");
  await panel.getByRole("button", { name: "บันทึกแบบฟอร์ม (1)", exact: true }).click();
  await expect(page.getByText(/บันทึกแบบฟอร์มเรียบร้อยแล้ว \(1 ช่อง\)/).first()).toBeVisible({ timeout: 15_000 });

  // สลับกลับ "ออกแบบฟอร์ม" → ลบช่อง → Undo คืนกลับมา
  await panel.getByRole("button", { name: "ออกแบบฟอร์ม", exact: true }).click();
  await panel.getByRole("button", { name: "ลบช่อง ชื่อ-นามสกุล" }).click();
  await expect(panel).toContainText("0 ช่อง", { timeout: 15_000 });

  await page.getByTitle("เลิกทำ (Ctrl+Z)").click();
  await expect(panel).toContainText("1 ช่อง", { timeout: 15_000 });
});
