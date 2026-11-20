import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

// แทรกหน้า (v1.39.0) — sample.pdf 3 หน้า · compare-a.pdf 2 หน้า
test.describe("แทรกหน้า", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/dashboard");
    await uploadSample(page);
    await expect(page.locator(".thumbnail-item img")).toHaveCount(3);
  });

  test("แผงหน้า › แทรกหลังหน้านี้ › จากเครื่อง เลือกหน้าที่ต้องการ แล้ว Undo ได้", async ({ page }) => {
    await page.locator(".thumbnail-item").nth(0).click({ button: "right" });
    await page.getByRole("menuitem", { name: "แทรกหน้าหลังหน้านี้" }).click();
    const dialog = page.getByRole("dialog", { name: "แทรกหน้า" });
    await expect(dialog.getByLabel("ตำแหน่งที่แทรก")).toHaveValue("1");

    await dialog.getByTestId("insert-pages-file").setInputFiles(path.join(FIXTURES, "compare-a.pdf"));
    await expect(dialog.locator("#insert-pages-range")).toHaveValue("1-2");
    await expect(dialog.getByTestId("insert-pages-thumbs").locator("img")).toHaveCount(2);
    // เลือกเฉพาะหน้า 2 ด้วยการกดภาพย่อหน้า 1 ออก
    await dialog.getByRole("button", { name: "หน้า 1 ของไฟล์ต้นทาง" }).click();
    await expect(dialog.locator("#insert-pages-range")).toHaveValue("2");
    await dialog.locator("#insert-pages-range").fill("9");
    await expect(dialog.getByRole("alert")).toContainText("เกิน 2 หน้า");
    await expect(dialog.getByRole("button", { name: "แทรกหน้า", exact: true })).toBeDisabled();
    await dialog.locator("#insert-pages-range").fill("2");
    await expect(dialog).toContainText("จะแทรก 1 หน้า หลังหน้า 1");
    await dialog.getByRole("button", { name: "แทรกหน้า", exact: true }).click();

    await expect(dialog).toHaveCount(0);
    await expect(page.getByText("แทรก 1 หน้าแล้ว")).toBeVisible();
    await expect(page.locator(".thumbnail-item")).toHaveCount(4);
    await page.getByRole("button", { name: /เลิกทำ/ }).first().click();
    await expect(page.locator(".thumbnail-item")).toHaveCount(3);
  });

  test("หน้าว่าง และแทรกซ้ำจากไฟล์ที่เปิดอยู่ (เอกสารของฉัน)", async ({ page }) => {
    await page.getByRole("button", { name: "＋ แทรกหน้า" }).click();
    const dialog = page.getByRole("dialog", { name: "แทรกหน้า" });
    await expect(dialog.getByLabel("ตำแหน่งที่แทรก")).toHaveValue("3"); // ท้ายเอกสาร
    await dialog.getByRole("tab", { name: "หน้าว่าง" }).click();
    await dialog.getByLabel("จำนวนหน้า").fill("2");
    await dialog.getByLabel("ขนาดหน้า").selectOption("a4-landscape");
    await dialog.getByRole("button", { name: "แทรกหน้า", exact: true }).click();
    await expect(page.locator(".thumbnail-item")).toHaveCount(5);

    await page.getByRole("button", { name: "แทรก", exact: true }).click();
    await page.getByRole("button", { name: /^แทรกหน้า\.\.\./ }).click();
    const dialog2 = page.getByRole("dialog", { name: "แทรกหน้า" });
    await dialog2.getByRole("tab", { name: "เอกสารของฉัน" }).click();
    await dialog2.getByTestId("insert-pages-mine").getByRole("button", { name: /ไฟล์ที่เปิดอยู่/ }).click();
    await dialog2.locator("#insert-pages-range").fill("1");
    await dialog2.getByLabel("ตำแหน่งที่แทรก").selectOption("0");
    await dialog2.getByRole("button", { name: "แทรกหน้า", exact: true }).click();
    await expect(dialog2).toHaveCount(0);
    await expect(page.locator(".thumbnail-item")).toHaveCount(6);
  });

  test("แทรกจากไฟล์ Word (แปลงเป็น PDF ก่อน)", async ({ page }) => {
    test.setTimeout(120_000);
    await page.getByRole("button", { name: "＋ แทรกหน้า" }).click();
    const dialog = page.getByRole("dialog", { name: "แทรกหน้า" });
    await dialog.getByTestId("insert-pages-file").setInputFiles(path.join(FIXTURES, "sample.docx"));
    await expect(dialog).toContainText("sample.pdf", { timeout: 90_000 });
    await dialog.getByRole("button", { name: "แทรกหน้า", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".thumbnail-item")).not.toHaveCount(3);
  });
});
