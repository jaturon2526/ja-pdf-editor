// ผู้ส่งบังคับให้ผู้ลงนามยืนยันตัวตนด้วย passkey ก่อนลงนาม (Chromium Virtual Authenticator แทน Face ID/Touch ID)
import { expect, test } from "@playwright/test";
import { PASSWORD, login, uploadSample } from "./helpers.js";

const SIGNER1 = process.env.E2E_SIGNER1 || "e2e-signer1@example.com";

async function api(page, method, url, body) {
  return page.evaluate(async ([m, u, b]) => {
    const res = await fetch(`/api${u}`, {
      method: m,
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json" },
      body: b ? JSON.stringify(b) : undefined,
    });
    return { status: res.status, body: await res.json().catch(() => null) };
  }, [method, url, body]);
}

test("ผู้ส่งบังคับ passkey → ผู้ลงนามที่ยังไม่มีถูกพาไปเพิ่ม → สแกน passkey แล้วลงนาม → บันทึกในคำขอ", async ({ browser }) => {
  test.setTimeout(120_000);

  // ---------- ผู้ส่ง: สร้างคำขอผ่าน API (หน้าสร้างคำขอทดสอบแยกใน signing.spec.js) ----------
  const ownerCtx = await browser.newContext();
  const owner = await ownerCtx.newPage();
  await login(owner);
  const sessionId = await uploadSample(owner);
  const files = await api(owner, "GET", "/pdf/files");
  const fileId = files.body.files.find((f) => f.session_id === sessionId).id;
  const title = `ต้องยืนยันด้วย passkey ${Date.now()}`;
  const created = await api(owner, "POST", "/signing/requests", {
    file_id: fileId, title,
    steps: [{ email: SIGNER1, sign_type: "electronic", require_passkey: true, page: 0, x0: 60, y0: 600, x1: 220, y1: 670 }],
  });
  expect(created.status).toBe(200);
  const requestUrl = `/signing/${created.body.id}`;

  // ---------- ผู้ลงนาม ----------
  const ctx = await browser.newContext();
  const s1 = await ctx.newPage();
  const cdp = await ctx.newCDPSession(s1);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true },
  });
  await s1.addInitScript(() => {
    if (window.PublicKeyCredential) window.PublicKeyCredential.isConditionalMediationAvailable = async () => false;
  });
  await login(s1, SIGNER1, PASSWORD);
  // ล้าง passkey ที่ค้างจากการรันครั้งก่อน (authenticator จำลองเป็นของใหม่ทุกครั้ง)
  for (const pk of (await api(s1, "GET", "/auth/passkeys")).body.passkeys) {
    await api(s1, "DELETE", `/auth/passkeys/${pk.id}`);
  }

  await s1.goto(requestUrl);
  await expect(s1.getByTestId("passkey-needed")).toBeVisible();
  await expect(s1.getByRole("button", { name: "ลงนามอิเล็กทรอนิกส์" })).toBeDisabled();

  await s1.getByRole("link", { name: "เพิ่ม passkey ที่หน้าความปลอดภัย" }).click();
  await s1.getByRole("button", { name: "+ เพิ่ม passkey" }).click();
  await s1.getByLabel("ตั้งชื่อให้จำได้ว่าเป็นอุปกรณ์ไหน").fill("มือถือผู้ลงนาม");
  await s1.getByRole("button", { name: "สร้าง passkey" }).click();
  await expect(s1.getByTestId("passkey-section")).toContainText('เพิ่ม passkey "มือถือผู้ลงนาม" แล้ว');

  await s1.goto(requestUrl);
  await expect(s1.getByTestId("passkey-required")).toBeVisible();
  const signBtn = s1.getByRole("button", { name: "ลงนามอิเล็กทรอนิกส์" });
  await expect(signBtn).toBeEnabled();
  await s1.waitForTimeout(500); // ให้ขอ challenge ล่วงหน้าเสร็จ
  await signBtn.click();
  await s1.getByPlaceholder("พิมพ์ข้อความที่จะใช้เป็นลายเซ็น...").fill("Signer One");
  await s1.getByRole("button", { name: "ตกลง" }).click();
  await expect(s1.getByRole("status")).toContainText("ลงนามเรียบร้อยแล้ว");

  // ---------- ผู้ส่งเห็นว่ายืนยันด้วย passkey ----------
  await owner.goto(requestUrl);
  await expect(owner.getByTestId("signing-steps")).toContainText("ยืนยันตัวตนด้วย Passkey (มือถือผู้ลงนาม)");

  // ลบ passkey ของผู้ลงนามทดสอบ — เทสลงนามอื่นใช้บัญชีเดียวกันโดยไม่มี authenticator
  for (const pk of (await api(s1, "GET", "/auth/passkeys")).body.passkeys) {
    await api(s1, "DELETE", `/auth/passkeys/${pk.id}`);
  }
  await Promise.all([ownerCtx.close(), ctx.close()]);
});
