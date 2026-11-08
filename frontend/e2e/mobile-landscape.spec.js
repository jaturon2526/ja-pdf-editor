// มือถือแนวนอน (iPhone 13 หมุนเป็น 844×390 — กว้างเกิน 768px แต่เป็นจอสัมผัสที่เตี้ย) ต้องได้หน้าตาแบบมือถือเหมือนแนวตั้ง:
// ปุ่ม ☰, แผงรายการหน้าแบบเลื่อนเข้าออก (ไม่เปิดค้าง), ซูมพอดีความกว้าง · คอมจอกว้างยังเป็นแบบเดิม
// + ชื่อแอปในแถบบน Editor (มือถือ) และหน้าเข้าสู่ระบบ · ข้อความ "กำลังโหลดหน้า…" ไม่ถูกบีบ
import { devices, expect, test } from "@playwright/test";
import { login } from "./helpers.js";

const iPhone = devices["iPhone 13"];

async function openSample(page) {
  await login(page);
  await page.setInputFiles("input[type=file][accept*='.pdf']", "e2e/fixtures/sample.pdf");
  await page.waitForURL("**/editor/**");
  await expect(page.locator(".page-image")).toBeVisible();
}

test.describe("มือถือแนวนอน", () => {
  test.use({ viewport: { width: 844, height: 390 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, userAgent: iPhone.userAgent });

  test("ได้หน้าตาแบบมือถือ: ☰, แผงหน้าไม่เปิดค้าง, ชื่อแอป, ซูมพอดีความกว้าง", async ({ page }) => {
    await openSample(page);
    await expect(page.getByTitle("เมนูหลัก")).toBeVisible();
    await expect(page.getByTestId("page-sidebar")).toBeHidden();
    await expect(page.getByTestId("app-brand").first()).toBeVisible();
    await expect(page.getByTestId("app-brand").first()).toContainText("JA PDF");
    // ซูมพอดีความกว้าง: หน้ากว้างเกือบเต็มพื้นที่แสดงผล
    await expect.poll(async () => {
      const box = await page.locator(".page-image").boundingBox();
      return box ? box.width : 0;
    }).toBeGreaterThan(700);
    await page.screenshot({ path: "test-results/landscape-editor.png" });
  });
});

test.describe("คอมพิวเตอร์", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("จอกว้างยังเป็นแบบคอม: เมนูบาร์เต็ม, แผงหน้าเปิด, ไม่มีชื่อแอปในแถบบน Editor", async ({ page }) => {
    await openSample(page);
    await expect(page.getByTitle("เมนูหลัก")).toBeHidden();
    await expect(page.getByTestId("page-sidebar")).toBeVisible();
    await expect(page.getByTestId("app-brand").filter({ visible: true })).toHaveCount(0);
  });

  test("หน้าเข้าสู่ระบบและ Dashboard มีโลโก้ + ชื่อแอป", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("app-brand")).toContainText("JA PDF Editor");
    await expect(page).toHaveTitle("JA PDF Editor");
    await login(page);
    await expect(page.getByTestId("app-brand")).toContainText("JA PDF Editor");
  });

  test("ข้อความกำลังโหลดหน้าไม่ถูกบีบ", async ({ page }) => {
    await login(page);
    await page.route(/\/pdf\/[^/]+\/page\/\d+/, async (route) => { await new Promise((r) => setTimeout(r, 1500)); await route.continue(); });
    await page.setInputFiles("input[type=file][accept*='.pdf']", "e2e/fixtures/sample.pdf");
    const loading = page.locator(".page-loading");
    await expect(loading).toBeVisible();
    const box = await loading.boundingBox();
    expect(box.width).toBeGreaterThan(200);
    expect(box.height).toBeLessThan(box.width * 3);
    const textBox = await loading.evaluate((el) => {
      const r = document.createRange(); r.selectNodeContents(el); const b = r.getBoundingClientRect(); return { w: b.width, h: b.height };
    });
    expect(textBox.h).toBeLessThan(30); // บรรทัดเดียว
  });
});
