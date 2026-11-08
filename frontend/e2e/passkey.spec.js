// Passkey — เพิ่มในหน้าความปลอดภัย แล้วเข้าสู่ระบบด้วย passkey (ใช้ Virtual Authenticator ของ Chromium แทน Face ID/Touch ID)
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

async function addVirtualAuthenticator(page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  const { authenticatorId } = await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return { cdp, authenticatorId };
}

// ลบ passkey ที่ค้างจากการรันครั้งก่อน (authenticator จำลองเป็นของใหม่ทุกครั้ง) แล้วเพิ่มใหม่ 1 อัน
async function freshPasskey(page, name) {
  await page.goto("/security");
  const section = page.getByTestId("passkey-section");
  await expect(section.getByText(/กำลังโหลด/)).toHaveCount(0);
  while (await section.getByRole("button", { name: "ลบ", exact: true }).count()) {
    await section.getByRole("button", { name: "ลบ", exact: true }).first().click();
    await page.getByRole("dialog", { name: "ลบ passkey" }).getByRole("button", { name: "ลบ passkey" }).click();
    await expect(page.getByRole("dialog", { name: "ลบ passkey" })).toHaveCount(0);
    await expect(section.getByText(/ลบ passkey ".*" แล้ว/)).toBeVisible(); // รอรายการโหลดใหม่
  }
  await section.getByRole("button", { name: "+ เพิ่ม passkey" }).click();
  await section.getByLabel("ตั้งชื่อให้จำได้ว่าเป็นอุปกรณ์ไหน").fill(name);
  await section.getByRole("button", { name: "สร้าง passkey" }).click();
  await expect(section).toContainText(`เพิ่ม passkey "${name}" แล้ว`);
  return section;
}

test("เพิ่ม passkey ในหน้าความปลอดภัย → ออกจากระบบ → กดปุ่มเข้าสู่ระบบด้วย passkey → เปลี่ยนชื่อ/ลบ", async ({ page }) => {
  // authenticator จำลองตอบคำขอแบบ autofill ให้เองทันที — ปิด autofill ในเทสนี้เพื่อทดสอบเส้นทางปุ่ม
  await page.addInitScript(() => {
    if (window.PublicKeyCredential) window.PublicKeyCredential.isConditionalMediationAvailable = async () => false;
  });
  const { cdp, authenticatorId } = await addVirtualAuthenticator(page);
  await login(page);
  const section = await freshPasskey(page, "เครื่องทดสอบ E2E");
  await expect(section.getByTestId("passkey-list")).toContainText("ยังไม่เคยใช้");
  const { credentials } = await cdp.send("WebAuthn.getCredentials", { authenticatorId });
  expect(credentials).toHaveLength(1);
  expect(credentials[0].isResidentCredential).toBe(true);

  // ออกจากระบบ แล้วเข้าใหม่ด้วย passkey (ไม่กรอกอีเมล/รหัสผ่าน)
  await page.evaluate(() => localStorage.removeItem("token"));
  await page.goto("/login");
  await page.getByRole("button", { name: "เข้าสู่ระบบด้วย Passkey" }).click();
  await page.waitForURL("**/dashboard");

  await page.goto("/security");
  const list = page.getByTestId("passkey-list");
  await expect(list).toContainText("ใช้ล่าสุด");

  await list.getByRole("button", { name: "เปลี่ยนชื่อ" }).click();
  await list.getByLabel("ชื่อ passkey").fill("MacBook ที่ทำงาน");
  await list.getByRole("button", { name: "บันทึก" }).click();
  await expect(list).toContainText("MacBook ที่ทำงาน");

  await list.getByRole("button", { name: "ลบ", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "ลบ passkey" });
  await expect(dialog).toContainText("passkey อันสุดท้าย");
  await dialog.getByRole("button", { name: "ลบ passkey" }).click();
  await expect(page.getByTestId("passkey-section")).toContainText("ยังไม่มี passkey");

  // passkey ยังอยู่ในอุปกรณ์ แต่ระบบลบแล้ว → เข้าสู่ระบบไม่ได้ และบอกเหตุผล
  await page.evaluate(() => localStorage.removeItem("token"));
  await page.goto("/login");
  await page.getByRole("button", { name: "เข้าสู่ระบบด้วย Passkey" }).click();
  await expect(page.getByText(/ไม่พบ passkey นี้ในระบบ/)).toBeVisible();
});

test("ช่องอีเมลในหน้าเข้าสู่ระบบแนะนำ passkey (autofill) แล้วเข้าสู่ระบบได้", async ({ page }) => {
  await addVirtualAuthenticator(page);
  await login(page);
  await freshPasskey(page, "autofill");
  await page.evaluate(() => localStorage.removeItem("token"));
  await page.goto("/login");
  await expect(page.locator("input[type=email]")).toHaveAttribute("autocomplete", "username webauthn");
  // autofill เริ่มเมื่อแตะช่องอีเมล — เบราว์เซอร์จริงแสดงรายการ passkey ใต้ช่อง ส่วน authenticator จำลองเลือกให้อัตโนมัติ
  await page.locator("input[type=email]").click();
  await page.waitForURL("**/dashboard");
});

test("แตะช่องอีเมล (autofill รออยู่) แล้วกดปุ่ม Passkey — ยกเลิก autofill แล้วเข้าสู่ระบบด้วยปุ่มได้", async ({ page }) => {
  let { cdp, authenticatorId } = await addVirtualAuthenticator(page);
  await login(page);
  await freshPasskey(page, "ปุ่มหลัง autofill");
  const { credentials } = await cdp.send("WebAuthn.getCredentials", { authenticatorId });
  await page.evaluate(() => localStorage.removeItem("token"));
  // ถอด authenticator ออกชั่วคราว → คำขอ autofill ค้างรอเหมือนผู้ใช้จริงที่ยังไม่เลือก passkey
  await cdp.send("WebAuthn.removeVirtualAuthenticator", { authenticatorId });
  await page.goto("/login");
  await page.locator("input[type=email]").click();
  await page.waitForTimeout(800);
  await expect(page).toHaveURL(/\/login/);
  ({ cdp, authenticatorId } = await addVirtualAuthenticator(page));
  await cdp.send("WebAuthn.addCredential", { authenticatorId, credential: credentials[0] });
  await page.getByRole("button", { name: "เข้าสู่ระบบด้วย Passkey" }).click();
  await page.waitForURL("**/dashboard");
});

test("แตะช่องอีเมลแล้วกดปุ่ม Passkey ทันที (ระหว่างที่คำขอ autofill ยังโหลด) — คำขอของปุ่มไม่ถูกยกเลิก", async ({ page }) => {
  // Safari: ถ้าคำขอ autofill เริ่มหลังจากกดปุ่มไปแล้ว คำขอของปุ่มถูกยกเลิกและปุ่มค้าง "รอยืนยันที่อุปกรณ์..." ตลอดไป
  let { cdp, authenticatorId } = await addVirtualAuthenticator(page);
  await login(page);
  await freshPasskey(page, "ปุ่มระหว่างโหลด");
  const { credentials } = await cdp.send("WebAuthn.getCredentials", { authenticatorId });
  await page.evaluate(() => localStorage.removeItem("token"));
  await cdp.send("WebAuthn.removeVirtualAuthenticator", { authenticatorId });   // คำขอของปุ่มรอผู้ใช้อยู่
  let slow = false;
  await page.route("**/auth/passkeys/login/options", async (route) => {
    if (slow) await new Promise((r) => setTimeout(r, 1500));          // คำขอ options ของ autofill มาช้า
    await route.continue();
  });
  await page.goto("/login");
  await page.waitForLoadState("networkidle");                          // options ของปุ่ม (ขอไว้ก่อน) มาแล้ว
  slow = true;
  await page.locator("input[type=email]").click();                     // เริ่มขอ options ของ autofill (ช้า)
  const button = page.getByRole("button", { name: /เข้าสู่ระบบด้วย Passkey|รอยืนยันที่อุปกรณ์/ });
  await button.click();
  await page.waitForTimeout(2500);                                     // options ของ autofill มาถึงแล้ว
  await expect(button).toHaveText(/รอยืนยันที่อุปกรณ์/);                // คำขอของปุ่มยังรออยู่ (ไม่ถูกยกเลิก)
  // กลับมาใช้งานได้: ยกเลิกเอง → ต่ออุปกรณ์ → กดใหม่ → เข้าสู่ระบบ
  await page.getByTestId("passkey-cancel").click();
  ({ cdp, authenticatorId } = await addVirtualAuthenticator(page));
  await cdp.send("WebAuthn.addCredential", { authenticatorId, credential: credentials[0] });
  await page.getByRole("button", { name: "เข้าสู่ระบบด้วย Passkey" }).click();
  await page.waitForURL("**/dashboard");
});

test("ปุ่ม Passkey ที่รออยู่ กด \"ยกเลิกแล้วกดใหม่\" ได้", async ({ page }) => {
  const { cdp, authenticatorId } = await addVirtualAuthenticator(page);
  await cdp.send("WebAuthn.removeVirtualAuthenticator", { authenticatorId });   // ไม่มีอุปกรณ์ตอบ → รอค้าง
  await page.goto("/login");
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "เข้าสู่ระบบด้วย Passkey" }).click();
  await expect(page.getByTestId("passkey-cancel")).toBeVisible();
  await page.getByTestId("passkey-cancel").click();
  await expect(page.getByRole("button", { name: "เข้าสู่ระบบด้วย Passkey" })).toBeEnabled();
});

test("เบราว์เซอร์โฟกัสช่องอีเมลให้เองตอนเปิดหน้า (Safari บน Mac) — ไม่เริ่ม autofill ปุ่ม Passkey ใช้ได้ทันที", async ({ page }) => {
  const { cdp, authenticatorId } = await addVirtualAuthenticator(page);
  await login(page);
  await freshPasskey(page, "โฟกัสเอง");
  await page.evaluate(() => localStorage.removeItem("token"));
  let optionCalls = 0;
  await page.route("**/auth/passkeys/login/options", async (route) => { optionCalls += 1; await route.continue(); });
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  const before = optionCalls;
  await page.locator("input[type=email]").focus();                      // โฟกัสโดยไม่มีการแตะ/พิมพ์
  await page.waitForTimeout(500);
  expect(optionCalls).toBe(before);                                     // ไม่ได้เริ่มคำขอ autofill
  await page.getByRole("button", { name: "เข้าสู่ระบบด้วย Passkey" }).click();
  await page.waitForURL("**/dashboard");
  expect(cdp && authenticatorId).toBeTruthy();
});
