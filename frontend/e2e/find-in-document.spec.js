import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

// ค้นหาข้อความในเอกสาร (Ctrl+F, v1.42.0) — sample.pdf มี 3 หน้า ("E2E หน้า 1..3" และ "บรรทัดทดสอบ ...")
test("ค้นหาข้อความในเอกสาร (Ctrl+F): นับจำนวน · ไฮไลต์ · กระโดดข้ามหน้า · ปิดด้วย Esc", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await expect(page.locator("img.page-image[src^='data:image/']")).toBeVisible();

  await page.keyboard.press("Control+f");
  const bar = page.getByTestId("find-bar");
  await expect(bar).toBeVisible();

  const input = bar.getByPlaceholder("ค้นหาในเอกสาร...");
  await input.fill("E2E");
  await expect(bar.getByTestId("find-status")).toHaveText("1 / 3");
  await expect(page.getByTestId("find-highlight-active")).toBeVisible();

  // กด Enter เพื่อกระโดดไปหน้าที่ 2 (ผลลัพธ์ที่ 2 / 3)
  await input.press("Enter");
  await expect(bar.getByTestId("find-status")).toHaveText("2 / 3");

  // กดปุ่มก่อนหน้ากลับมาที่ 1 / 3
  await bar.getByRole("button", { name: "ผลลัพธ์ก่อนหน้า" }).click();
  await expect(bar.getByTestId("find-status")).toHaveText("1 / 3");

  // ปิดด้วย Esc → แถบหายและไฮไลต์หาย
  await input.press("Escape");
  await expect(bar).toBeHidden();
  await expect(page.getByTestId("find-highlight-active")).toHaveCount(0);
});

test("มือถือ (390×844): เปิดค้นหาจากปุ่มบนแถบเครื่องมือและค้นหาคำไทยได้", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await uploadSample(page);
  await expect(page.locator("img.page-image[src^='data:image/']")).toBeVisible();

  await page.getByRole("button", { name: "ค้นหาในเอกสาร (Ctrl+F)" }).click();
  const bar = page.getByTestId("find-bar");
  await expect(bar).toBeVisible();
  await bar.getByPlaceholder("ค้นหาในเอกสาร...").fill("บรรทัดทดสอบ");
  await expect(bar.getByTestId("find-status")).toContainText("1 /");
  await bar.getByRole("button", { name: "ปิดแถบค้นหา" }).click();
  await expect(bar).toBeHidden();
});
