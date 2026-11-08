import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

const P12 = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "signer2.p12");

// เซ็นดิจิทัลในหน้าแก้ไข: รหัสผ่านผิดรู้ทันทีในหน้าต่างใบรับรอง · เซ็นสำเร็จ
test("เซ็นดิจิทัลรับรอง: ตรวจรหัสผ่านก่อนวางตำแหน่ง แล้วเซ็นได้", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.getByRole("button", { name: "ลายเซ็นดิจิทัล", exact: true }).click();
  await page.getByText("เซ็นดิจิทัลรับรอง...").click();
  await page.locator("input[type=file][accept*='.p12']").setInputFiles(P12);
  const pw = page.getByPlaceholder("รหัสผ่านสำหรับเปิดคีย์ (Passphrase) *");
  await pw.fill("wrong-pass");
  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(page.getByTestId("cert-error")).toContainText("รหัสผ่านไม่ถูกต้อง");
  await pw.fill("p12-pass");
  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(page.getByText(/ใบรับรองของ E2E Signer Two/)).toBeVisible();
  await page.getByRole("button", { name: "ตกลง", exact: true }).click(); // ปุ่มตกลงของกรอบตำแหน่งลายเซ็น
  await expect(page.getByText(/ลงลายเซ็นดิจิทัลสำเร็จ/)).toBeVisible({ timeout: 30_000 });
});
