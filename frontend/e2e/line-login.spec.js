// เข้าสู่ระบบด้วย LINE — ปุ่มหน้า Login, หน้า /auth/line/callback (เข้าได้ทันที / ขออีเมล / state ไม่ตรง), เชื่อมจากหน้าความปลอดภัย
// จำลอง /api/auth/line/* ในเบราว์เซอร์ (CI ไม่มี LINE Login channel) และจำลอง "LINE ส่งกลับ" ด้วยการให้ /start คืน URL
// ของหน้า callback เอง — ฝั่ง backend (แลก token, ตรวจ nonce, ผูกบัญชี) ทดสอบใน backend/tests/test_line_login.py
import { expect, test } from "@playwright/test";
import { EMAIL, PASSWORD, login } from "./helpers.js";

async function realToken(request) {
  const r = await request.post("/api/auth/login", { form: { username: EMAIL, password: PASSWORD } });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token;
}

async function mockLineLogin(page, handlers) {
  const calls = [];
  // หน้า Login อ่านสถานะปุ่มจาก /config/public (backend จริงใน CI ไม่ได้เปิด Google/LINE)
  const lineConfig = handlers["/auth/line/config"];
  await page.route("**/api/config/public", (route) =>
    route.fulfill({
      json: {
        app_name: "JA PDF Editor", profile: "public", google_client_id: "e2e-test.apps.googleusercontent.com",
        line_login: !!(lineConfig && lineConfig.enabled), self_registration: true, allowed_email_domains: [],
      },
    }));
  await page.route("**/api/auth/line/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace(/^\/api/, "");
    const body = req.postData() ? req.postDataJSON() : null;
    calls.push({ method: req.method(), path, body });
    const h = handlers[path];
    if (!h) return route.fulfill({ status: 404, json: { detail: "not mocked" } });
    const res = typeof h === "function" ? await h(body) : h;
    // ตอบ error: { httpStatus, json } · อื่นๆ = JSON body (มีฟิลด์ status ของ API เองได้)
    return route.fulfill(res.httpStatus ? { status: res.httpStatus, json: res.json } : { json: res });
  });
  return calls;
}

const callbackUrl = (state, code = "code-1") => `/auth/line/callback?code=${code}&state=${state}`;

test("ปุ่มเข้าสู่ระบบด้วย LINE → LINE ส่งกลับ → เข้าหน้าเอกสาร", async ({ page, request }) => {
  const token = await realToken(request);
  const calls = await mockLineLogin(page, {
    "/auth/line/config": { enabled: true },
    "/auth/line/start": { url: callbackUrl("st-1"), state: "st-1" },
    "/auth/line/callback": (b) =>
      b.state === "st-1" ? { status: "login", access_token: token, token_type: "bearer" } : { httpStatus: 400, json: { detail: "bad state" } },
  });
  await page.goto("/login");
  await expect(page.getByText("หรือใช้บัญชี Google / LINE")).toBeVisible();
  await page.getByTestId("line-login-button").click();
  await page.waitForURL("**/dashboard");
  expect(calls.find((c) => c.path === "/auth/line/callback").body).toEqual({ code: "code-1", state: "st-1" });
});

test("ไม่ได้เปิด LINE Login → ไม่มีปุ่ม", async ({ page }) => {
  await mockLineLogin(page, { "/auth/line/config": { enabled: false } });
  await page.goto("/login");
  await expect(page.getByText("หรือใช้บัญชี Google", { exact: true })).toBeVisible();
  await expect(page.getByTestId("line-login-button")).toHaveCount(0);
});

test("state ไม่ตรงกับที่เบราว์เซอร์นี้เริ่มไว้ → ไม่ส่งไป backend และแจ้งให้เริ่มใหม่", async ({ page }) => {
  const calls = await mockLineLogin(page, { "/auth/line/config": { enabled: true } });
  await page.goto(callbackUrl("someone-elses-state"));
  await expect(page.getByTestId("line-login-message")).toContainText("ไม่ได้เริ่มจากเบราว์เซอร์นี้");
  expect(calls.filter((c) => c.path === "/auth/line/callback")).toHaveLength(0);
  await page.getByRole("link", { name: "กลับไปหน้าเข้าสู่ระบบ" }).click();
  await page.waitForURL("**/login");
});

test("กดยกเลิกที่หน้า LINE → แจ้งว่ายกเลิกแล้ว", async ({ page }) => {
  await page.goto("/auth/line/callback?error=access_denied&state=x");
  await expect(page.getByTestId("line-login-message")).toHaveText("ยกเลิกการเข้าสู่ระบบด้วย LINE แล้ว");
});

test("บัญชี LINE ไม่มีอีเมล → กรอกอีเมล → กดลิงก์ยืนยันในเบราว์เซอร์เดียวกัน → เข้าระบบ", async ({ page, request }) => {
  const token = await realToken(request);
  const calls = await mockLineLogin(page, {
    "/auth/line/config": { enabled: true },
    "/auth/line/start": { url: callbackUrl("st-2"), state: "st-2" },
    "/auth/line/callback": { status: "need_email", pending: "pending-xyz", name: "คุณไลน์" },
    "/auth/line/email": (b) => ({ status: "sent", email: b.email }),
    "/auth/line/confirm": (b) =>
      b.pending === "pending-xyz" && b.token === "mail-token"
        ? { status: "login", access_token: token, token_type: "bearer" }
        : { httpStatus: 403, json: { detail: "ต้องเปิดลิงก์ยืนยันในเบราว์เซอร์เดียวกับที่กดเข้าสู่ระบบด้วย LINE" } },
  });
  await page.goto("/login");
  await page.getByTestId("line-login-button").click();
  const form = page.getByTestId("line-login-email");
  await expect(form).toContainText("สวัสดีคุณ คุณไลน์");
  await form.getByLabel("อีเมล").fill("me@example.com");
  await form.getByRole("button", { name: "ส่งลิงก์ยืนยัน" }).click();
  await expect(page.getByTestId("line-login-sent")).toContainText("me@example.com");
  expect(calls.find((c) => c.path === "/auth/line/email").body).toEqual({ pending: "pending-xyz", email: "me@example.com" });

  await page.goto("/auth/line/callback?confirm=mail-token"); // ลิงก์จากอีเมล
  await page.waitForURL("**/dashboard");
});

test("หน้าความปลอดภัย: เชื่อมบัญชี LINE เพื่อเข้าสู่ระบบ → กลับมาแสดงเชื่อมแล้ว → ยกเลิก", async ({ page }) => {
  await login(page);
  let linked = false;
  const status = () => ({
    enabled: false,
    linked: false,
    notifications: true,
    add_friend_url: "",
    login: { enabled: true, linked },
  });
  await page.route("**/api/line/status", (route) => route.fulfill({ json: status() }));
  const calls = await mockLineLogin(page, {
    "/auth/line/link-start": { url: callbackUrl("st-link"), state: "st-link" },
    "/auth/line/callback": () => {
      linked = true;
      return { status: "linked" };
    },
    "/auth/line/link": () => {
      linked = false;
      return { enabled: true, linked: false };
    },
  });
  await page.goto("/security");
  const section = page.getByTestId("line-login-section");
  await section.getByRole("button", { name: "เชื่อมบัญชี LINE เพื่อเข้าสู่ระบบ" }).click();
  await page.waitForURL((u) => u.pathname === "/security");
  await expect(section).toContainText("เชื่อมบัญชี LINE แล้ว");
  await expect(section.getByTestId("line-login-linked")).toBeVisible();
  expect(page.url()).not.toContain("line_login=");

  await section.getByRole("button", { name: "ยกเลิกการเข้าสู่ระบบด้วย LINE" }).click();
  await section.getByRole("button", { name: "ยกเลิก", exact: true }).click();
  await expect(section).toContainText("ยกเลิกการเข้าสู่ระบบด้วย LINE แล้ว");
  await expect(section.getByRole("button", { name: "เชื่อมบัญชี LINE เพื่อเข้าสู่ระบบ" })).toBeVisible();
  expect(calls.some((c) => c.method === "DELETE" && c.path === "/auth/line/link")).toBe(true);
});
