// ส่งเอกสารให้ลงนามตามลำดับ: ผู้ส่ง → ผู้ลงนามคนที่ 1 (อิเล็กทรอนิกส์) → คนที่ 2 (ดิจิทัล) → ไฟล์กลับไปหาผู้ส่ง
// ต้องมีผู้ใช้ทดสอบ e2e-signer1@example.com และ e2e-signer2@example.com (รหัสผ่านเดียวกับ E2E_PASSWORD)
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { PASSWORD, login, uploadSample } from "./helpers.js";

const SIGNER1 = process.env.E2E_SIGNER1 || "e2e-signer1@example.com";
const SIGNER2 = process.env.E2E_SIGNER2 || "e2e-signer2@example.com";
const P12 = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "signer2.p12");

test("ส่งลงนาม 2 คนตามลำดับ แล้วไฟล์ที่ลงนามครบกลับไปหาผู้ส่ง", async ({ browser }) => {
  test.setTimeout(150_000);

  // ---------- ผู้ส่ง ----------
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
  const title = `สัญญาทดสอบ ${Date.now()}`;
  await owner.getByLabel("ชื่อเอกสาร").fill(title);
  // ครบกำหนดอีก 3 วัน (ค่า datetime-local เป็นเวลาท้องถิ่นของเบราว์เซอร์)
  const due = new Date(Date.now() + 3 * 24 * 3600 * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  const dueLocal = `${due.getFullYear()}-${pad(due.getMonth() + 1)}-${pad(due.getDate())}T${pad(due.getHours())}:${pad(due.getMinutes())}`;
  await owner.getByLabel("ครบกำหนดลงนาม").fill(dueLocal);

  const rows = owner.getByTestId("signer-row");
  await rows.nth(0).getByPlaceholder("อีเมลผู้ลงนาม").fill(SIGNER1);
  await rows.nth(0).getByPlaceholder("อีเมลผู้ลงนาม").press("Enter");
  await expect(rows.nth(0).getByText("✓")).toBeVisible();
  await rows.nth(0).locator("select").selectOption("electronic");
  await rows.nth(0).getByRole("button", { name: "วางกล่องลายเซ็น" }).click();
  await pageEl.hover({ position: { x: 150, y: 500 } });
  await expect(pageEl.getByTestId("signature-ghost")).toBeVisible(); // กล่องลอยตามเมาส์ก่อนคลิกวาง
  await pageEl.click({ position: { x: 150, y: 500 } });
  await expect(pageEl.getByTestId("signature-ghost")).toHaveCount(0);

  await owner.getByRole("button", { name: "+ เพิ่มผู้ลงนาม" }).click();
  await rows.nth(1).getByPlaceholder("อีเมลผู้ลงนาม").fill(SIGNER2);
  await rows.nth(1).getByPlaceholder("อีเมลผู้ลงนาม").press("Enter");
  await expect(rows.nth(1).getByText("✓")).toBeVisible();
  await rows.nth(1).locator("select").selectOption("digital");
  await rows.nth(1).getByRole("button", { name: "วางกล่องลายเซ็น" }).click();
  await pageEl.click({ position: { x: 400, y: 500 } });
  await expect(pageEl.getByTestId("signature-box")).toHaveCount(2);

  await owner.getByRole("button", { name: /ส่งให้ลงนาม \(2 คน\)/ }).click();
  await owner.waitForURL(/\/signing\/\d+$/);
  const requestUrl = new URL(owner.url()).pathname;
  await expect(owner.getByText("ครบกำหนด:")).toBeVisible();

  // ผู้ส่งกดส่งเตือนได้ แต่กดซ้ำทันทีไม่ได้ (เว้นช่วง)
  await owner.getByRole("button", { name: "ส่งเตือนผู้ลงนาม" }).click();
  await expect(owner.getByRole("status")).toContainText("ส่งเตือน");
  await owner.getByRole("button", { name: "ส่งเตือนผู้ลงนาม" }).click();
  await expect(owner.getByRole("alert")).toContainText("ส่งเตือนอีกครั้งได้ในอีก");

  // ---------- ผู้ลงนามคนที่ 2 ยังเซ็นไม่ได้ ----------
  const s2Ctx = await browser.newContext();
  const s2 = await s2Ctx.newPage();
  await login(s2, SIGNER2, PASSWORD);
  await s2.goto(requestUrl);
  await expect(s2.getByTestId("signing-steps")).toContainText("ถึงคิวลงนาม");
  await expect(s2.getByRole("button", { name: "ลงนามดิจิทัล (ใบรับรอง)" })).toHaveCount(0);

  // ---------- ผู้ลงนามคนที่ 1: เห็นในกล่อง "รอฉันลงนาม" + แจ้งเตือน → ลงนามอิเล็กทรอนิกส์ ----------
  const s1Ctx = await browser.newContext();
  const s1 = await s1Ctx.newPage();
  await login(s1, SIGNER1, PASSWORD);
  await expect(s1.getByTestId("notification-badge")).toBeVisible();
  await s1.goto("/signing?box=to_sign");
  await s1.getByRole("link", { name: title }).click();
  await s1.getByRole("button", { name: "ลงนามอิเล็กทรอนิกส์" }).click();
  await s1.getByPlaceholder("พิมพ์ข้อความที่จะใช้เป็นลายเซ็น...").fill("Signer One");
  await s1.getByRole("button", { name: "ตกลง" }).click();
  await expect(s1.getByRole("status")).toContainText("ลงนามเรียบร้อยแล้ว");

  // ---------- ผู้ลงนามคนที่ 2: ลงนามดิจิทัลด้วยไฟล์ p12 ----------
  await s2.reload();
  await s2.getByRole("button", { name: "ลงนามดิจิทัล (ใบรับรอง)" }).click();
  await s2.locator("input[type=file][accept*='.p12']").setInputFiles(P12);
  await s2.getByPlaceholder("รหัสผ่านสำหรับเปิดคีย์ (Passphrase) *").fill("p12-pass");
  await s2.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(s2.getByRole("status")).toContainText("ลงนามดิจิทัลเรียบร้อยแล้ว");

  // ---------- ผู้ส่ง: สถานะครบ + ลายเซ็นถูกต้อง + ไฟล์อยู่ในเอกสารของฉัน ----------
  await owner.reload();
  await expect(owner.getByText("ลงนามครบแล้ว").first()).toBeVisible();
  await owner.getByRole("button", { name: "ตรวจสอบลายเซ็นในเอกสาร" }).click();
  await expect(owner.getByTestId("verify-report")).toContainText("ถูกต้อง");
  await expect(owner.getByTestId("verify-report")).not.toContainText("ไม่ถูกต้อง");
  await owner.goto("/dashboard");
  await expect(owner.getByText(`${title} (ลงนามครบแล้ว).pdf`).first()).toBeVisible();

  await Promise.all([ownerCtx.close(), s1Ctx.close(), s2Ctx.close()]);
});
