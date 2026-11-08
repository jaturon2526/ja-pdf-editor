// รูปโปรไฟล์: เลือกอีโมจิ + เปลี่ยนสี → ใช้ · อัปโหลดรูป → ครอป → ใช้ · แสดงที่มุมขวาบนของ Dashboard · ลบรูป
import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

// PNG 2×1 พิกเซล (แดง/น้ำเงิน) — ครอปเป็นสี่เหลี่ยมได้
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAEElEQVR4nGP4z8DAwMDwHwAF/AL+vB4p4QAAAABJRU5ErkJggg==",
  "base64",
);

test("เลือกอีโมจิ / อัปโหลดรูป / ลบรูปโปรไฟล์", async ({ page }) => {
  await login(page);
  await page.goto("/profile");
  const section = page.getByTestId("avatar-section");
  await section.getByRole("button", { name: "เลือกอีโมจิ" }).click();
  const picker = page.getByTestId("emoji-picker");
  await expect(picker.getByRole("button", { name: "แมว" })).toBeVisible();
  await expect(picker.locator("img").first()).toBeVisible({ timeout: 15_000 });
  await picker.getByRole("button", { name: "แมว" }).click();
  await picker.getByTestId("face-colors").getByRole("button", { name: "สีหน้า #34D399" }).click();
  await picker.getByRole("button", { name: "ใช้อีโมจินี้" }).click();
  await expect(section.getByRole("status")).toContainText("บันทึกรูปโปรไฟล์แล้ว");
  await expect(section.getByTestId("user-avatar").locator("img")).toHaveAttribute("src", /\/api\/auth\/avatar\/\d+\.png\?t=/);

  await page.goto("/dashboard");
  const headerImg = page.getByRole("button", { name: "เมนูบัญชี" }).locator("img");
  await expect(headerImg).toHaveAttribute("src", /\/api\/auth\/avatar\//);
  await expect.poll(() => headerImg.evaluate((el) => el.naturalWidth)).toBe(256);

  await page.goto("/profile");
  await section.getByLabel("เลือกรูปโปรไฟล์").setInputFiles({ name: "me.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByTestId("avatar-cropper")).toBeVisible();
  await page.getByRole("button", { name: "ใช้รูปนี้" }).click();
  await expect(section.getByRole("status")).toContainText("บันทึกรูปโปรไฟล์แล้ว");

  await section.getByRole("button", { name: "ลบรูป" }).click();
  await expect(section.getByRole("status")).toContainText("ลบรูปโปรไฟล์แล้ว");
  await expect(section.getByTestId("user-avatar").locator("img")).toHaveCount(0);
});
