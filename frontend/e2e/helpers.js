import { expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const SAMPLE_PDF = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "sample.pdf");
export const EMAIL = process.env.E2E_EMAIL || "e2e@example.com";
export const PASSWORD = process.env.E2E_PASSWORD || "E2e-Passw0rd!";

// token อยู่ใน HttpOnly cookie (ja_session) — page.request / fetch ในหน้าแนบให้เอง
// คำขอที่แก้ข้อมูลต้องส่ง cookie ja_csrf กลับใน header X-CSRF-Token
export async function csrfHeaders(page) {
  const csrf = (await page.context().cookies()).find((c) => c.name === "ja_csrf");
  return csrf ? { "X-CSRF-Token": csrf.value } : {};
}

// ออกจากระบบแบบลบ cookie ทิ้ง (ไม่เรียก /auth/logout)
export async function forgetLogin(page) {
  await page.context().clearCookies();
}

export async function login(page, email = EMAIL, password = PASSWORD) {
  await page.goto("/login");
  await page.fill("input[type=email]", email);
  await page.fill("input[type=password]", password);
  await page.keyboard.press("Enter");
  await page.waitForURL("**/dashboard");
}

// อัปโหลดไฟล์ตัวอย่างจาก Dashboard แล้วรอจนเข้าหน้า Editor — คืน session id
export async function uploadSample(page) {
  await page.setInputFiles("input[type=file][accept*='.pdf']", SAMPLE_PDF);
  await page.waitForURL("**/editor/**");
  await expect(page.locator("img[src^='data:image/']").first()).toBeVisible();
  return page.url().split("/").pop();
}
