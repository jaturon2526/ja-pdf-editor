// ตัดขอบหน้ากระดาษ (Crop Page, v1.44.0): กรอบลาก + ระยะ มม. + หน้านี้/ทุกหน้า + เลิกทำได้
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

test("ตัดขอบหน้ากระดาษ: ปรับระยะขอบ 20 มม. · ตัดหน้านี้ · ขนาดหน้าเล็กลง · เลิกทำคืนขนาดเดิมได้", async ({ page }) => {
  await login(page);
  await uploadSample(page);

  const sheet = page.locator(".page-sheet");
  const beforeBox = await sheet.boundingBox();
  expect(beforeBox).not.toBeNull();

  await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
  await page.getByRole("button", { name: /^ตัดขอบหน้ากระดาษ\.\.\./ }).click();

  await expect(page.getByTestId("crop-page-layer")).toBeVisible();
  const panel = page.getByRole("complementary", { name: "แผงตัดขอบหน้ากระดาษ" });
  await expect(panel).toBeVisible();

  await panel.getByRole("button", { name: "20 มม.", exact: true }).click();
  await panel.getByRole("button", { name: "ตัดขอบ", exact: true }).click();

  await expect(page.getByText(/ตัดขอบหน้ากระดาษเรียบร้อยแล้ว \(1 หน้า\)/).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("crop-page-layer")).toBeHidden();

  await expect
    .poll(async () => (await sheet.boundingBox())?.width ?? 9999, { timeout: 10_000 })
    .toBeLessThan(beforeBox.width - 20);

  // เลิกทำ (Undo) → ขนาดหน้ากลับเป็นเดิม
  await page.getByTitle("เลิกทำ (Ctrl+Z)").click();
  await expect
    .poll(async () => Math.abs(((await sheet.boundingBox())?.width ?? 0) - beforeBox.width), { timeout: 10_000 })
    .toBeLessThan(5);
});

test("มือถือ (390×844): เปิดตัดขอบหน้ากระดาษจากเมนูหลักแล้วตัดขอบได้", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await uploadSample(page);

  await page.getByTitle("เมนูหลัก").click();
  await page.getByRole("button", { name: /^ตัดขอบหน้ากระดาษ\.\.\./ }).click();

  const panel = page.getByRole("complementary", { name: "แผงตัดขอบหน้ากระดาษ" });
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("crop-page-layer")).toBeVisible();

  await panel.getByRole("button", { name: "ตัดขอบ", exact: true }).click();
  await expect(page.getByText(/ตัดขอบหน้ากระดาษเรียบร้อยแล้ว \(1 หน้า\)/).first()).toBeVisible({ timeout: 15_000 });
});
