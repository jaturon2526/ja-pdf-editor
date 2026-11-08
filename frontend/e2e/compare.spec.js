// เปรียบเทียบเอกสาร: เลือก 2 ไฟล์จาก Dashboard → หน้าเปรียบเทียบ (เคียงข้าง/ซ้อนทับ/รายการ/รายงาน) และเปิดจาก Editor
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { login } from "./helpers.js";

const FIX = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

async function uploadViaApi(page, file, name) {
  const token = await page.evaluate(() => localStorage.getItem("token"));
  const res = await page.request.post("/api/pdf/upload", {
    headers: { Authorization: `Bearer ${token}` },
    multipart: { file: { name, mimeType: "application/pdf", buffer: fs.readFileSync(path.join(FIX, file)) } },
  });
  expect(res.ok()).toBeTruthy();
  return res.json();
}

test("Dashboard: เลือก 2 ไฟล์ แล้วดูจุดต่าง ข้อความ + ภาพ · ซ้อนทับ · ดาวน์โหลดรายงาน", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  const tag = Date.now();
  await uploadViaApi(page, "compare-a.pdf", `สัญญา-${tag}-v1.pdf`);
  await uploadViaApi(page, "compare-b.pdf", `สัญญา-${tag}-v2.pdf`);
  await page.reload();

  await page.getByTestId("tool-card-compare").click();
  const dialog = page.getByTestId("compare-start");
  await dialog.getByLabel("ไฟล์เดิม (A): เลือกไฟล์").selectOption({ label: `สัญญา-${tag}-v1.pdf` });
  await dialog.getByLabel("ไฟล์ใหม่ (B): เลือกไฟล์").selectOption({ label: `สัญญา-${tag}-v2.pdf` });
  await dialog.getByRole("button", { name: "เปรียบเทียบ", exact: true }).click();

  await expect(page).toHaveURL(/\/compare\//);
  const viewer = page.getByTestId("compare-viewer");
  await expect(viewer).toBeVisible({ timeout: 60_000 });
  const list = page.getByTestId("compare-list");
  await expect(list).toContainText("จุดต่าง 3 จุด");
  await expect(list).toContainText("5,000");
  await expect(list).toContainText("6,500");
  await expect(list).toContainText("โดยโอนเข้าบัญชี");
  await expect(list).toContainText("ภาพต่าง");

  // ภาพหน้าโหลดจาก /api/compare/.../page (blob)
  await expect(viewer.locator("img[src^='blob:']").first()).toBeVisible();

  // กดรายการ → ไฮไลต์จุดนั้นในหน้า
  await list.getByRole("button", { name: /5,000/ }).click();
  await expect(list.locator("[aria-current=true]")).toContainText("6,500");
  await expect(viewer.locator("[data-mark] .animate-pulse, [data-mark].animate-pulse").first()).toBeVisible();
  await page.keyboard.press("j");
  await expect(list.locator("[aria-current=true]")).not.toContainText("5,000");

  // กรองชนิด
  await list.getByRole("button", { name: /ภาพต่าง 1/ }).click();
  await expect(list).toContainText("จุดต่าง 2 จาก 3 จุด");

  // ซ้อนทับ
  await viewer.getByRole("button", { name: "ซ้อนทับ" }).click();
  await expect(viewer.getByRole("button", { name: "ไฮไลต์ต่าง" })).toBeVisible();
  await viewer.getByRole("button", { name: "โปร่งใส" }).click();
  await expect(viewer.getByLabel("ความทึบของไฟล์ใหม่")).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    viewer.getByRole("button", { name: "ดาวน์โหลดรายงาน" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^เปรียบเทียบ .*\.pdf$/);
  const bytes = fs.readFileSync(await download.path());
  expect(bytes.subarray(0, 4).toString()).toBe("%PDF");
});

test("Editor: เทียบเอกสารที่กำลังแก้กับฉบับที่บันทึกไว้", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  const up = await uploadViaApi(page, "compare-a.pdf", `editor-cmp-${Date.now()}.pdf`);
  await page.goto(`/editor/${up.session_id}`);
  await expect(page.locator("img[src^='data:image/']").first()).toBeVisible();

  await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
  await page.getByText("เปรียบเทียบกับ...").click();
  const dialog = page.getByTestId("compare-start");
  await expect(dialog.getByLabel("ไฟล์นี้ — เวอร์ชันก่อนหน้า")).toBeDisabled();
  await expect(dialog.getByLabel("ไฟล์นี้ — ฉบับที่บันทึกไว้")).toBeChecked();
  await expect(dialog.getByLabel("เอกสารที่กำลังแก้ไข")).toBeChecked();
  await dialog.getByRole("button", { name: "เปรียบเทียบ", exact: true }).click();

  await expect(page.getByTestId("compare-viewer")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("status")).toContainText("ไม่พบจุดต่าง");
});
