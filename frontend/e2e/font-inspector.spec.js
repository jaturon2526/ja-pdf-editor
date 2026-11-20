import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

// ตรวจฟอนต์ (v1.38.0): sample.pdf ใช้ Sarabun Regular (ฝังในไฟล์) หัวเรื่อง 24 pt บรรทัดอื่น 14 pt
test("ตรวจฟอนต์: ชี้ข้อความดูฟอนต์/ขนาด, ฟอนต์ทั้งเอกสาร, และฟอนต์ในไฟล์ตอนแก้ข้อความ", async ({ page }) => {
  await login(page);
  await page.goto("/dashboard");
  await uploadSample(page);

  await page.getByRole("button", { name: "ตรวจฟอนต์", exact: true }).click();
  const panel = page.getByTestId("font-inspector-panel");
  await expect(panel).toContainText("ในหน้านี้มี");
  await expect(panel.getByTestId("source-fonts")).toContainText("Sarabun-Regular");
  await expect(panel.getByTestId("source-fonts")).toContainText("14 pt");

  // เลือกหัวเรื่อง → รายละเอียดของข้อความนั้น
  await page.getByRole("button", { name: /ฟอนต์ของ “E2E หน้า 1”/ }).click();
  await expect(panel).toContainText("ข้อความที่เลือก");
  await expect(panel.getByTestId("source-fonts")).toContainText("24 pt");
  await expect(panel.getByTestId("source-fonts")).toContainText("ฝังในไฟล์");

  // ฟอนต์ทั้งเอกสาร
  await panel.getByRole("button", { name: "ฟอนต์ทั้งเอกสาร..." }).click();
  const dialog = page.getByRole("dialog", { name: "ฟอนต์ในเอกสาร" });
  await expect(dialog.getByTestId("document-fonts")).toContainText("Sarabun Regular");
  await expect(dialog.getByTestId("document-fonts")).toContainText("หน้า 1–3");
  await dialog.getByRole("button", { name: "ปิด" }).click();

  // ปิดเครื่องมือ แล้วแก้ข้อความ — แผงคุณสมบัติบอกฟอนต์ในไฟล์
  await panel.getByRole("button", { name: "ปิดเครื่องมือตรวจฟอนต์" }).click();
  await expect(panel).toHaveCount(0);
  await page.getByRole("button", { name: "แทรกข้อความ", exact: true }).click();
  await page.locator(".edit-box-text").filter({ hasText: "" }).first().click();
  await expect(page.getByRole("heading", { name: "ฟอนต์ในไฟล์" })).toBeVisible();
  await expect(page.getByTestId("source-fonts")).toContainText("Sarabun-Regular");
});
