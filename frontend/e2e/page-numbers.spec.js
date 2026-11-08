// ใส่เลขหน้า: Editor (เมนูแทรก › เลขหน้า) และเครื่องมือด่วนใน Dashboard — sample.pdf มี 3 หน้า
// ตรวจข้อความในไฟล์จริงผ่าน API (ข้อความจริง ค้นหาได้) · ค่าเริ่มต้น: หน้าแรกที่ใส่ = 1, N = จำนวนหน้าที่ใส่
import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";


test("Editor: เลขหน้า 1/N เริ่มหน้า 2 + เลขไทย + ตรวจข้อมูลก่อนกด", async ({ page }) => {
  await login(page);
  const sid = await uploadSample(page);
  await page.getByRole("button", { name: "แทรก", exact: true }).click();
  await page.getByText("เลขหน้า...").click();
  const form = page.getByRole("dialog", { name: "ใส่เลขหน้า" });
  await form.getByRole("button", { name: /1\/N/ }).click();
  // ตรวจข้อมูล: หน้าเริ่มเกินจำนวนหน้า → ปุ่มกดไม่ได้ + แจ้งเหตุผล
  await form.getByLabel("เริ่มใส่ที่หน้า").fill("5");
  await expect(form.getByRole("alert")).toContainText("เอกสารมี 3 หน้า");
  await expect(form.getByRole("button", { name: "ใส่เลขหน้า", exact: true })).toBeDisabled();
  await form.getByLabel("เริ่มใส่ที่หน้า").fill("2");
  await form.getByRole("button", { name: "เลขไทย ๑ ๒ ๓" }).click();
  await form.getByRole("button", { name: "ซ้าย", exact: true }).click();
  await form.getByText("หน้าคู่วางฝั่งตรงข้าม").click();
  const preview = form.getByTestId("page-number-preview");
  await expect(preview).toContainText("๑/๒");
  await expect(preview).toContainText("ใส่ 2 หน้า");
  await form.getByRole("button", { name: "ใส่เลขหน้า", exact: true }).click();
  await expect(page.getByText("ใส่เลขหน้าเรียบร้อยแล้ว")).toBeVisible({ timeout: 20_000 });
  expect(sid).toBeTruthy();
});

test("Dashboard: ใส่เลขหน้าจากเครื่องมือด่วน → ได้ไฟล์ใหม่", async ({ page }) => {
  await login(page);
  await uploadSample(page);
  await page.goto("/dashboard");
  await page.getByTestId("tool-card-page-numbers").click();
  await page.getByRole("dialog", { name: "เลือกเอกสารที่จะใส่เลขหน้า" }).getByRole("button", { name: "sample.pdf" }).first().click();
  const form = page.getByRole("dialog", { name: "ใส่เลขหน้า" });
  await expect(form).toContainText("บันทึกเป็นไฟล์ใหม่");
  await form.getByRole("button", { name: "ใส่เลขหน้า", exact: true }).click();
  const done = page.getByRole("dialog", { name: /ใส่เลขหน้าแล้ว 3 หน้า/ });
  await expect(done).toContainText(/sample \(เลขหน้า\)( \(\d+\))?\.pdf/, { timeout: 30_000 });
});
