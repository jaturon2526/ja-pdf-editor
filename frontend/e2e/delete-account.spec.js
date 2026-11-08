// ลบบัญชี (หน้าโปรไฟล์): ต้องเห็นคำเตือน/สิ่งที่จะถูกลบ ติ๊กยอมรับ พิมพ์อีเมล และใส่รหัสผ่านก่อนจึงกดลบได้
// จำลอง /api/auth/account/* เพื่อไม่ลบผู้ใช้ทดสอบจริง (การลบจริงทดสอบใน backend/tests/test_account_deletion.py)
import { expect, test } from "@playwright/test";
import { EMAIL, login } from "./helpers.js";

const SUMMARY = {
  email: EMAIL, files: 3, storage_bytes: 2.5 * 1024 * 1024, requests_in_progress: 1, requests_total: 4,
  pending_as_signer: 2, signed_for_others: 1, passkeys: 0, line_linked: true, is_last_admin: false,
};

test("ลบบัญชี: คำเตือนครบ ปุ่มกดได้เมื่อยืนยันครบ รหัสผิดแจ้งเตือน และลบแล้วกลับหน้าเข้าสู่ระบบ", async ({ page }) => {
  await login(page);
  const deleteCalls = [];
  await page.route("**/api/auth/account/deletion-summary", (route) => route.fulfill({ json: SUMMARY }));
  await page.route("**/api/auth/account/delete", (route) => {
    const body = route.request().postDataJSON();
    deleteCalls.push(body);
    if (body.password !== "right-password") return route.fulfill({ status: 400, json: { detail: "รหัสผ่านไม่ถูกต้อง" } });
    return route.fulfill({ json: { deleted: true } });
  });

  await page.goto("/profile");
  const section = page.getByTestId("delete-account-section");
  await section.getByRole("button", { name: "ลบบัญชีของฉัน..." }).click();
  const dialog = page.getByRole("dialog", { name: "ลบบัญชีถาวร" });
  await expect(dialog.getByRole("alert").first()).toContainText("การลบบัญชีกู้คืนไม่ได้");
  const summary = dialog.getByTestId("delete-summary");
  await expect(summary).toContainText("3 ไฟล์ (2.5 MB)");
  await expect(summary).toContainText("ที่ยังค้าง 1 รายการจะถูกยกเลิกและแจ้งผู้ลงนาม");
  await expect(summary).toContainText("รอคุณลงนาม 2 รายการ — จะถูกปฏิเสธอัตโนมัติ");
  await expect(summary).toContainText("บล็อกเองได้ใน LINE");

  const del = dialog.getByRole("button", { name: "ลบบัญชีถาวร" });
  await expect(del).toBeDisabled();
  await dialog.getByLabel(/ฉันเข้าใจว่าบัญชี/).check();
  await dialog.getByLabel(/พิมพ์อีเมล/).fill("wrong@example.com");
  await dialog.getByLabel("รหัสผ่านปัจจุบัน").fill("bad");
  await expect(del).toBeDisabled(); // อีเมลไม่ตรง
  await dialog.getByLabel(/พิมพ์อีเมล/).fill(EMAIL.toUpperCase());
  await expect(del).toBeEnabled();

  await del.click();
  await expect(dialog).toContainText("รหัสผ่านไม่ถูกต้อง");
  await expect(page).toHaveURL(/\/profile$/);

  await dialog.getByLabel("รหัสผ่านปัจจุบัน").fill("right-password");
  await del.click();
  await page.waitForURL("**/login?deleted=1");
  await expect(page.getByText("ลบบัญชีพร้อมไฟล์และข้อมูลทั้งหมดเรียบร้อยแล้ว")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("token"))).toBeNull();
  expect(deleteCalls.at(-1)).toEqual({ confirm_email: EMAIL.toUpperCase(), password: "right-password" });
});

test("แอดมินคนสุดท้ายลบบัญชีไม่ได้", async ({ page }) => {
  await login(page);
  await page.route("**/api/auth/account/deletion-summary", (route) =>
    route.fulfill({ json: { ...SUMMARY, is_last_admin: true } }));
  await page.goto("/profile");
  await page.getByRole("button", { name: "ลบบัญชีของฉัน..." }).click();
  const dialog = page.getByRole("dialog", { name: "ลบบัญชีถาวร" });
  await expect(dialog).toContainText("คุณเป็นผู้ดูแลระบบคนสุดท้าย");
  await expect(dialog.getByRole("button", { name: "ลบบัญชีถาวร" })).toHaveCount(0);
  await dialog.getByRole("button", { name: "ยกเลิก" }).click();
  await expect(dialog).toHaveCount(0);
});
