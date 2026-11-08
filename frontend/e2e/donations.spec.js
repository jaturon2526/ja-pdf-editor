// รับบริจาค PromptPay: หน้า /support (QR + สิทธิ์ + แจ้งโอน), /supporters (ชื่อ/ไม่ออกนาม), แผงแอดมิน (อนุมัติ)
// ผู้ใช้ e2e ไม่ใช่แอดมินและระบบปิดรับบริจาคเป็นค่าเริ่มต้น → จำลอง /api/donations/* ในเบราว์เซอร์
// (ตรรกะฝั่ง backend — QR ตรงมาตรฐาน, สิทธิ์, หมดอายุ — ทดสอบใน backend/tests/test_donations.py)
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

const INFO = {
  enabled: true, receiver_name: "ผู้พัฒนาทดสอบ", promptpay_masked: "081-xxx-5678", thank_you: "",
  free_plan: { max_storage_mb: 100, max_sessions: 2 },
  tiers: [
    { min_amount: 49, plan: "pro", days: 30, max_storage_mb: 500, max_sessions: 5 },
    { min_amount: 499, plan: "premium", days: 365, max_storage_mb: 1024, max_sessions: 10 },
  ],
};
const QR_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>';

async function mockPublic(page, info = INFO) {
  const qrUrls = [];
  await page.route("**/api/donations/info", (route) => route.fulfill({ json: info }));
  await page.route("**/api/donations/qr.svg*", (route) => {
    qrUrls.push(route.request().url());
    return route.fulfill({ body: QR_SVG, contentType: "image/svg+xml" });
  });
  return qrUrls;
}

test("หน้า /support: เลือกยอดแล้ว QR เปลี่ยนตาม บอกสิทธิ์ที่จะได้ และแจ้งโอนพร้อมเลือกไม่ออกนาม", async ({ page }) => {
  await login(page);
  const qrUrls = await mockPublic(page);
  let posted = null;
  await page.route("**/api/donations/mine", (route) => route.fulfill({ json: { items: [], plan: "free", expire_date: null } }));
  await page.route("**/api/donations", (route) => {
    posted = route.request().postData() || "";
    return route.fulfill({ json: { id: 1, status: "approved", granted_plan: "pro", granted_days: 30, verify_status: "verified" } });
  });
  await page.goto("/support");
  await expect(page.getByRole("heading", { name: "สนับสนุนผู้พัฒนา" })).toBeVisible();
  await expect(page.getByText("081-xxx-5678")).toBeVisible();
  await expect(page.getByTestId("donation-perk")).toContainText("PRO 1 เดือน");

  await page.getByRole("button", { name: "฿499" }).click();
  await expect(page.getByTestId("donation-perk")).toContainText("PREMIUM 1 ปี");
  await expect(page.getByTestId("donation-qr")).toHaveAttribute("src", /amount=499\.00/);
  await expect.poll(() => qrUrls.some((u) => u.includes("amount=499.00"))).toBe(true);

  await page.getByLabel("ยอดเงินอื่น").fill("20");
  await expect(page.getByTestId("donation-perk")).toHaveCount(0); // ต่ำกว่าระดับแรก = ไม่มีสิทธิ์ แต่ยังโอนได้

  await page.getByLabel("ไม่ประสงค์ออกนาม").check();
  await expect(page.getByLabel("ชื่อที่จะแสดง")).toHaveCount(0);
  await page.getByLabel("ข้อความ").fill("สู้ ๆ ครับ");
  await page.getByRole("button", { name: "แจ้งโอนแล้ว" }).click();
  await expect(page.getByTestId("donation-notice")).toContainText("ตรวจสลิปกับธนาคารแล้ว");
  await expect(page.getByTestId("donation-notice")).toContainText("PRO 1 เดือน");
  expect(posted).toContain('name="amount"\r\n\r\n20');
  expect(posted).toContain('name="anonymous"\r\n\r\ntrue');
  expect(posted).toContain("สู้ ๆ ครับ");
});

test("ระบบปิดรับบริจาค: หน้า /support บอกว่ายังไม่เปิด และไม่มีเมนู ☕", async ({ page }) => {
  await page.route("**/api/donations/info", (route) => route.fulfill({ json: { enabled: false, tiers: [] } }));
  await page.goto("/support");
  await expect(page.getByTestId("donation-disabled")).toBeVisible();
  await page.route("**/api/config/public", (route) => route.fulfill({ json: {
    app_name: "JA PDF Editor", profile: "public", google_client_id: null, line_login: false, self_registration: true,
    allowed_email_domains: [], donations: false } }));
  await page.goto("/login");
  await expect(page.getByTestId("source-code-link")).toBeVisible();
  await expect(page.getByTestId("login-support-link")).toHaveCount(0);
});

test("เปิดรับบริจาค: หน้า Login มีลิงก์ ☕ ไปหน้า /support", async ({ page }) => {
  await mockPublic(page);
  await page.route("**/api/config/public", (route) => route.fulfill({ json: {
    app_name: "JA PDF Editor", profile: "public", google_client_id: null, line_login: false, self_registration: true,
    allowed_email_domains: [], donations: true } }));
  await page.goto("/login");
  await page.getByTestId("login-support-link").click();
  await expect(page).toHaveURL(/\/support$/);
  await expect(page.getByTestId("donation-qr")).toBeVisible();
});

test("หน้ารายชื่อผู้สนับสนุนแสดงชื่อหรือไม่ออกนามตามที่เลือก (ไม่ต้อง login)", async ({ page }) => {
  await page.route("**/api/donations/board", (route) => route.fulfill({ json: { items: [
    { name: "คุณใจดี", anonymous: false, message: "เป็นกำลังใจให้", date: "2026-11-08" },
    { name: "ผู้สนับสนุนไม่ประสงค์ออกนาม", anonymous: true, message: null, date: "2026-11-07" },
  ] } }));
  await page.goto("/supporters");
  const list = page.getByTestId("supporters-list");
  await expect(list).toContainText("คุณใจดี");
  await expect(list).toContainText("“เป็นกำลังใจให้”");
  await expect(list).toContainText("ผู้สนับสนุนไม่ประสงค์ออกนาม");
});

test("แอดมิน: เห็นรายการรอตรวจและกดอนุมัติตามระดับที่แนะนำ", async ({ page }) => {
  await login(page);
  const approved = [];
  let pending = [{
    id: 7, amount: 120, transferred_at: "2026-11-08T03:00:00Z", status: "pending", anonymous: false, show_on_board: true,
    display_name: "คุณใจดี", message: "สู้ ๆ", granted_plan: null, granted_days: null, admin_note: null, has_slip: false,
    user: { id: 2, email: "donor@example.com", display_name: "ใจดี", plan_type: "free", expire_date: null },
    suggested: { min_amount: 49, plan: "pro", days: 30 },
    verify_status: "retry", slip_ref: "015312101530BPM04512", slip_bank: "004", can_verify: true,
    verify_detail: { amount: null, problems: ["ธนาคารยังไม่พร้อมให้ตรวจ"] },
  }];
  const verified = [];
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: { id: 1, email: "admin@example.com", is_admin: true, is_active: true, plan_type: "premium" } }));
  await page.route("**/api/admin/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/admin/stats")) return route.fulfill({ json: { total_users: 3, total_files: 5, total_storage: 1024, ai_requests_today: 0 } });
    if (url.pathname.endsWith("/admin/users")) return route.fulfill({ json: { users: [] } });
    if (url.pathname.endsWith("/admin/plans")) return route.fulfill({ json: [] });
    if (url.pathname.endsWith("/admin/quotas")) return route.fulfill({ json: { alert_percent: 80, items: [], history: [] } });
    if (url.pathname.endsWith("/admin/donations/config")) {
      return route.fulfill({ json: { enabled: true, promptpay_id: "0812345678", receiver_name: "ทดสอบ", tiers: INFO.tiers, thank_you: "",
        verify_provider: "easyslip", verify_key_set: true, verify_bank_account: "", auto_approve: true } });
    }
    if (url.pathname.endsWith("/verify")) {
      verified.push(url.pathname);
      return route.fulfill({ json: {} });
    }
    if (url.pathname.endsWith("/approve")) {
      approved.push(url.pathname);
      pending = [];
      return route.fulfill({ json: {} });
    }
    if (url.pathname.endsWith("/admin/donations")) return route.fulfill({ json: { items: pending, pending: pending.length } });
    return route.fulfill({ status: 404, json: { detail: "not mocked" } });
  });
  await page.goto("/admin");
  const panel = page.getByTestId("donations-panel");
  await expect(panel.getByTestId("donations-pending")).toContainText("รอตรวจ 1");
  await panel.getByRole("button", { name: /รับบริจาค/ }).click();
  await expect(panel.getByLabel("เลขพร้อมเพย์")).toHaveValue("0812345678");
  const list = panel.getByTestId("donations-list");
  await expect(list).toContainText("donor@example.com");
  await expect(list).toContainText("คุณใจดี");
  await expect(panel.getByTestId("verify-settings")).toContainText("ตั้งไว้แล้ว");
  await expect(list.getByTestId("verify-badge")).toContainText("รอตรวจอีกครั้ง");
  await expect(list).toContainText("เลขอ้างอิง 015312101530BPM04512");
  await list.getByTestId("donation-verify").click();
  await expect.poll(() => verified).toEqual(["/api/admin/donations/7/verify"]);
  await list.getByTestId("donation-approve").click();
  await expect.poll(() => approved).toEqual(["/api/admin/donations/7/approve"]);
  await expect(panel.getByText("ไม่มีรายการ")).toBeVisible();
});
