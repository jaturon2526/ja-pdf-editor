// มือถือ (จำลอง iPhone): ปัดเปลี่ยนหน้า, นิ้วเดียวเลื่อนจอ, กดค้างเลือกข้อความ, สองนิ้วซูม, พิมพ์ในแท็บใหม่
// ใช้ CDP Input.dispatchTouchEvent ส่งสัมผัสหลายนิ้วจริง (Playwright มีแค่ tap) — sample.pdf มี 3 หน้า
import { devices, expect, test } from "@playwright/test";
import { login } from "./helpers.js";

const iPhone = devices["iPhone 13"];
test.use({ viewport: iPhone.viewport, deviceScaleFactor: iPhone.deviceScaleFactor, isMobile: true, hasTouch: true, userAgent: iPhone.userAgent });

async function openSample(page) {
  await login(page);
  await page.setInputFiles("input[type=file][accept*='.pdf']", "e2e/fixtures/sample.pdf");
  await page.waitForURL("**/editor/**");
  await expect(page.locator(".page-image")).toBeVisible();
}

async function touchCdp(page) {
  const cdp = await page.context().newCDPSession(page);
  const send = (type, points) =>
    cdp.send("Input.dispatchTouchEvent", { type, touchPoints: points.map((p, i) => ({ x: p.x, y: p.y, id: i })) });
  return {
    send,
    async drag(from, to, { steps = 8, holdMs = 0 } = {}) {
      await send("touchStart", [from]);
      if (holdMs) await page.waitForTimeout(holdMs);
      for (let i = 1; i <= steps; i++) {
        await send("touchMove", [{ x: from.x + ((to.x - from.x) * i) / steps, y: from.y + ((to.y - from.y) * i) / steps }]);
        await page.waitForTimeout(16);
      }
      await send("touchEnd", []);
    },
    async pinch(center, startGap, endGap, steps = 10) {
      const pts = (g) => [{ x: center.x - g / 2, y: center.y }, { x: center.x + g / 2, y: center.y }];
      await send("touchStart", pts(startGap));
      for (let i = 1; i <= steps; i++) {
        await send("touchMove", pts(startGap + ((endGap - startGap) * i) / steps));
        await page.waitForTimeout(16);
      }
      await send("touchEnd", []);
    },
  };
}

const pageInput = (page) => page.getByLabel("หน้าปัจจุบัน");
const zoomInput = (page) => page.getByTitle("พิมพ์เปอร์เซ็นต์ซูม");

test.describe("มือถือ: ท่าทางนิ้วบนหน้าเอกสาร", () => {
  test.beforeEach(async ({ page }) => {
    await openSample(page);
  });

  test("ปัดซ้าย/ขวา = หน้าถัดไป/ก่อนหน้า · หน้าแรกปัดขวาไม่เปลี่ยน", async ({ page }) => {
    const t = await touchCdp(page);
    const box = await page.locator(".canvas-area").boundingBox();
    const y = box.y + box.height / 2;
    await t.drag({ x: box.x + box.width - 40, y }, { x: box.x + 40, y }, { steps: 6 });
    await expect(pageInput(page)).toHaveValue("2");
    await t.drag({ x: box.x + box.width - 40, y }, { x: box.x + 40, y }, { steps: 6 });
    await expect(pageInput(page)).toHaveValue("3");
    await t.drag({ x: box.x + 40, y }, { x: box.x + box.width - 40, y }, { steps: 6 });
    await expect(pageInput(page)).toHaveValue("2");
    await t.drag({ x: box.x + 40, y }, { x: box.x + box.width - 40, y }, { steps: 6 });
    await t.drag({ x: box.x + 40, y }, { x: box.x + box.width - 40, y }, { steps: 6 });
    await expect(pageInput(page)).toHaveValue("1");
    await expect(page.getByRole("heading", { name: "คัดลอกข้อความ" })).toHaveCount(0);
  });

  test("นิ้วเดียวลากขึ้นบนหน้า = เลื่อนจอ ไม่ใช่กรอบเลือกข้อความ", async ({ page }) => {
    await zoomInput(page).fill("150");
    await zoomInput(page).press("Enter");
    await expect.poll(() => page.locator(".canvas-area").evaluate((el) => el.scrollHeight > el.clientHeight * 1.5)).toBe(true);
    await page.waitForTimeout(500);
    const area = page.locator(".canvas-area");
    const before = await area.evaluate((el) => el.scrollTop);
    const t = await touchCdp(page);
    const a = await area.boundingBox();
    const x = a.x + a.width / 2;
    await t.drag({ x, y: a.y + a.height - 120 }, { x, y: a.y + 120 }, { steps: 10 });
    await page.waitForTimeout(400);
    expect(await area.evaluate((el) => el.scrollTop)).toBeGreaterThan(before + 50);
    await expect(page.getByRole("heading", { name: "คัดลอกข้อความ" })).toHaveCount(0);
    await expect(pageInput(page)).toHaveValue("1");
  });

  test("กดค้างแล้วลาก = เลือกข้อความเพื่อคัดลอก", async ({ page }) => {
    const t = await touchCdp(page);
    const img = await page.locator(".page-image").boundingBox();
    const from = { x: img.x + 20, y: img.y + 200 };
    const to = { x: img.x + img.width - 40, y: img.y + 260 };
    await t.send("touchStart", [from]);
    await page.waitForTimeout(650);
    for (let i = 1; i <= 6; i++) {
      await t.send("touchMove", [{ x: from.x + ((to.x - from.x) * i) / 6, y: from.y + ((to.y - from.y) * i) / 6 }]);
      await page.waitForTimeout(16);
    }
    // แว่นขยายอยู่เหนือนิ้ว (ไม่ถูกนิ้วบัง) และมีภาพหน้าเอกสารจริง
    const loupe = page.getByTestId("text-loupe");
    await expect(loupe).toBeVisible();
    const lb = await loupe.boundingBox();
    expect(lb.y + lb.height).toBeLessThanOrEqual(to.y - 20);
    const painted = await loupe.evaluate((c) => {
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let dark = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i] < 120 && d[i + 1] < 120 && d[i + 2] < 120) dark++;
      return dark;
    });
    expect(painted).toBeGreaterThan(20); // ตัวหนังสือในแว่น
    await t.send("touchEnd", []);
    await expect(loupe).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "คัดลอกข้อความ" })).toBeVisible();
  });

  test("สองนิ้วกาง = ซูมเข้า จุดใต้นิ้วอยู่ที่เดิม และรูปคมตามความละเอียดจอ", async ({ page }) => {
    const img = page.locator(".page-image");
    const z0 = Number(await zoomInput(page).inputValue());
    const b0 = await img.boundingBox();
    const center = { x: b0.x + b0.width * 0.5, y: b0.y + 150 };
    // จุดบนหน้า (สัดส่วน) ที่อยู่ใต้กึ่งกลางนิ้วก่อนซูม
    const fx = (center.x - b0.x) / b0.width;
    const fy = (center.y - b0.y) / b0.height;
    const t = await touchCdp(page);
    await t.pinch(center, 80, 200);
    await expect.poll(async () => Number(await zoomInput(page).inputValue())).toBeGreaterThan(z0 * 2);
    await page.waitForTimeout(300);
    const b1 = await img.boundingBox();
    expect(b1.width).toBeGreaterThan(b0.width * 2);
    // จุดเดิมยังอยู่ใต้นิ้ว (คลาดได้ไม่กี่ px) — เดิมกระโดดไปมุมซ้ายบนของหน้า
    expect(Math.abs(b1.x + fx * b1.width - center.x)).toBeLessThan(12);
    expect(Math.abs(b1.y + fy * b1.height - center.y)).toBeLessThan(12);
    // ซูมจนหน้ากว้างกว่าจอ: เลื่อนไปขอบซ้ายสุดต้องเห็นขอบซ้ายของหน้า (เดิมล้นออกนอกพื้นที่เลื่อน)
    const area = page.locator(".canvas-area");
    await area.evaluate((el) => { el.scrollLeft = 0; });
    const a = await area.boundingBox();
    const b2 = await img.boundingBox();
    expect(b2.x).toBeGreaterThanOrEqual(a.x);
    // รูปเรนเดอร์ละเอียดกว่าขนาดบนจอ (จอ 3x → เรนเดอร์ 2x)
    const ratio = await img.evaluate((el) => el.naturalWidth / el.getBoundingClientRect().width);
    expect(ratio).toBeGreaterThan(1.8);
  });

  test("สองนิ้วหุบ = ซูมออก ไม่ต่ำกว่าขอบเขต", async ({ page }) => {
    const z0 = Number(await zoomInput(page).inputValue());
    const box = await page.locator(".page-image").boundingBox();
    const t = await touchCdp(page);
    await t.pinch({ x: box.x + box.width / 2, y: box.y + 200 }, 300, 60);
    await expect.poll(async () => Number(await zoomInput(page).inputValue())).toBeLessThan(z0);
    expect(Number(await zoomInput(page).inputValue())).toBeGreaterThanOrEqual(10);
  });
});

test("มือถือ: พิมพ์เปิดไฟล์ในแท็บใหม่ (ไม่ถูกบล็อก popup)", async ({ page }) => {
  await openSample(page);
  const popup = page.waitForEvent("popup");
  await page.getByRole("button", { name: "พิมพ์เอกสาร (Ctrl+P)" }).click();
  const tab = await popup; // เปิดตอนกด (ยังอยู่ในการกดของผู้ใช้) — เดิมเปิดหลังโหลดไฟล์ iPhone บล็อกเงียบๆ
  await expect(page.getByText(/เปิดเอกสารในแท็บใหม่แล้ว/)).toBeVisible();
  expect(tab.isClosed()).toBe(false); // แท็บไม่ถูกปิดทิ้ง (Chromium แบบ headless ดาวน์โหลด PDF แทนการแสดง จึงไม่ตรวจ URL)
});
