import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

const TABLE_PDF = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "table.pdf");

// แก้ไขตาราง (v1.40.0) — table.pdf: ตาราง 4×4 ข้อมูลสมมติ (backend/scripts/create_table_fixture.py)
// คอลัมน์ x 60/110/300/420/535 pt · แถว y 120–225 pt · "รวมทั้งสิ้น ..." อยู่ใต้ตารางที่ y 300
test.describe("แก้ไขตาราง", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/dashboard");
    await page.setInputFiles("input[type=file][accept*='.pdf']", TABLE_PDF);
    await page.waitForURL("**/editor/**");
    await expect(page.locator("img[src^='data:image/']").first()).toBeVisible();
    await page.getByRole("button", { name: "แก้ไขตาราง", exact: true }).click();
    const panel = page.getByTestId("table-edit-panel");
    await expect(panel).toContainText("คลิกหรือแตะกรอบประสีฟ้า");
    await page.getByRole("button", { name: /เลือกตารางที่ 1 \(4 แถว × 4 คอลัมน์\)/ }).click();
    await expect(panel).toContainText("4 แถว × 4 คอลัมน์");
  });

  test("ลากย้าย · ย่อคอลัมน์จนตัดบรรทัด · ตกลง แล้ว Undo กลับ", async ({ page }) => {
    const panel = page.getByTestId("table-edit-panel");
    const left = panel.locator("#tbl-left");
    await expect(left).toHaveValue("21.2"); // 60 pt

    // ลากตารางไปทางขวา → ตำแหน่งซ้ายเพิ่ม แล้วรีเซ็ตกลับ
    const move = page.locator("[data-handle='ย้ายตาราง']");
    const box = await move.boundingBox();
    await page.mouse.move(box.x + 30, box.y + 10);
    await page.mouse.down();
    await page.mouse.move(box.x + 60, box.y + 10, { steps: 4 });
    await page.mouse.up();
    await expect.poll(async () => Number(await left.inputValue())).toBeGreaterThan(25);
    await panel.getByRole("button", { name: "รีเซ็ต" }).click();
    await expect(left).toHaveValue("21.2");

    // คอลัมน์ "รายการ" 190 pt → 30 มม. — "ค่าเดินทางไปประชุมวิชาการ" ไม่พอ ต้องตัดบรรทัดและแถวสูงขึ้น
    await expect(panel.locator("#tbl-col-1")).toHaveValue("67");
    await panel.locator("#tbl-col-1").fill("30");
    await panel.getByRole("button", { name: "ตกลง" }).click();
    await expect(panel.getByRole("status")).toContainText("แก้ตารางแล้ว");
    await expect(panel.getByRole("status")).toContainText("ตัดบรรทัดใหม่");
    await expect(panel.locator("#tbl-col-1")).toHaveValue("30"); // เลือกตารางเดิมค้างไว้แก้ต่อ
    await expect(page.getByRole("button", { name: "ตกลง" })).toBeDisabled();

    await page.getByRole("button", { name: /เลิกทำ/ }).first().click();
    await page.getByRole("button", { name: /เลือกตารางที่ 1/ }).click();
    await expect(panel.locator("#tbl-col-1")).toHaveValue("67");
  });

  test("ย้ายไปทับข้อความ → ถามยืนยันก่อน แล้ว 'วางทับต่อ' ได้", async ({ page }) => {
    const panel = page.getByTestId("table-edit-panel");
    await panel.locator("#tbl-top").fill("75"); // 212 pt → ตารางลงไปถึง ~317 pt ทับ "รวมทั้งสิ้น" ที่ y 300
    await panel.getByRole("button", { name: "ตกลง" }).click();
    const warning = panel.getByRole("alert").filter({ hasText: "ทับข้อความ" });
    await expect(warning).toBeVisible();
    await warning.getByRole("button", { name: "วางทับต่อ" }).click();
    await expect(panel.getByRole("status")).toContainText("แก้ตารางแล้ว");
    await expect(panel.locator("#tbl-top")).toHaveValue("75");
  });
});
