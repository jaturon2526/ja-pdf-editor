import { expect, test } from "@playwright/test";
import { csrfHeaders, login, uploadSample } from "./helpers.js";

// รูปลายเซ็นจำลอง (PNG สีน้ำเงินเข้ม 16×16 พิกเซล = 256 ink pixels > MIN_INK_PIXELS 30 — ใช้สำหรับทดสอบเท่านั้น)
const SYNTHETIC_SIG_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAGUlEQVR4nGOQCrv9nxLMMGrAqAGjBgwXAwD/rEofHqNm6QAAAABJRU5ErkJggg==", // pragma: allowlist secret
  "base64",
);

async function cleanupSavedSignaturesAndPasskeys(page) {
  const headers = await csrfHeaders(page);
  const sigRes = await page.request.get("/api/signature/saved");
  if (sigRes.ok()) {
    const sigs = await sigRes.json();
    for (const s of Array.isArray(sigs) ? sigs : []) {
      await page.request.delete(`/api/signature/saved/${s.id}`, { headers });
    }
  }
  const pkRes = await page.request.get("/api/auth/passkeys");
  if (pkRes.ok()) {
    const data = await pkRes.json();
    for (const pk of data.passkeys || []) {
      await page.request.delete(`/api/auth/passkeys/${pk.id}`, { headers });
    }
  }
}

test.afterEach(async ({ page }) => {
  await cleanupSavedSignaturesAndPasskeys(page);
});

test("บันทึกรูปลายเซ็นด้วย Passkey → ปลดล็อกใช้งานในหน้าเซ็นเอกสาร → ลบ", async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
      hasPrf: true,
    },
  });

  await login(page);
  await cleanupSavedSignaturesAndPasskeys(page);

  // 1) เพิ่ม Passkey แล้วอัปโหลดรูปลายเซ็น + เข้ารหัสล็อกด้วย Passkey
  await page.goto("/security");
  const pkSection = page.getByTestId("passkey-section");
  await pkSection.getByRole("button", { name: "+ เพิ่ม passkey" }).click();
  await pkSection.getByLabel("ตั้งชื่อให้จำได้ว่าเป็นอุปกรณ์ไหน").fill("อุปกรณ์ลายเซ็น E2E");
  await pkSection.getByRole("button", { name: "สร้าง passkey" }).click();
  await expect(pkSection).toContainText('เพิ่ม passkey "อุปกรณ์ลายเซ็น E2E" แล้ว');

  const sigSection = page.getByTestId("saved-sig-section");
  await sigSection.getByLabel("ชื่อรูปลายเซ็น").fill("ลายเซ็นทางการ E2E");
  await page.getByTestId("saved-sig-file-input").setInputFiles({
    name: "signature.png",
    mimeType: "image/png",
    buffer: SYNTHETIC_SIG_PNG,
  });
  await expect(sigSection.getByAltText("ตัวอย่างรูปลายเซ็น")).toBeVisible();
  await sigSection.getByRole("button", { name: "บันทึกด้วย Passkey" }).click();

  await expect(sigSection.getByRole("status")).toContainText("ลายเซ็นทางการ E2E");
  const list = page.getByTestId("saved-sig-list");
  await expect(list).toContainText("ลายเซ็นทางการ E2E");
  await expect(list).toContainText("อุปกรณ์ลายเซ็น E2E");

  // 2) เปิดเอกสารในหน้าแก้ไข → ลายเซ็นอิเล็กทรอนิกส์ → แท็บ "ที่บันทึกไว้" → ปลดล็อกด้วย Passkey → เซ็นสำเร็จ
  await page.goto("/dashboard");
  await uploadSample(page);
  await page.getByRole("button", { name: "ลายเซ็นดิจิทัล", exact: true }).click();
  await page.getByText("ลายเซ็นอิเล็กทรอนิกส์...").click();

  await page.getByRole("tab", { name: "ที่บันทึกไว้" }).click();
  await expect(page.getByRole("radio", { name: /ลายเซ็นทางการ E2E/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "ปลดล็อกด้วย Passkey" }).click();
  await expect(page.getByAltText("พรีวิวลายเซ็นที่ปลดล็อกแล้ว")).toBeVisible();

  await page.getByRole("button", { name: "ตกลง", exact: true }).click();
  await page.getByRole("button", { name: "ตกลง", exact: true }).click(); // ยืนยันตำแหน่งวางลายเซ็น
  await expect(page.getByText(/ลงลายเซ็นอิเล็กทรอนิกส์สำเร็จ/)).toBeVisible({ timeout: 30_000 });

  // 3) กลับหน้าความปลอดภัย → ลบรูปลายเซ็นที่บันทึกไว้
  await page.goto("/security");
  await page.getByTestId("saved-sig-list").getByRole("button", { name: "ลบ", exact: true }).click();
  await expect(page.getByTestId("saved-sig-list")).toHaveCount(0);
});
