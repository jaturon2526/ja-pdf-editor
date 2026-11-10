// แทรกรูปภาพ: เมนูแทรก › แทรกรูปภาพ = เลือกไฟล์แล้ววางรูปให้ย้าย/ปรับขนาด (ไม่ต้องคลิกบนหน้าก่อน)
// เครื่องมือ › แก้ไขรูปภาพ = ลากไฟล์รูปมาวางบนหน้าได้ ตรงจุดที่ปล่อย
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

// PNG 40x20 พิกเซล (แนวนอน 2:1) — กล่องที่วางต้องกว้างกว่าสูงตามสัดส่วนรูป
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAACgAAAAUCAIAAABwJOjsAAAALUlEQVR4nGO8o6HBQC7wqRAhWy8T2TopBKMWj1o8avGoxaMWj1o8avGoxfQHAJ+1AixR3IeNAAAAAElFTkSuQmCC", "base64");

async function boxSize(page) {
  const box = await page.locator(".image-edit-box").boundingBox();
  return { w: box.width, h: box.height, x: box.x, y: box.y };
}

test("เมนูแทรก › แทรกรูปภาพ เปิดเลือกไฟล์ทันที แล้วย้าย/บันทึกได้", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.getByRole("button", { name: "แทรก", exact: true }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByText("แทรกรูปภาพ", { exact: true }).last().click();
  await (await chooser).setFiles({ name: "logo.png", mimeType: "image/png", buffer: PNG });

  const edit = page.locator(".image-edit-box");
  await expect(edit).toBeVisible();
  await expect(edit.locator("img.image-edit-preview")).toBeVisible();
  const before = await boxSize(page);
  expect(before.w).toBeGreaterThan(before.h * 1.8); // สัดส่วน 2:1

  // ลากย้ายได้
  await page.mouse.move(before.x + before.w / 2, before.y + before.h / 2);
  await page.mouse.down();
  await page.mouse.move(before.x + before.w / 2 + 60, before.y + before.h / 2 + 40, { steps: 5 });
  await page.mouse.up();
  const after = await boxSize(page);
  expect(after.x).toBeGreaterThan(before.x + 30);

  await page.getByRole("button", { name: "ตกลง" }).click();
  await page.getByTitle("บันทึกการแก้ไขทั้งหมดลงไฟล์จริง").click();
  await expect(page.getByText(/บันทึกการแก้ไขทั้งหมดสำเร็จ \(1 จุด\)/).first()).toBeVisible({ timeout: 20_000 });
});

test("เครื่องมือ › แก้ไขรูปภาพ: ลากไฟล์รูปมาวางบนหน้า = แทรกรูปตรงจุดที่ปล่อย", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
  await page.getByText("แก้ไขรูปภาพ", { exact: true }).click();
  await expect(page.getByText("ลากไฟล์รูปภาพมาวางบนหน้า")).toBeVisible();

  const pageImg = page.locator(".canvas-area img[src^='data:image/']").first();
  const rect = await pageImg.boundingBox();
  const target = { x: rect.x + rect.width * 0.5, y: rect.y + rect.height * 0.3 };
  const data = await page.evaluateHandle((b64) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], "drop.png", { type: "image/png" }));
    return dt;
  }, PNG.toString("base64"));
  await page.dispatchEvent(".canvas-area", "dragover", { dataTransfer: data, clientX: target.x, clientY: target.y });
  await expect(page.locator(".canvas-area.image-drop-target")).toBeVisible();
  await page.dispatchEvent(".canvas-area", "drop", { dataTransfer: data, clientX: target.x, clientY: target.y });

  const edit = page.locator(".image-edit-box");
  await expect(edit).toBeVisible();
  await expect(page.locator(".canvas-area.image-drop-target")).toHaveCount(0);
  const box = await boxSize(page);
  expect(Math.abs(box.x + box.w / 2 - target.x)).toBeLessThan(12); // กึ่งกลางรูป = จุดที่ปล่อย
  expect(Math.abs(box.y + box.h / 2 - target.y)).toBeLessThan(12);
  await expect(page).toHaveURL(/\/editor\//); // ไม่ได้เปิดเป็นเอกสารใหม่
});
