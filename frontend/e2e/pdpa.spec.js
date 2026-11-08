// PDPA — ตรวจหาและปกปิดข้อมูลส่วนบุคคล (Dashboard เครื่องมือด่วน + แผงใน Editor)
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { login } from "./helpers.js";

const PDPA_PDF = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "pdpa-sample.pdf");

async function uploadPdpaSample(page) {
  await page.goto("/dashboard");
  await page.setInputFiles("input[type=file][accept*='.pdf']", PDPA_PDF);
  await page.waitForURL("**/editor/**");
  await expect(page.locator("img[src^='data:image/']").first()).toBeVisible();
}

test("ปกปิดข้อมูลส่วนบุคคลจากเครื่องมือด่วน → ได้ไฟล์ใหม่ (PDPA)", async ({ page }) => {
  await login(page);
  await uploadPdpaSample(page);
  await page.goto("/dashboard");
  await expect(page.getByTestId("tool-card-pdpa")).toBeVisible();
  await page.getByTestId("tool-card-pdpa").click();

  const chooser = page.getByRole("dialog", { name: "เลือกเอกสารที่จะปกปิดข้อมูลส่วนบุคคล" });
  await chooser.getByText("pdpa-sample.pdf", { exact: true }).first().click();

  const review = page.getByRole("dialog", { name: "ปกปิดข้อมูลส่วนบุคคล (PDPA)" });
  const list = review.getByTestId("pii-list");
  await expect(list).toContainText("3-1005-00123-45-8", { timeout: 30_000 });
  await expect(list).toContainText("089-123-4567");
  await expect(list).toContainText("sommut.t@example.com");
  await expect(list).toContainText("นายสมมติ ทดสอบดี");
  // ความมั่นใจสูง (บัตร โทร อีเมล) ติ๊กไว้ก่อน · ชื่อ/ที่อยู่/บัญชี ให้เลือกเอง
  await expect(review.getByLabel("เลือก 3-1005-00123-45-8")).toBeChecked();
  await expect(review.getByLabel("เลือก นายสมมติ ทดสอบดี")).not.toBeChecked();
  await review.getByLabel("เลือก นายสมมติ ทดสอบดี").check();

  await review.getByRole("button", { name: "ปกปิด 4 รายการ" }).click();
  const done = page.getByRole("dialog", { name: "ปกปิดข้อมูลแล้ว 4 รายการ" });
  await expect(done).toContainText(/pdpa-sample \(PDPA\)( \(\d+\))?\.pdf/, { timeout: 30_000 }); // ชื่อซ้ำจากรอบก่อนได้ (2), (3)
  const download = page.waitForEvent("download");
  await done.getByRole("button", { name: /ดาวน์โหลดรายงาน/ }).click();
  // ชื่อไฟล์ภาษาไทยของ blob ใน headless Chromium บาง container กลายเป็น "download" — ตรวจเนื้อหาแทน
  const csv = fs.readFileSync(await (await download).path(), "utf8");
  expect(csv).toContain("รายงานการปกปิดข้อมูลส่วนบุคคล");
  expect(csv).toContain("เลขประจำตัวประชาชน");
  expect(csv).not.toContain("3-1005-00123-45-8"); // รายงานเก็บเฉพาะค่าที่ปิดบางส่วน
  await done.getByRole("button", { name: "ปิด", exact: true }).click();
  await expect(page.getByText("pdpa-sample (PDPA).pdf").first()).toBeVisible();
});

test("แผงตรวจหาข้อมูลส่วนบุคคลใน Editor: ไฮไลต์ → ปกปิด → สแกนใหม่ไม่พบรายการที่ปิดแล้ว", async ({ page }) => {
  await login(page);
  await uploadPdpaSample(page);

  await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
  await page.getByText("ตรวจหาข้อมูลส่วนบุคคล (PDPA)...").click();

  const panel = page.getByTestId("pii-panel");
  await expect(panel.getByTestId("pii-list")).toContainText("089-123-4567", { timeout: 30_000 });
  await expect(page.getByTestId("pii-highlight").first()).toBeVisible();
  const highlights = await page.getByTestId("pii-highlight").count();
  expect(highlights).toBeGreaterThanOrEqual(6);

  await panel.getByRole("button", { name: "ปกปิด 3 รายการ" }).click();
  await expect(panel).toContainText("ปกปิดแล้ว 3 รายการ", { timeout: 30_000 });
  await expect(page.getByTestId("pii-highlight")).toHaveCount(0);

  await panel.getByRole("button", { name: "สแกนอีกครั้ง" }).click();
  const list = panel.getByTestId("pii-list");
  await expect(list).toContainText("นายสมมติ ทดสอบดี");
  await expect(list).not.toContainText("089-123-4567");
  await expect(list).not.toContainText("3-1005-00123-45-8");
});
