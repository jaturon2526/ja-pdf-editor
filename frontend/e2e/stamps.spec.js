// ตราประทับสำเร็จรูป (Stamps, v1.43.0): เลือกแบบสำเร็จรูป/กำหนดเอง → วางบนหน้า → บันทึกการแก้ไข → เลิกทำได้
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

test("ตราประทับสำเร็จรูป: เลือกแบบ อนุมัติแล้ว · วางบนหน้า · บันทึกการแก้ไข · เลิกทำได้", async ({ page }) => {
  await login(page);
  await uploadSample(page);

  await page.getByRole("button", { name: "แทรก", exact: true }).click();
  await page.getByRole("button", { name: /^ตราประทับ\.\.\./ }).click();

  const dialog = page.getByRole("dialog", { name: "ตราประทับสำเร็จรูป" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("canvas")).toBeVisible();

  await dialog.getByRole("button", { name: "อนุมัติแล้ว", exact: true }).click();
  await expect(dialog.getByLabel("ข้อความบนตราประทับ")).toHaveValue("อนุมัติแล้ว");
  await dialog.getByRole("button", { name: "วางตราประทับ", exact: true }).click();
  await expect(dialog).toBeHidden();

  // กล่องตราประทับวางบนหน้าแล้ว → ตกลง → บันทึกการแก้ไข
  const stampBox = page.locator(".page-sheet img[src^='blob:']").first();
  await expect(stampBox).toBeVisible({ timeout: 10_000 });
  await page.locator(".page-sheet").getByRole("button", { name: "ตกลง", exact: true }).click();
  await page.getByTitle("บันทึกการแก้ไขทั้งหมดลงไฟล์จริง").click();
  await expect(page.getByText(/บันทึกการแก้ไขทั้งหมดสำเร็จ \(1 จุด\)/).first()).toBeVisible({ timeout: 20_000 });

  // เลิกทำได้ (Undo)
  const undoBtn = page.getByTitle("เลิกทำ (Ctrl+Z)");
  await expect(undoBtn).toBeEnabled();
  await undoBtn.click();
  await expect(page.getByTitle("ทำซ้ำ (Ctrl+Y)")).toBeEnabled({ timeout: 10_000 });
});

test("มือถือ (390×844): เปิดตราประทับจากเมนูหลักแล้ววางตรา ลับ ได้", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await uploadSample(page);

  await page.getByTitle("เมนูหลัก").click();
  await page.getByRole("button", { name: /^ตราประทับ\.\.\./ }).click();

  const dialog = page.getByRole("dialog", { name: "ตราประทับสำเร็จรูป" });
  await expect(dialog).toBeVisible();

  await dialog.getByRole("button", { name: "ลับ", exact: true }).click();
  await dialog.getByRole("button", { name: "วางตราประทับ", exact: true }).click();
  await expect(dialog).toBeHidden();

  await expect(page.locator(".page-sheet img[src^='blob:']").first()).toBeVisible({ timeout: 10_000 });
});
