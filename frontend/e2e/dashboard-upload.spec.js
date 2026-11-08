// หน้าเอกสารของฉัน: อัปโหลดหลายไฟล์ — เลือกหลายไฟล์จากปุ่ม และลากวางหลายไฟล์ (มีไฟล์ที่ไม่รองรับปนมา)
import fs from "node:fs";
import { expect, test } from "@playwright/test";
import { SAMPLE_PDF, login } from "./helpers.js";

const stamp = () => Date.now().toString(36);

test("เลือกหลายไฟล์จากปุ่มอัปโหลด → อยู่หน้าเดิม และไฟล์ขึ้นในรายการครบ", async ({ page }) => {
  await login(page);
  const buf = fs.readFileSync(SAMPLE_PDF);
  const names = [`multi-a-${stamp()}.pdf`, `multi-b-${stamp()}.pdf`];
  await page.getByTestId("upload-input").setInputFiles(names.map((name) => ({ name, mimeType: "application/pdf", buffer: buf })));
  await expect(page.getByText("อัปโหลดสำเร็จ 2 ไฟล์")).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/dashboard");
  for (const n of names) await expect(page.getByText(n.replace(/\.pdf$/, ""), { exact: false }).first()).toBeVisible();
});

test("ลากวางหลายไฟล์ → อัปโหลดทุกไฟล์ที่รองรับ และแจ้งไฟล์ที่ไม่รองรับ", async ({ page }) => {
  await login(page);
  const b64 = fs.readFileSync(SAMPLE_PDF).toString("base64");
  const names = [`drop-a-${stamp()}.pdf`, `drop-b-${stamp()}.pdf`];
  await page.evaluate(
    ({ b64, names }) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const dt = new DataTransfer();
      for (const n of names) dt.items.add(new File([bytes], n, { type: "application/pdf" }));
      dt.items.add(new File(["hello"], "notes.txt", { type: "text/plain" }));
      const target = document.querySelector("nav").parentElement;
      for (const type of ["dragenter", "dragover", "drop"]) {
        target.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
      }
    },
    { b64, names },
  );
  await expect(page.getByText("อัปโหลดสำเร็จ 2 ไฟล์ · ไม่สำเร็จ 1 ไฟล์")).toBeVisible();
  await expect(page.getByTestId("message-details")).toContainText("notes.txt");
  for (const n of names) await expect(page.getByText(n.replace(/\.pdf$/, ""), { exact: false }).first()).toBeVisible();
});

test("อัปโหลดไฟล์ Word → แปลงเป็น PDF และเก็บเป็นไฟล์ .pdf ในเอกสารของฉัน", async ({ page }) => {
  await login(page);
  const name = `office-${stamp()}`;
  const buf = fs.readFileSync(SAMPLE_PDF.replace(/sample\.pdf$/, "sample.docx"));
  const mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  // เลือก 2 ไฟล์ = อัปโหลดเก็บไว้โดยไม่เปิด Editor
  await page.getByTestId("upload-input").setInputFiles([
    { name: `${name}-a.docx`, mimeType: mime, buffer: buf },
    { name: `${name}-b.docx`, mimeType: mime, buffer: buf },
  ]);
  await expect(page.getByText("อัปโหลดสำเร็จ 2 ไฟล์")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(`${name}-a`, { exact: false }).first()).toBeVisible();
  const res = await page.request.get("/api/pdf/files", {
    headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("token"))}` },
  });
  const files = (await res.json()).files.map((f) => f.filename);
  expect(files).toContain(`${name}-a.pdf`);
  expect(files).toContain(`${name}-b.pdf`);
});

test("หน้าคู่มือ: ดาวน์โหลดไฟล์ตัวอย่างเอกสารอัตโนมัติได้", async ({ page }) => {
  await page.goto("/manual.html#auto-gen-samples");
  const link = page.locator('a[href="/api/autogen/samples/template.docx"]');
  await expect(link).toBeVisible();
  const res = await page.request.get("/api/autogen/samples/data.json");
  expect(res.status()).toBe(200);
  expect(Array.isArray(await res.json())).toBe(true);
});

