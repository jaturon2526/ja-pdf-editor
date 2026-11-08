import { expect, test } from "@playwright/test";
import { login, SAMPLE_PDF, uploadSample } from "./helpers.js";

for (const [mode, label] of [["editable", "แก้ไขข้อความได้อิสระ"], ["layout", "รักษาหน้าตาเหมือนต้นฉบับ"]]) {
  test(`แปลง PDF เป็น Word (${mode}) จาก Dashboard แล้วได้ไฟล์ .docx`, async ({ page }) => {
    test.setTimeout(150_000); // การแปลงครั้งแรกใน container ช้ากว่าปกติ (โหลดโมดูล/ฟอนต์)
    await login(page);
    await uploadSample(page);
    await page.goto("/dashboard");
    await page.getByRole("button", { name: "เมนูไฟล์" }).first().click();
    await page.getByRole("menuitem", { name: "แปลงเป็น Word" }).click();
    const download = page.waitForEvent("download", { timeout: 120_000 });
    await page.getByRole("button", { name: new RegExp(label) }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.docx$/);
    await expect(page.getByText(/แปลงไฟล์สำเร็จ/)).toBeVisible();
  });
}

test("ผู้ที่ไม่ได้ login ถูกพาไปหน้า login", async ({ page }) => {
  // context ใหม่ไม่มี token — เปิดหน้า Dashboard ตรงๆ ต้องถูกพาไปหน้า login
  await page.goto("/dashboard");
  await page.waitForURL((url) => url.pathname === "/" || url.pathname === "/login");
  await expect(page.locator("input[type=password]")).toBeVisible();
});

test("เลือกหลายไฟล์แล้วลบพร้อมกันจาก Dashboard", async ({ page }) => {
  await login(page);
  for (let i = 0; i < 3; i++) {
    await page.goto("/dashboard");
    await uploadSample(page);
  }
  await page.goto("/dashboard");
  await page.evaluate(() => localStorage.setItem("viewMode", "grid"));
  await page.reload();
  const cards = page.getByTestId("file-card");
  await expect(cards.first()).toBeVisible();
  const before = await cards.count();

  await page.getByRole("button", { name: "เลือกหลายไฟล์" }).click();
  // ในโหมดเลือก คลิกการ์ด = เลือก (ไม่เปิดไฟล์)
  await cards.nth(0).click();
  await cards.nth(1).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByTestId("selected-count")).toHaveText("เลือกแล้ว 2 ไฟล์");

  await page.getByRole("button", { name: "ลบที่เลือก (2)" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("ยืนยันการลบเอกสาร 2 ไฟล์");
  await dialog.getByRole("button", { name: "ลบ 2 ไฟล์" }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByText("ลบเอกสาร 2 ไฟล์เรียบร้อยแล้ว")).toBeVisible();
  await expect(cards).toHaveCount(before - 2);
  // ลบเสร็จแล้วออกจากโหมดเลือก
  await expect(page.getByRole("button", { name: "เลือกหลายไฟล์" })).toBeVisible();
});

test("ใส่ลายน้ำจากเครื่องมือด่วน โดยไม่ต้องเปิดไฟล์ → ได้ไฟล์ใหม่", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.goto("/dashboard");
  await page.evaluate(() => localStorage.setItem("viewMode", "grid"));
  await page.reload();
  await expect(page.getByTestId("file-card").first()).toBeVisible();
  const before = await page.getByTestId("file-card").count();

  await page.getByRole("button", { name: /ใส่ลายน้ำ/ }).click();
  const chooser = page.getByRole("dialog", { name: "เลือกเอกสารที่จะใส่ลายน้ำ" });
  await chooser.getByRole("button", { name: "sample.pdf" }).first().click(); // ไฟล์ล่าสุดอยู่บนสุด
  const form = page.getByRole("dialog", { name: "ใส่ลายน้ำ" });
  await form.getByLabel("ข้อความลายน้ำ").fill("ลับเฉพาะ");
  await expect(form.getByTestId("watermark-preview")).toContainText("ลับเฉพาะ");
  await form.getByRole("button", { name: "ใส่ลายน้ำ", exact: true }).click();

  const done = page.getByRole("dialog", { name: "ใส่ลายน้ำเรียบร้อยแล้ว" });
  await expect(done).toContainText(/sample \(ลายน้ำ\)( \(\d+\))?\.pdf/, { timeout: 30_000 });
  await done.getByRole("button", { name: "ปิด", exact: true }).click();
  await expect(page.getByTestId("file-card")).toHaveCount(before + 1);
});

test("เซ็นเซอร์ด้วยคำค้นหาจากเครื่องมือด่วน: พบคำ → ได้ไฟล์ใหม่ · ไม่พบ → ไม่สร้างไฟล์", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.goto("/dashboard");
  await page.evaluate(() => localStorage.setItem("viewMode", "grid"));
  await page.reload();
  await expect(page.getByTestId("file-card").first()).toBeVisible();
  const before = await page.getByTestId("file-card").count();

  const pick = async () => {
    await page.getByRole("button", { name: /เซ็นเซอร์ด้วยคำค้นหา/ }).click();
    await page.getByRole("dialog", { name: "เลือกเอกสารที่จะเซ็นเซอร์" }).getByRole("button", { name: "sample.pdf" }).first().click();
  };

  await pick();
  await page.getByLabel("คำที่ต้องการเซ็นเซอร์").fill("ไม่มีคำนี้แน่นอน");
  await page.getByRole("button", { name: "เซ็นเซอร์", exact: true }).click();
  const notFound = page.getByRole("dialog", { name: "ไม่พบคำที่ค้นหา" });
  await expect(notFound).toBeVisible({ timeout: 30_000 });
  await notFound.getByRole("button", { name: "ค้นหาคำอื่น" }).click();

  await page.getByLabel("คำที่ต้องการเซ็นเซอร์").fill("บรรทัดทดสอบ");
  await page.getByRole("button", { name: "เซ็นเซอร์", exact: true }).click();
  const done = page.getByRole("dialog", { name: /เซ็นเซอร์แล้ว \d+ จุด/ });
  await expect(done).toContainText(/sample \(เซ็นเซอร์\)( \(\d+\))?\.pdf/, { timeout: 30_000 });
  await done.getByRole("button", { name: "ปิด", exact: true }).click();
  await expect(page.getByTestId("file-card")).toHaveCount(before + 1);
});

test("เมนู ☰ ของไฟล์: ดาวน์โหลด · คุณสมบัติเอกสาร · เข้ารหัส PDF (ได้ไฟล์ใหม่)", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.goto("/dashboard");
  await page.evaluate(() => localStorage.setItem("viewMode", "grid"));
  await page.reload();
  await expect(page.getByTestId("file-card").first()).toBeVisible();
  const before = await page.getByTestId("file-card").count();
  const menu = () => page.getByRole("button", { name: "เมนูไฟล์" }).first().click(); // ไฟล์ที่เพิ่งอัปโหลดอยู่บนสุด

  await menu();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "ดาวน์โหลด" }).click();
  expect((await download).suggestedFilename()).toBe("sample.pdf");

  await menu();
  await page.getByRole("menuitem", { name: "คุณสมบัติเอกสาร" }).click();
  await expect(page.getByText("จำนวนหน้า (Page Count)")).toBeVisible();
  await expect(page.locator(".docprops-modal-card")).toContainText("3");
  await page.keyboard.press("Escape");
  await page.locator(".modal-overlay").click({ position: { x: 5, y: 5 } });

  await menu();
  await page.getByRole("menuitem", { name: "เข้ารหัส PDF" }).click();
  await page.getByPlaceholder("รหัสผ่านใหม่").fill("E2e-pass!");
  await page.getByPlaceholder("ยืนยันรหัสผ่านอีกครั้ง").fill("E2e-pass!");
  await page.getByRole("dialog", { name: "เข้ารหัส PDF" }).getByRole("button", { name: "เข้ารหัส PDF" }).click();
  const done = page.getByRole("dialog", { name: "เข้ารหัสเรียบร้อยแล้ว" });
  await expect(done).toContainText(/sample \(เข้ารหัส\)( \(\d+\))?\.pdf/, { timeout: 30_000 }); // ชื่อซ้ำจากรอบก่อนได้ (2), (3)
  await done.getByRole("button", { name: "ปิด", exact: true }).click();
  await expect(page.getByTestId("file-card")).toHaveCount(before + 1);
});

test("เมนู ☰ ไม่ปิดเองเมื่อหน้าเลื่อน (เช่น เนื้อหาด้านบนโหลดเสร็จ) และเลื่อนตามการ์ด", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.goto("/dashboard");
  await page.evaluate(() => localStorage.setItem("viewMode", "grid"));
  await page.reload();
  const button = page.getByRole("button", { name: "เมนูไฟล์" }).first();
  await button.click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  const offset = async () => (await menu.boundingBox()).y - (await button.boundingBox()).y;
  const y0 = (await button.boundingBox()).y;
  const offsetBefore = await offset();
  await page.evaluate(() => window.scrollBy(0, 60));
  await expect.poll(async () => (await button.boundingBox()).y).not.toBe(y0); // หน้าเลื่อนจริง
  await expect(menu).toBeVisible();
  expect(Math.abs((await offset()) - offsetBefore)).toBeLessThan(1); // เมนูยังติดกับปุ่ม
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
});

test("แปลงเป็น Word จากเมนู เครื่องมือ ในหน้า Editor (เปิดดูไฟล์ก่อนแปลง)", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page);
  await uploadSample(page);   // เปิดไฟล์ใน Editor
  await page.getByRole("button", { name: "เครื่องมือ", exact: true }).click();
  await page.getByText("แปลงเป็น Word...").click();
  const download = page.waitForEvent("download", { timeout: 120_000 });
  await page.getByRole("button", { name: /รักษาหน้าตาเหมือนต้นฉบับ/ }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.docx$/);
});

test("การ์ด แปลงเป็น Word ในเครื่องมือด่วน: เลือกไฟล์แล้วเปิดหน้าต่างเลือกรูปแบบ", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.goto("/dashboard");
  await page.getByTestId("tool-card-word").click();
  const chooser = page.getByRole("dialog", { name: "เลือกเอกสารที่จะแปลงเป็น Word" });
  await expect(chooser.getByText(/ไฟล์สแกน/)).toBeVisible();
  await chooser.getByRole("button", { name: /^sample/ }).first().click();
  await expect(chooser).toHaveCount(0);
  // PDF ทั่วไป → หน้าต่างเลือกรูปแบบเดิม (ไฟล์สแกนจะได้หน้าต่าง "แปลงไฟล์สแกนเป็น Word" แทน)
  await expect(page.getByRole("button", { name: /รักษาหน้าตาเหมือนต้นฉบับ/ })).toBeVisible();
});

test("รวมไฟล์ PDF: ไฟล์จากเครื่อง + ไฟล์ในเอกสารของฉัน → ไฟล์ใหม่ในเอกสารของฉัน", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.goto("/dashboard");
  await page.getByRole("button", { name: /รวมไฟล์ PDF/ }).click();
  const modal = page.getByTestId("merge-modal");
  await modal.getByTestId("merge-file-input").setInputFiles(SAMPLE_PDF);
  await modal.getByTestId("merge-add-stored").click();
  await modal.getByTestId("merge-doc-list").getByRole("checkbox").first().check();
  await modal.getByTestId("merge-add-picked").click();
  await expect(modal.getByTestId("merge-list").locator("li")).toHaveCount(2);
  await modal.getByRole("button", { name: /^เลื่อน .* ขึ้น$/ }).nth(1).click();     // สลับลำดับ
  await modal.getByTestId("merge-submit").click();
  await page.waitForURL("**/editor/**", { timeout: 60_000 });
  await page.goto("/dashboard");
  await expect(page.getByText(/\(รวม 2 ไฟล์\)\.pdf/).first()).toBeVisible();
});
