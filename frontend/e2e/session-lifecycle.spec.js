// คืนหน่วยความจำ: ออกจากหน้าแก้ไข → เอกสารบนเซิร์ฟเวอร์ถูกปิด · เปิดลิงก์เดิม/รีเฟรช → เปิดใหม่จากไฟล์ที่บันทึกให้เอง
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

async function infoStatus(page, sid) {
  return page.evaluate(async (id) => {
    const r = await fetch(`/api/pdf/${id}/info`, { headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
    return r.status;
  }, sid);
}

test("กลับหน้าเอกสารของฉันแล้วปิด session · เปิดลิงก์เดิมแล้วเปิดใหม่จากไฟล์ที่บันทึก", async ({ page }) => {
  await login(page);
  const sid = await uploadSample(page);
  expect(await infoStatus(page, sid)).toBe(200);
  await page.getByRole("button", { name: "ไฟล์", exact: true }).click();
  await page.getByText("← กลับหน้าเอกสารของฉัน").click();
  await page.waitForURL("**/dashboard");
  await expect.poll(() => infoStatus(page, sid)).toBe(404);

  await page.goto(`/editor/${sid}`);
  await page.waitForURL((url) => url.pathname.startsWith("/editor/") && !url.pathname.endsWith(sid));
  await expect(page.locator("img[src^='data:image/']").first()).toBeVisible();

  // รีเฟรชหน้า (ไม่มีงานค้าง) → ปิดตอน pagehide แล้วเปิดใหม่ได้
  const current = page.url().split("/").pop();
  await page.reload();
  await expect(page.locator("img[src^='data:image/']").first()).toBeVisible();
  expect(page.url().split("/").pop()).not.toBe(current);
});
