// เซ็นเซอร์ด้วยคำค้นหา: ค้นไม่เจอเพราะข้อความอยู่ในรูป → ปุ่ม "อ่านข้อความในรูป (OCR) แล้วค้นหาอีกครั้ง" → เซ็นเซอร์ได้
// จำลอง redact-search / ocr-text-layer ในเบราว์เซอร์ (OCR จริงทดสอบใน backend/tests/test_thai_ocr.py)
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

test("ค้นไม่เจอในหน้าที่มีรูป → อ่านข้อความในรูปด้วย OCR → ค้นหาซ้ำแล้วเซ็นเซอร์ได้", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  let ocrDone = false;
  const calls = [];
  await page.route("**/api/pdf/*/redact-search", (route) => {
    calls.push("search");
    return route.fulfill({ json: ocrDone ? { status: "ok", redacted_count: 1 } : { status: "ok", redacted_count: 0, image_pages: [1] } });
  });
  await page.route("**/api/pdf/*/ocr-text-layer", (route) => {
    calls.push(`ocr ${route.request().postData()}`);
    ocrDone = true;
    return route.fulfill({ json: { pages: [1], words: 12, skipped_pages: 0 } });
  });

  await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
  await page.getByText("เซ็นเซอร์ด้วยคำค้นหา...").click();
  await page.getByPlaceholder("เช่น เลขบัตรประชาชน, ชื่อ").fill("ผู้อำนวยการสำนักเงินสมทบ");
  await page.getByRole("button", { name: "เริ่มเซ็นเซอร์" }).click();
  await expect(page.getByText(/หน้า 1 มีรูปภาพ/)).toBeVisible();
  await page.getByTestId("ocr-retry").click();
  await expect(page.getByText("ลบข้อความสำเร็จ! พบและเซ็นเซอร์ทั้งหมด 1 จุด")).toBeVisible();
  expect(calls).toEqual(["search", 'ocr {"pages":[0]}', "search"]);
});
