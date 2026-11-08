// เอกสารอัตโนมัติ + QR/บาร์โค้ด: ใช้ไฟล์ตัวอย่างชุดที่ 3 (บัตรพนักงาน) จากคู่มือ → .zip ได้ Word 4 ไฟล์
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import { login } from "./helpers.js";

test("สร้างบัตรพนักงานพร้อม QR/บาร์โค้ดจากไฟล์ตัวอย่าง", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  const get = async (name) => Buffer.from(await (await page.request.get(`/api/autogen/samples/${name}`)).body());
  const tpl = await get("template_qr.docx");
  const data = await get("data_qr.xlsx");

  await page.getByRole("button", { name: /สร้างเอกสารอัตโนมัติ/ }).click();
  const modal = page.getByTestId("autogen-modal");
  await modal.getByText("ดาวน์โหลดไฟล์ตัวอย่าง").click();
  await expect(modal.getByRole("link", { name: "Template QR/บาร์โค้ด" })).toBeVisible();
  await modal.getByTestId("autogen-template").setInputFiles({ name: "template_qr.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: tpl });
  await modal.getByTestId("autogen-data").setInputFiles({ name: "data_qr.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: data });
  await expect(modal.getByTestId("autogen-preview")).toContainText("ตัวแปรทุกตัวใน Template มีในไฟล์ข้อมูล");
  await modal.getByTestId("autogen-format").selectOption("docx");

  const [download] = await Promise.all([page.waitForEvent("download"), modal.getByTestId("autogen-submit").click()]);
  await expect(modal.getByTestId("autogen-result")).toContainText("สร้าง 4 เอกสาร");
  const zip = fs.readFileSync(await download.path());
  expect(zip.subarray(0, 2).toString()).toBe("PK");
  for (const n of ["สมชาย ใจดี.docx", "John Smith.docx"]) expect(zip.includes(Buffer.from(n))).toBeTruthy();
});
