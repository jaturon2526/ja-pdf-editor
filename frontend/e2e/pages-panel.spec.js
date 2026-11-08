import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

// แยกหน้าเอกสาร + แผงหน้าเอกสาร/บุ๊กมาร์ก (sample.pdf มี 3 หน้า)
test.describe("แยกหน้า / แผงหน้าเอกสาร", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await uploadSample(page);
    await expect(page.locator(".thumbnail-item img")).toHaveCount(3);
  });

  test("แยกหน้า: ตรวจเลขหน้าก่อนส่ง แสดงสรุป และได้ชื่อไฟล์จากเอกสาร", async ({ page }) => {
    await page.getByRole("button", { name: "ไฟล์", exact: true }).click();
    await page.getByText("แยกหน้า (Extract Pages)...").click();
    const input = page.getByLabel(/หน้าที่ต้องการ/);
    await input.fill("1, 9");
    await expect(page.getByRole("alert")).toHaveText("ไม่มีหน้า 9 (เอกสารมี 3 หน้า)");
    await input.fill("3, 1-2");
    await expect(page.getByTestId("extract-summary")).toHaveText("จะได้ 3 หน้า: 3, 1-2");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "ดาวน์โหลด", exact: true }).click();
    const file = await download; // ชื่อไทยต้องรัน Chromium ด้วย locale UTF-8 (LANG=C.UTF-8) ไม่งั้นได้ "download"
    expect(file.suggestedFilename()).toMatch(/^sample \(หน้า 3,1-2\)\.pdf$/);
    await expect(page.getByText(/ดาวน์โหลด ".*\(หน้า 3,1-2\)\.pdf" แล้ว/)).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    await page.getByRole("button", { name: "ไฟล์", exact: true }).click();
    await page.getByText("แยกหน้า (Extract Pages)...").click();
    await expect(page.getByLabel(/หน้าที่ต้องการ/)).toHaveValue(""); // เปิดใหม่ไม่ค้างค่าเดิม
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("มือถือ: กดค้างที่หน้า → เมนูของแอปเมนูเดียว ไม่มีการเลือกข้อความ/เมนูของ iOS", async ({ page }) => {
    const sidebar = page.getByTestId("page-sidebar");
    // ปิดการเลือกข้อความและเมนู "คัดลอก/ค้นดู" ของ iOS ทั้งแผง (เดิมกดค้างแล้วขึ้นซ้อนกับเมนูของแอป)
    const css = await sidebar.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { select: cs.userSelect || cs.webkitUserSelect, callout: el.className.includes("[-webkit-touch-callout:none]") };
    });
    expect(css).toEqual({ select: "none", callout: true });

    const thumb = page.locator(".thumbnail-item").nth(1);
    const box = await thumb.boundingBox();
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    const touch = { pointerType: "touch", button: 0, buttons: 1, isPrimary: true, clientX: x, clientY: y, bubbles: true, pointerId: 7 };
    await thumb.dispatchEvent("pointerdown", touch);
    await thumb.dispatchEvent("contextmenu", { clientX: x, clientY: y, bubbles: true, cancelable: true }); // Android ยิงด้วย
    await page.waitForTimeout(700);
    const menu = page.getByRole("menu");
    await expect(menu).toHaveCount(1);
    const mbox = await menu.boundingBox();
    expect(mbox.x).toBeGreaterThan(x); // เยื้องจากนิ้ว ไม่ใช่ใต้นิ้วพอดี
    await page.evaluate(({ x, y }) => {
      window.dispatchEvent(new PointerEvent("pointerup", { pointerType: "touch", clientX: x, clientY: y, pointerId: 7 }));
    }, { x, y });
    await thumb.dispatchEvent("click"); // click ที่ตามมาตอนยกนิ้ว — ต้องไม่ปิดเมนู/ไม่กระโดดหน้า
    await expect(menu).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "ลบหน้านี้ทิ้ง" })).toBeEnabled();
    await page.getByRole("menuitem", { name: "หมุนขวา ↻ (90°)" }).click();
    await expect(menu).toHaveCount(0);
  });

  test("มือถือ: เลือกหลายหน้าจากเมนูกดค้าง → แตะเลือก → จัดการทั้งชุด → เสร็จ", async ({ page }) => {
    const items = page.locator(".thumbnail-item");
    const box = await items.nth(1).boundingBox();
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await items.nth(1).dispatchEvent("pointerdown", { pointerType: "touch", button: 0, buttons: 1, isPrimary: true, clientX: x, clientY: y, bubbles: true, pointerId: 9 });
    await page.waitForTimeout(700);
    await page.evaluate(({ x, y }) => window.dispatchEvent(new PointerEvent("pointerup", { pointerType: "touch", clientX: x, clientY: y, pointerId: 9 })), { x, y });
    await page.getByRole("menuitem", { name: "☑ เลือกหลายหน้า" }).click();

    const bar = page.getByTestId("select-mode-bar");
    await expect(bar).toContainText("เลือก 1 หน้า"); // หน้าที่กดค้างถูกเลือกไว้แล้ว
    await items.nth(2).click(); // แตะ = เลือกเพิ่ม ไม่กระโดดหน้า
    await expect(bar).toContainText("เลือก 2 หน้า");
    await expect(items.nth(0)).toHaveClass(/border-sky-400/); // หน้าที่ดูอยู่ยังเป็นหน้า 1
    await items.nth(1).click(); // แตะซ้ำ = เลิกเลือก
    await expect(bar).toContainText("เลือก 1 หน้า");
    await bar.getByRole("button", { name: "ทั้งหมด" }).click();
    await expect(bar).toContainText("เลือก 3 หน้า");
    await bar.getByRole("button", { name: "ล้าง" }).click();
    await expect(bar.getByRole("button", { name: "จัดการ ▾" })).toBeDisabled();
    await items.nth(0).click();
    await items.nth(2).click();

    await bar.getByRole("button", { name: "จัดการ ▾" }).click();
    await expect(page.getByRole("menuitem", { name: "☑ เลือกหลายหน้า" })).toHaveCount(0);
    await page.getByRole("menuitem", { name: "หมุนขวา ↻ (90°) (2 หน้า)" }).click();
    await expect(page.getByText(/หมุนหน้าที่เลือก/)).toBeVisible();
    await expect(bar).toContainText("เลือก 2 หน้า"); // ยังอยู่ในโหมดเลือก ทำต่อได้

    await bar.getByRole("button", { name: "เสร็จ" }).click();
    await expect(bar).toHaveCount(0);
    await expect(page.locator(".thumbnail-item span.bg-sky-500")).toHaveCount(0); // ไม่มีเครื่องหมายเลือกค้าง
  });

  test("เลื่อนหน้าลง 2 ครั้ง: หน้าที่เลือกย้ายต่อเนื่อง (selection ตามไป)", async ({ page }) => {
    const items = page.locator(".thumbnail-item");
    await items.nth(0).click();
    await items.nth(0).click({ button: "right" });
    await page.getByRole("menuitem", { name: "เลื่อนหน้าลง" }).click();
    await expect(page.getByText("เลื่อนหน้าลงสำเร็จ")).toBeVisible();
    await items.nth(1).click({ button: "right" }); // หน้าแรกเดิมตอนนี้อยู่ตำแหน่ง 2
    await page.getByRole("menuitem", { name: "เลื่อนหน้าลง" }).click();
    await expect(page.getByRole("menuitem")).toHaveCount(0);
    // เลื่อนลงจนสุดแล้ว — เมนูเลื่อนลงต้องปิด (selection อยู่ที่หน้าสุดท้าย)
    await expect(page.locator(".thumbnail-item img")).toHaveCount(3);
    await items.nth(2).click({ button: "right" });
    await expect(page.getByRole("menuitem", { name: "เลื่อนหน้าลง" })).toBeDisabled();
    await expect(page.getByRole("menuitem", { name: "เลื่อนหน้าขึ้น" })).toBeEnabled();
  });

  test("ลบทุกหน้าไม่ได้", async ({ page }) => {
    const items = page.locator(".thumbnail-item");
    await items.nth(0).click();
    await items.nth(2).click({ modifiers: ["Shift"] });
    await items.nth(1).click({ button: "right" });
    await expect(page.getByRole("menuitem", { name: "ลบหน้าที่เลือก (3 หน้า)" })).toBeDisabled();
  });

  test("บุ๊กมาร์กเรียงตามหน้า", async ({ page }) => {
    const items = page.locator(".thumbnail-item");
    await items.nth(2).click();
    await page.getByRole("button", { name: "บุ๊คมาร์ค" }).click();
    await page.getByRole("button", { name: /เพิ่มที่คั่นหน้า/ }).click();
    await expect(page.getByTestId("bookmark-item")).toHaveCount(1);
    await page.getByRole("button", { name: "หน้าเอกสาร" }).click();
    await items.nth(0).click();
    await page.getByRole("button", { name: "บุ๊คมาร์ค" }).click();
    await page.getByRole("button", { name: /เพิ่มที่คั่นหน้า/ }).click();
    await expect(page.getByTestId("bookmark-item")).toHaveCount(2);
    await expect(page.getByTestId("bookmark-item").first()).toContainText("หน้า 1");
  });
});
