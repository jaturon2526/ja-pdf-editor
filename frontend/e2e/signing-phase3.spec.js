// เฟส 3: ลงนามพร้อมกัน (ขั้นเดียวกัน) + เชิญคนที่ยังไม่มีบัญชี + หนังสือรับรองการลงนาม
import { expect, test } from "@playwright/test";
import { PASSWORD, login, uploadSample } from "./helpers.js";

const SIGNER1 = process.env.E2E_SIGNER1 || "e2e-signer1@example.com";
const SIGNER2 = process.env.E2E_SIGNER2 || "e2e-signer2@example.com";

async function addSigner(page, pageEl, index, email, { parallel = false, x = 150 } = {}) {
  const rows = page.getByTestId("signer-row");
  if (index > 0) await page.getByRole("button", { name: "+ เพิ่มผู้ลงนาม" }).click();
  const row = rows.nth(index);
  await row.getByPlaceholder("อีเมลผู้ลงนาม").fill(email);
  await row.getByPlaceholder("อีเมลผู้ลงนาม").press("Enter");
  await row.locator("select").selectOption("electronic");
  if (parallel) await row.getByLabel(/ลงนามพร้อมกับคนก่อนหน้า/).check();
  await row.getByRole("button", { name: "วางกล่องลายเซ็น" }).click();
  await pageEl.click({ position: { x, y: 520 } });
  return row;
}

async function signElectronic(page, name) {
  await page.getByRole("button", { name: "ลงนามอิเล็กทรอนิกส์" }).click();
  await page.getByPlaceholder("พิมพ์ข้อความที่จะใช้เป็นลายเซ็น...").fill(name);
  await page.getByRole("button", { name: "ตกลง" }).click();
  await expect(page.getByRole("status")).toContainText("ลงนามเรียบร้อยแล้ว");
}

test("ลงนามพร้อมกัน 2 คน แล้วรอผู้ถูกเชิญ + ดาวน์โหลดหนังสือรับรอง", async ({ browser }) => {
  test.setTimeout(150_000);
  const invitee = `invitee-${Date.now()}@example.org`;

  const ownerCtx = await browser.newContext();
  const owner = await ownerCtx.newPage();
  await login(owner);
  const sessionId = await uploadSample(owner);
  const fileId = await owner.evaluate(async (sid) => {
    const res = await fetch("/api/pdf/files", { headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
    return (await res.json()).files.find((f) => f.session_id === sid).id;
  }, sessionId);

  await owner.goto(`/signing/new?file=${fileId}`);
  const pageEl = owner.getByTestId("signing-page");
  await expect(pageEl.locator("img")).toBeVisible();
  const title = `ขั้นพร้อมกัน ${Date.now()}`;
  await owner.getByLabel("ชื่อเอกสาร").fill(title);

  const r1 = await addSigner(owner, pageEl, 0, SIGNER1, { x: 120 });
  await expect(r1.getByText("✓")).toBeVisible();
  const r2 = await addSigner(owner, pageEl, 1, SIGNER2, { parallel: true, x: 300 });
  await expect(r2.getByText("✓")).toBeVisible();
  const r3 = await addSigner(owner, pageEl, 2, invitee, { x: 480 });
  await expect(r3.getByTestId("invite-note")).toBeVisible();

  await owner.getByRole("button", { name: /ส่งให้ลงนาม \(3 คน\)/ }).click();
  await owner.waitForURL(/\/signing\/\d+$/);
  const requestUrl = new URL(owner.url()).pathname;
  await expect(owner.getByTestId("signing-steps")).toContainText("ส่งคำเชิญแล้ว");

  // คนที่ 2 (ขั้นเดียวกับคนที่ 1) ลงนามได้ทันทีโดยไม่ต้องรอคนที่ 1
  const s2Ctx = await browser.newContext();
  const s2 = await s2Ctx.newPage();
  await login(s2, SIGNER2, PASSWORD);
  await s2.goto(requestUrl);
  await signElectronic(s2, "Signer Two");

  const s1Ctx = await browser.newContext();
  const s1 = await s1Ctx.newPage();
  await login(s1, SIGNER1, PASSWORD);
  await s1.goto(requestUrl);
  await signElectronic(s1, "Signer One");

  // ขั้นที่ 2 รอผู้ถูกเชิญ (ยังไม่มีบัญชี)
  await owner.reload();
  await expect(owner.getByTestId("signing-steps")).toContainText("ถึงคิวลงนาม");
  await expect(owner.getByText("กำลังลงนาม").first()).toBeVisible();

  const download = owner.waitForEvent("download");
  await owner.getByRole("button", { name: "ดาวน์โหลดหนังสือรับรองการลงนาม" }).click();
  const file = await (await download).path();
  const { readFileSync } = await import("node:fs");
  expect(readFileSync(file).subarray(0, 5).toString()).toBe("%PDF-");

  await Promise.all([ownerCtx.close(), s1Ctx.close(), s2Ctx.close()]);
});
