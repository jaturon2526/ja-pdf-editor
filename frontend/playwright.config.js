// E2E test — รันกับระบบที่เปิดอยู่แล้ว (docker compose หรือ vite dev + backend)
//
//   1) สร้างผู้ใช้ทดสอบ (ครั้งเดียว) — ผู้ส่ง + ผู้ลงนาม 2 คนสำหรับ e2e/signing.spec.js:
//        for u in e2e@example.com e2e-signer1@example.com e2e-signer2@example.com; do
//          docker compose -f docker-compose.dev.yml exec backend python -m scripts.create_test_user $u 'E2e-Passw0rd!'; done
//   2) ติดตั้ง browser (ครั้งแรก):  npx playwright install chromium
//   3) รัน:  E2E_BASE_URL=http://localhost:8080 npm run test:e2e
//
// ตัวแปร: E2E_BASE_URL (ดีฟอลต์ http://localhost:8080), E2E_EMAIL, E2E_PASSWORD,
//         PW_CHROMIUM_PATH (ใช้ Chromium ที่ติดตั้งไว้แล้วแทนการดาวน์โหลด)
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:8080",
    viewport: { width: 1400, height: 850 },
    acceptDownloads: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1400, height: 850 },
        launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
      },
    },
  ],
});
