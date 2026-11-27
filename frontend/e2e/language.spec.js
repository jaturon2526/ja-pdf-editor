import { expect, test } from "@playwright/test";
import { login } from "./helpers.js";

test.describe("Language switching (i18n)", () => {
  test("เปลี่ยนภาษาในหน้าโปรไฟล์เป็น English แล้วคงอยู่หลังรีโหลด และสลับกลับเป็นไทยได้", async ({ page }) => {
    await login(page);

    // ไปหน้าโปรไฟล์แล้วเปลี่ยนเป็นภาษาอังกฤษ
    await page.goto("/profile");
    const select = page.getByTestId("profile-language-select");
    await expect(select).toBeVisible();
    await select.selectOption("en");
    await page.getByTestId("profile-save-button").click();
    await expect(page.getByTestId("profile-save-success")).toContainText("Profile saved successfully");

    // กลับหน้า Dashboard ตรวจว่าเปลี่ยนเป็นภาษาอังกฤษและยังคงอยู่หลัง reload
    await page.goto("/dashboard");
    await expect(page.getByTestId("dashboard-my-docs-heading")).toHaveText("My Documents");
    await page.reload();
    await expect(page.getByTestId("dashboard-my-docs-heading")).toHaveText("My Documents");

    // สลับกลับเป็นภาษาไทยเพื่อไม่กระทบเทสต์อื่นที่ใช้บัญชีทดสอบเดียวกัน
    await page.goto("/profile");
    await page.getByTestId("profile-language-select").selectOption("th");
    await page.getByTestId("profile-save-button").click();
    await expect(page.getByTestId("profile-save-success")).toContainText("บันทึกข้อมูลเรียบร้อยแล้ว");
    await page.goto("/dashboard");
    await expect(page.getByTestId("dashboard-my-docs-heading")).toHaveText("เอกสารของฉัน");
  });
});
