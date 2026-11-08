import { expect, test } from "@playwright/test";
import { login, uploadSample } from "./helpers.js";

// เมนูไฟล์: ดาวน์โหลด/พิมพ์ไม่บันทึกทับไฟล์ในเอกสารของฉัน, เตือนก่อนทิ้งการแก้ไขที่ยังไม่บันทึก
test.describe("เมนูไฟล์", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await uploadSample(page);
    await expect(page.locator(".thumbnail-item img")).toHaveCount(3);
  });

  async function rotateFirstPage(page) {
    await page.locator(".thumbnail-item").first().click({ button: "right" });
    await page.getByText("หมุนขวา").first().click();
    await expect(page.getByText("หมุนหน้าสำเร็จ")).toBeVisible();
  }

  test("ดาวน์โหลดไม่บันทึกทับไฟล์เดิม", async ({ page }) => {
    await rotateFirstPage(page);
    const saves = [];
    page.on("request", (r) => /\/pdf\/[^/]+\/save$/.test(r.url()) && saves.push(r.url()));
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "ดาวน์โหลดลงเครื่อง" }).click();
    await download;
    expect(saves).toHaveLength(0);
  });

  test("กลับหน้าเอกสารของฉันขณะมีการแก้ไขที่ยังไม่บันทึก → ถามก่อน · บันทึกแล้วไม่ถาม", async ({ page }) => {
    await rotateFirstPage(page);
    let asked = "";
    page.once("dialog", (d) => { asked = d.message(); d.dismiss(); });
    await page.getByRole("button", { name: "ไฟล์", exact: true }).click();
    await page.getByText("← กลับหน้าเอกสารของฉัน").click();
    expect(asked).toContain("ยังไม่ได้บันทึก");
    await expect(page).toHaveURL(/\/editor\//);

    await page.keyboard.press("Control+s");
    await expect(page.getByText("บันทึกเอกสารเรียบร้อยแล้ว")).toBeVisible();
    let askedAgain = false;
    page.once("dialog", (d) => { askedAgain = true; d.accept(); });
    await page.getByRole("button", { name: "ไฟล์", exact: true }).click();
    await page.getByText("← กลับหน้าเอกสารของฉัน").click();
    await expect(page).toHaveURL(/\/dashboard/);
    expect(askedAgain).toBe(false);
  });
});
