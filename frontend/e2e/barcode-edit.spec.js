import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

const BARCODES_PDF = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "barcodes.pdf");

// ย้าย/ลบบาร์โค้ด (v1.41.0) — barcodes.pdf: Code 128 "DN-0001" แบบเวกเตอร์ + QR แบบรูปภาพ (ข้อมูลสมมติ,
// backend/scripts/create_barcode_fixture.py)
test("ย้าย/ลบบาร์โค้ด: ลากย้าย ตกลง · ลบ QR · เลิกทำกลับมา", async ({ page }) => {
  await login(page);
  await page.goto("/dashboard");
  await page.setInputFiles("input[type=file][accept*='.pdf']", BARCODES_PDF);
  await page.waitForURL("**/editor/**");
  await expect(page.locator("img.page-image[src^='data:image/']")).toBeVisible();

  await page.getByRole("button", { name: "ย้าย / ลบบาร์โค้ด", exact: true }).click();
  const panel = page.getByTestId("barcode-edit-panel");
  await expect(panel).toContainText("2 รายการในหน้านี้");

  // ย้าย Code 128 ลงมา
  await page.getByRole("button", { name: /เลือกบาร์โค้ดที่ \d+: Code128 “DN-0001”/ }).click();
  await expect(panel.getByTestId("barcode-selected")).toContainText("DN-0001");
  const top = panel.locator("#bc-top");
  const before = Number(await top.inputValue());
  const handle = page.locator("[data-handle='ย้ายบาร์โค้ด']");
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 200, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => Number(await top.inputValue())).toBeGreaterThan(before + 40);
  await panel.getByRole("button", { name: "ตกลง" }).click();
  await expect(panel.getByRole("status")).toContainText("ย้ายบาร์โค้ดแล้ว");
  await expect(panel.getByTestId("barcode-selected")).toContainText("DN-0001"); // เลือกค้างที่ตำแหน่งใหม่
  await expect.poll(async () => Number(await top.inputValue())).toBeGreaterThan(before + 40);

  // ลบ QR
  await page.getByRole("button", { name: /เลือกบาร์โค้ดที่ \d+: QRCode/ }).click();
  await panel.getByRole("button", { name: "ลบบาร์โค้ดนี้" }).click();
  await expect(panel.getByRole("status")).toContainText("ลบบาร์โค้ดแล้ว");
  await expect(panel).toContainText("1 รายการในหน้านี้");

  // เลิกทำ → QR กลับมา (เครื่องมือยังเปิดอยู่)
  await page.getByRole("button", { name: /เลิกทำ/ }).first().click();
  await expect(panel).toContainText("2 รายการในหน้านี้");
});

test("มือถือ (390×844): เปิดจากเมนูหลัก · แผ่นล่างไม่บังบาร์โค้ด · ลากย้ายได้", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/dashboard");
  await page.setInputFiles("input[type=file][accept*='.pdf']", BARCODES_PDF);
  await page.waitForURL("**/editor/**");
  await expect(page.locator("img.page-image[src^='data:image/']")).toBeVisible();

  await page.getByTitle("เมนูหลัก").click();
  await page.getByRole("button", { name: /^ย้าย \/ ลบบาร์โค้ด บาร์โค้ดและ QR/ }).click();
  const panel = page.getByTestId("barcode-edit-panel");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("2 รายการในหน้านี้");

  const bcBtn = page.getByRole("button", { name: /เลือกบาร์โค้ดที่ \d+: Code128 “DN-0001”/ });
  const bcBox = await bcBtn.boundingBox();
  const panelBox = await panel.boundingBox();
  expect(bcBox.y + bcBox.height).toBeLessThan(panelBox.y); // แผ่นล่างไม่บังบาร์โค้ด

  await bcBtn.click();
  const handle = page.locator("[data-handle='ย้ายบาร์โค้ด']");
  await expect(handle).toHaveCSS("touch-action", "none");
  const top = panel.locator("#bc-top");
  const before = Number(await top.inputValue());
  const box = await handle.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 60, { steps: 4 });
  await page.mouse.up();
  await expect.poll(async () => Number(await top.inputValue())).toBeGreaterThan(before + 10);
  await panel.getByRole("button", { name: "ตกลง" }).click();
  await expect(panel.getByRole("status")).toContainText("ย้ายบาร์โค้ดแล้ว");
});
