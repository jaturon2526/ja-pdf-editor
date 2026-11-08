// แผ่นเซ็นลายเซ็นบนมือถือ: เส้นต้องอยู่ตรงปลายนิ้ว (เดิมเลื่อนเพราะ canvas ถูกย่อด้วย CSS) และใช้ได้ทั้งลายเซ็นอิเล็กทรอนิกส์/ดิจิทัล
import { expect, test } from "@playwright/test";
import { SAMPLE_PDF, login, uploadSample } from "./helpers.js";

// ลากนิ้วเป็นเส้นตรงด้วย touch event จริง (ไม่ใช่เมาส์)
async function swipe(page, from, to, steps = 12) {
  const cdp = await page.context().newCDPSession(page);
  const pt = (x, y) => [{ x, y, radiusX: 2, radiusY: 2, force: 0.5, id: 1 }];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(from.x, from.y) });
  for (let i = 1; i <= steps; i += 1) {
    const x = from.x + ((to.x - from.x) * i) / steps;
    const y = from.y + ((to.y - from.y) * i) / steps;
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pt(x, y) });
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

// มีหมึกที่จุด (x, y) บนจอไหม — อ่านจาก canvas ที่ความละเอียดจริง
async function inkAt(page, x, y) {
  return page.evaluate(([px, py]) => {
    const c = document.querySelector("[data-testid=signature-pad]");
    const r = c.getBoundingClientRect();
    const sx = c.width / r.width;
    const d = c.getContext("2d").getImageData(Math.round((px - r.left) * sx) - 2, Math.round((py - r.top) * sx) - 2, 5, 5).data;
    let alpha = 0;
    for (let i = 3; i < d.length; i += 4) alpha = Math.max(alpha, d[i]);
    return alpha;
  }, [x, y]);
}

test.describe("มือถือ", () => {
  test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });

  test("เซ็นด้วยนิ้ว: เส้นอยู่ตรงตำแหน่งที่ลาก ไม่เลื่อน และหน้าไม่เลื่อนตาม", async ({ page }) => {
    await login(page);
    await page.setInputFiles("input[type=file][accept*='.pdf']", SAMPLE_PDF);
    await page.waitForURL("**/editor/**");
    await expect(page.getByRole("button", { name: "เมนูหลัก" })).toBeVisible();
    await page.waitForTimeout(1500); // รอหน้าเอกสารโหลด (มือถือแสดงผลต่างจากจอใหญ่)
    await page.getByRole("button", { name: "เมนูหลัก" }).click();
    await page.getByText("ลายเซ็นอิเล็กทรอนิกส์...").click();

    const dialog = page.getByRole("dialog", { name: "ลายเซ็นอิเล็กทรอนิกส์" });
    await expect(dialog.getByRole("tab", { name: "เซ็นสด" })).toHaveAttribute("aria-selected", "true"); // จอสัมผัสเริ่มที่เซ็นสด
    const pad = page.getByTestId("signature-pad");
    const box = await pad.boundingBox();
    expect(box.width).toBeGreaterThan(300); // ใช้ความกว้างจอเต็มที่
    expect(box.height).toBeGreaterThan(170);

    const from = { x: box.x + box.width * 0.15, y: box.y + box.height * 0.4 };
    const to = { x: box.x + box.width * 0.85, y: box.y + box.height * 0.6 };
    const scrollBefore = await page.evaluate(() => document.scrollingElement.scrollTop);
    await swipe(page, from, to);

    const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
    expect(await inkAt(page, mid.x, mid.y)).toBeGreaterThan(100); // หมึกอยู่ใต้นิ้วพอดี
    expect(await inkAt(page, to.x - 4, to.y)).toBeGreaterThan(100);
    expect(await inkAt(page, mid.x, mid.y + 30)).toBe(0); // ไม่เลื่อนลงไปจากตำแหน่งนิ้ว
    expect(await page.evaluate(() => document.scrollingElement.scrollTop)).toBe(scrollBefore);

    // เลิกทำ → ว่าง → ตกลงไม่ได้
    await dialog.getByRole("button", { name: "↶ เลิกทำ" }).click();
    expect(await inkAt(page, mid.x, mid.y)).toBe(0);
    await expect(dialog.getByRole("button", { name: "ตกลง" })).toBeDisabled();

    await swipe(page, from, to);
    await dialog.getByRole("button", { name: "ตกลง" }).click();
    await expect(dialog).toHaveCount(0);
  });
});

test("ลายเซ็นดิจิทัล: เลือกเซ็นสด/พิมพ์/รูปภาพ หรือไม่ใส่รูปได้", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.getByRole("button", { name: "ลายเซ็นดิจิทัล", exact: true }).click();
  await page.getByText("เซ็นดิจิทัลรับรอง...").click();
  const dialog = page.getByRole("dialog", { name: "ลายเซ็นดิจิทัล (ใบรับรอง)" });
  await expect(dialog.getByRole("tab", { name: "ไม่ใส่รูป" })).toHaveAttribute("aria-selected", "true");
  for (const name of ["เซ็นสด", "พิมพ์", "รูปภาพ"]) {
    await expect(dialog.getByRole("tab", { name })).toBeVisible();
  }
  await dialog.getByRole("tab", { name: "เซ็นสด" }).click();
  const box = await page.getByTestId("signature-pad").boundingBox();
  await page.mouse.move(box.x + 40, box.y + 60);
  await page.mouse.down();
  await page.mouse.move(box.x + 200, box.y + 100, { steps: 10 });
  await page.mouse.up();
  expect(await inkAt(page, box.x + 120, box.y + 80)).toBeGreaterThan(100);
  await dialog.getByRole("button", { name: "ยกเลิก" }).click();
  await expect(dialog).toHaveCount(0);
});
