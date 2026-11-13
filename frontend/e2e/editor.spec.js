import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

test.describe("Editor", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await uploadSample(page);
  });

  test("หมุนหน้าแล้ว undo/redo ได้", async ({ page }) => {
    const thumbs = page.locator("img[src^='data:image/']");
    await expect(thumbs).toHaveCount(4); // หน้าหลัก 1 + thumbnail 3
    await thumbs.nth(1).click({ button: "right" });
    await page.getByRole("menuitem", { name: /^หมุนขวา/ }).click();
    await expect(page.getByText("หมุนหน้าสำเร็จ")).toBeVisible();

    await page.locator("body").click({ position: { x: 700, y: 400 } });
    await page.keyboard.press("Control+z");
    await expect(page.getByText("เลิกทำ (Undo) สำเร็จ")).toBeVisible();
    await page.keyboard.press("Control+y");
    await expect(page.getByText("ทำซ้ำ (Redo) สำเร็จ")).toBeVisible();
  });

  test("เมนูคลิกขวาอยู่ในหน้าจอเสมอ และกล่องหลักไม่เลื่อน", async ({ page }) => {
    const vp = page.viewportSize();
    await page.mouse.click(vp.width - 10, vp.height - 40, { button: "right" });
    const menu = page.getByText("หมุนขวา ↻ (90°)").locator("xpath=ancestor::div[contains(@style,'position: fixed')][1]");
    const box = await menu.boundingBox();
    expect(box.x + box.width).toBeLessThanOrEqual(vp.width);
    expect(box.y + box.height).toBeLessThanOrEqual(vp.height);
    const rootScroll = await page.evaluate(() => document.querySelector("#root > div").scrollTop);
    expect(rootScroll).toBe(0);
  });

  test("ปิดเอกสารแล้วปุ่มเปิดไฟล์อยู่กลางพื้นที่เอกสาร", async ({ page }) => {
    await page.getByRole("button", { name: "ไฟล์", exact: true }).click();
    await page.getByText("ปิดเอกสาร", { exact: true }).click();
    const btn = page.getByRole("button", { name: "เปิดไฟล์ PDF" });
    await expect(btn).toBeVisible();
    const area = await page.locator(".canvas-area").boundingBox();
    const b = await btn.boundingBox();
    expect(Math.abs(b.x + b.width / 2 - (area.x + area.width / 2))).toBeLessThan(4);
    expect(Math.abs(b.y + b.height / 2 - (area.y + area.height / 2))).toBeLessThan(area.height / 4);
  });

  test("ดาวน์โหลดไฟล์ PDF ได้", async ({ page }) => {
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "ดาวน์โหลดลงเครื่อง" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.pdf$/);
  });

  test("เอกสารที่มีหน้าแนวนอนให้เลือกพิมพ์ตามที่เห็นบนจอ", async ({ page }) => {
    const thumbs = page.locator("img[src^='data:image/']");
    await thumbs.nth(1).click({ button: "right" });
    await page.getByRole("menuitem", { name: /^หมุนซ้าย/ }).click();
    await expect(page.getByText("หมุนหน้าสำเร็จ")).toBeVisible();

    await page.getByRole("button", { name: "พิมพ์เอกสาร (Ctrl+P)" }).click();
    const printRequest = page.waitForResponse((r) => r.url().includes("/print?layout=as_shown"));
    await page.getByRole("button", { name: /พิมพ์ตามที่เห็นบนจอ/ }).click();
    const res = await printRequest;
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("application/pdf");
  });

  test("เมนูบนเปิดหน้าต่างได้ และกด Esc ปิดหน้าต่าง", async ({ page }) => {
    await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
    await page.getByText("ลดขนาดไฟล์...").click();
    await expect(page.getByText("ลดขนาดไฟล์ (Compress PDF)")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByText("ลดขนาดไฟล์ (Compress PDF)")).toBeHidden();
  });

  test("ใส่ลายน้ำแล้วเลิกทำได้ (งานที่เปลี่ยนเอกสารผ่าน runDocumentChange)", async ({ page }) => {
    await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
    await page.getByText("ใส่ลายน้ำ...").click();
    await page.getByPlaceholder("เช่น CONFIDENTIAL").fill("E2E");
    await page.getByRole("dialog", { name: "ใส่ลายน้ำ" }).getByRole("button", { name: "ใส่ลายน้ำ", exact: true }).click();
    await expect(page.getByText("ประทับลายน้ำเรียบร้อยแล้ว")).toBeVisible();
    await page.getByRole("button", { name: "แก้ไข", exact: true }).click();
    await page.getByText("เลิกทำ", { exact: true }).click();
    await expect(page.getByText("เลิกทำ (Undo) สำเร็จ")).toBeVisible();
  });
});
