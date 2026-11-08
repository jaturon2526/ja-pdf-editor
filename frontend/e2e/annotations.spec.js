import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

// คำอธิบายประกอบ (sample.pdf หน้า 1: บรรทัดทดสอบที่ y≈105–123, 145–163, 185–203 pt, x 60–222)
async function pagePoint(page, xPt, yPt) {
  const img = page.locator("img.page-image");
  const box = await img.boundingBox();
  const scale = box.width / 595;
  return { x: box.x + xPt * scale, y: box.y + yPt * scale };
}

async function drag(page, from, to) {
  const a = await pagePoint(page, ...from);
  const b = await pagePoint(page, ...to);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move((a.x + b.x) / 2, (a.y + b.y) / 2, { steps: 4 });
  await page.mouse.move(b.x, b.y, { steps: 4 });
  await page.mouse.up();
}

test.describe("คำอธิบายประกอบ", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await uploadSample(page);
    await expect(page.locator("img.page-image")).toBeVisible();
  });

  test("ไฮไลต์หลายบรรทัดเป็นรายการเดียว — Undo ครั้งเดียวหายทั้งหมด", async ({ page }) => {
    await page.getByRole("button", { name: "เน้นข้อความ" }).click();
    await drag(page, [58, 108], [224, 200]);
    await expect(page.getByText(/ไฮไลท์ข้อความสำเร็จ \(3 บรรทัด\)/)).toBeVisible();
    await page.getByRole("button", { name: "เลือก", exact: true }).click();
    await expect(page.locator(".annot-box-highlight")).toHaveCount(1);
    await page.getByRole("button", { name: "เลิกทำ (Ctrl+Z)" }).click();
    await expect(page.getByText("เลิกทำ (Undo) สำเร็จ")).toBeVisible();
    await expect(page.locator(".annot-box-highlight")).toHaveCount(0);
  });

  test("กล่องข้อความ: ข้อความอยู่ในรูปหน้าเอกสาร และกดตกลงโดยไม่แก้ไม่สร้างขั้น Undo เปล่า", async ({ page }) => {
    await page.getByRole("button", { name: "กล่องข้อความ" }).click();
    const p = await pagePoint(page, 300, 500);
    await page.mouse.click(p.x, p.y);
    await page.getByPlaceholder(/พิมพ์ข้อความ/).fill("ทดสอบกล่องข้อความ");
    await page.getByRole("button", { name: "เพิ่ม", exact: true }).click();
    await expect(page.getByText("เพิ่มกล่องข้อความสำเร็จ")).toBeVisible();
    await page.getByRole("button", { name: "เลือก", exact: true }).click();
    const boxEl = page.locator(".annot-box-freetext");
    await expect(boxEl).toHaveCount(1);
    await expect(page.locator(".annot-box-text")).toHaveCount(0); // ไม่วาดทับ — ข้อความอยู่ใน appearance ของไฟล์แล้ว

    let patched = 0;
    page.on("request", (r) => r.method() === "PATCH" && r.url().includes("/annotation/") && patched++);
    await boxEl.click();
    await page.getByRole("button", { name: "ตกลง", exact: true }).click();
    await expect(page.locator(".annot-box-freetext.editing")).toHaveCount(0);
    expect(patched).toBe(0);
  });
});
