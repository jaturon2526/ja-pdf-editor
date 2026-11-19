import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { csrfHeaders, login, uploadSample } from "./helpers.js";

const P12 = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "signer2.p12");
const PW = "p12-pass";

// ลบใบรับรองที่บันทึกไว้ของผู้ใช้ทดสอบ — spec อื่น (sign-editor) คาดว่าหน้าต่างเซ็นเปิดมาที่ "เลือกไฟล์"
async function removeSavedCertificates(page) {
  const list = await (await page.request.get("/api/signature/certificates")).json();
  for (const c of Array.isArray(list) ? list : []) {
    await page.request.post(`/api/signature/certificates/${c.id}/delete`, {
      headers: { ...(await csrfHeaders(page)), "Content-Type": "application/json" },
      data: { password: PW },
    });
  }
}

test.afterEach(async ({ page }) => {
  await removeSavedCertificates(page);
});

test("บันทึกใบรับรองในหน้าความปลอดภัย → ใช้เซ็นโดยไม่ต้องเลือกไฟล์ → ลบ (ยืนยันรหัสทุกขั้น)", async ({ page }) => {
  await login(page);
  await removeSavedCertificates(page);

  // 1) บันทึก: รหัสผิดไม่บันทึก · รหัสถูกบันทึกพร้อมข้อมูลใบรับรอง
  await page.goto("/security");
  const section = page.getByTestId("certificate-section");
  await section.getByRole("button", { name: "+ เพิ่มใบรับรอง" }).click();
  await page.getByTestId("certificate-file").setInputFiles(P12);
  await section.getByLabel(/รหัสผ่านของใบรับรอง/).fill("wrong-pass");
  await section.getByRole("button", { name: "ตรวจและบันทึก" }).click();
  await expect(section.getByRole("alert")).toContainText("รหัสผ่านไม่ถูกต้อง");
  await expect(page.getByTestId("certificate-list")).toHaveCount(0);
  await section.getByLabel(/รหัสผ่านของใบรับรอง/).fill(PW);
  await section.getByRole("button", { name: "ตรวจและบันทึก" }).click();
  await expect(section.getByRole("status")).toContainText("ไม่ได้เก็บรหัสผ่าน");
  const list = page.getByTestId("certificate-list");
  await expect(list).toContainText("E2E Signer Two");
  await expect(list).toContainText("ผู้ออก");
  await expect(list).toContainText("ยังไม่เคยใช้");

  // 2) เซ็นในหน้าแก้ไขด้วยใบที่บันทึกไว้ (ต้องกรอกรหัสอีกครั้ง)
  await page.goto("/dashboard");
  await uploadSample(page);
  await page.getByRole("button", { name: "ลายเซ็นดิจิทัล", exact: true }).click();
  await page.getByText("เซ็นดิจิทัลรับรอง...").click();
  await expect(page.getByRole("radio", { name: "ใบรับรองที่บันทึกไว้" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("saved-certificates").getByRole("radio")).toBeChecked();
  const pw = page.getByPlaceholder("รหัสผ่านสำหรับเปิดคีย์ (Passphrase) *");
  await pw.fill("wrong-pass");
  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(page.getByTestId("cert-error")).toContainText("รหัสผ่าน");
  await pw.fill(PW);
  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(page.getByText(/ใบรับรองของ E2E Signer Two/)).toBeVisible();
  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(page.getByText(/ลงลายเซ็นดิจิทัลสำเร็จ/)).toBeVisible({ timeout: 30_000 });

  // 3) ลบ: รหัสผิดไม่ลบ · รหัสถูกลบ
  await page.goto("/security");
  await expect(list).toContainText("ใช้ล่าสุด");
  await list.getByRole("button", { name: "ลบ" }).click();
  const dialog = page.getByRole("dialog", { name: "ลบใบรับรอง" });
  await dialog.getByLabel("รหัสผ่านของใบรับรอง").fill("wrong-pass");
  await dialog.getByRole("button", { name: "ลบใบรับรอง" }).click();
  await expect(dialog.getByRole("alert")).toContainText("ไม่ถูกต้อง");
  await dialog.getByLabel("รหัสผ่านของใบรับรอง").fill(PW);
  await dialog.getByRole("button", { name: "ลบใบรับรอง" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId("certificate-list")).toHaveCount(0);
  await expect(section.getByText("ยังไม่มีใบรับรองที่บันทึกไว้")).toBeVisible();
});

// passkey ปลดล็อกใบรับรอง (WebAuthn PRF) — authenticator จำลองของ Chromium ที่รองรับ PRF (hasPrf)
test("ผูก passkey กับใบรับรอง → เซ็นโดยสแกน passkey แทนพิมพ์รหัส → ลบด้วย passkey", async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true,
      isUserVerified: true, automaticPresenceSimulation: true, hasPrf: true },
  });
  await login(page);
  await removeSavedCertificates(page);
  // passkey ที่ค้างจากการรันก่อน (authenticator จำลองเป็นของใหม่ทุกครั้ง)
  for (const pk of (await (await page.request.get("/api/auth/passkeys")).json()).passkeys || []) {
    await page.request.delete(`/api/auth/passkeys/${pk.id}`, { headers: await csrfHeaders(page) });
  }

  await page.goto("/security");
  const pkSection = page.getByTestId("passkey-section");
  await pkSection.getByRole("button", { name: "+ เพิ่ม passkey" }).click();
  await pkSection.getByLabel("ตั้งชื่อให้จำได้ว่าเป็นอุปกรณ์ไหน").fill("มือถือ E2E");
  await pkSection.getByRole("button", { name: "สร้าง passkey" }).click();
  await expect(pkSection).toContainText('เพิ่ม passkey "มือถือ E2E" แล้ว');

  const section = page.getByTestId("certificate-section");
  await section.getByRole("button", { name: "+ เพิ่มใบรับรอง" }).click();
  await page.getByTestId("certificate-file").setInputFiles(P12);
  await section.getByLabel(/รหัสผ่านของใบรับรอง/).fill(PW);
  await section.getByRole("button", { name: "ตรวจและบันทึก" }).click();
  await expect(section.getByRole("status")).toContainText("ไม่ได้เก็บรหัสผ่าน");

  // ผูก: รหัสผิดไม่ผูก · รหัสถูก + สแกน passkey → ผูกแล้ว
  await section.getByRole("button", { name: "ใช้ passkey แทนรหัส" }).click();
  const bind = page.getByRole("dialog", { name: "ใช้ passkey ปลดล็อกใบรับรอง" });
  await bind.getByLabel(/รหัสผ่านของใบรับรอง/).fill("wrong-pass");
  await bind.getByRole("button", { name: "ยืนยันด้วย passkey" }).click();
  await expect(bind.getByRole("alert")).toContainText("ไม่ถูกต้อง");
  await bind.getByLabel(/รหัสผ่านของใบรับรอง/).fill(PW);
  await bind.getByRole("button", { name: "ยืนยันด้วย passkey" }).click();
  await expect(bind).toHaveCount(0);
  await expect(section.getByRole("status")).toContainText("ผูก passkey");
  await expect(section.getByTestId("certificate-passkeys")).toContainText("มือถือ E2E");

  // เซ็นในหน้าแก้ไข: กด "ปลดล็อกด้วย passkey" แทนการพิมพ์รหัส
  await page.goto("/dashboard");
  await uploadSample(page);
  await page.getByRole("button", { name: "ลายเซ็นดิจิทัล", exact: true }).click();
  await page.getByText("เซ็นดิจิทัลรับรอง...").click();
  await expect(page.getByTestId("saved-certificates")).toContainText("ปลดล็อกด้วย passkey ได้");
  await page.getByRole("button", { name: "ปลดล็อกด้วย passkey" }).click();
  await expect(page.getByRole("button", { name: "ปลดล็อกด้วย passkey แล้ว" })).toBeDisabled();
  await expect(page.getByPlaceholder("รหัสผ่านสำหรับเปิดคีย์ (Passphrase) *")).toHaveValue(PW);
  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(page.getByText(/ใบรับรองของ E2E Signer Two/)).toBeVisible();
  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await expect(page.getByText(/ลงลายเซ็นดิจิทัลสำเร็จ/)).toBeVisible({ timeout: 30_000 });

  // ลบด้วย passkey
  await page.goto("/security");
  await page.getByTestId("certificate-list").getByRole("button", { name: "ลบ", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "ลบใบรับรอง" });
  await dialog.getByRole("button", { name: "ยืนยันด้วย passkey แล้วลบ" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId("certificate-list")).toHaveCount(0);
});
