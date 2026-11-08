# JA PDF Editor — Frontend (React + Vite)

หน้าเว็บของ JA PDF Editor: หน้าเอกสารของฉัน (Dashboard), Editor, งานลงนาม, บัญชีผู้ใช้, ผู้ดูแลระบบ และคู่มือผู้ใช้
(ภาพรวมทั้งระบบดู [`../README.md`](../README.md))

## รันในเครื่อง

```bash
cd frontend
npm install
cp .env.template .env      # ไม่บังคับ — ปุ่ม Google/LINE และการสมัครอ่านจาก backend (GET /api/config/public)
npm run dev
```

เปิด `http://localhost:5173` — คำขอ `/api/*` ถูก proxy ไปที่ `http://localhost:8001` (backend ของ `docker-compose.dev.yml`)
โดยตัด `/api` ออก (ตั้งค่าใน `vite.config.js`) · ถ้ารัน backend เองนอก Docker ให้ใช้ `uvicorn app.main:app --port 8001`
· production: nginx ใน `nginx.conf` ทำ rewrite แบบเดียวกัน — แก้ที่หนึ่งต้องแก้อีกที่ให้ตรงกัน

## ทดสอบ

```bash
npm run lint          # ESLint
npm test              # Vitest — src/**/*.test.js(x)
npm run build         # ตรวจว่า build ผ่าน
npm run test:e2e      # Playwright กับระบบที่รันอยู่ (ดีฟอลต์ http://localhost:8080 — ดูหัว playwright.config.js)
```

E2E ต้องมีผู้ใช้ทดสอบ (ผู้ส่ง + ผู้ลงนาม 2 คน) — คำสั่งสร้างอยู่ที่หัว `playwright.config.js` (CI ทำให้เอง)

## โครงสร้าง

```
frontend/
├── index.html            # โหลดฟอนต์ (Inter + Noto Sans Thai, Sarabun/Kanit สำหรับเอกสาร)
├── vite.config.js        # proxy /api → localhost:8001, ตั้งค่า vitest
├── nginx.conf            # production: เสิร์ฟ SPA + proxy /api → backend:8000
├── public/
│   ├── manual.html       # คู่มือผู้ใช้ — อัปเดตทุกครั้งที่เพิ่ม/เปลี่ยนฟีเจอร์
│   └── images/manual/    # รูปประกอบคู่มือ
├── e2e/                  # Playwright (+ fixtures/)
└── src/
    ├── main.jsx, App.jsx # router
    ├── pages/            # Dashboard, Editor, Signing*, Login, Profile, Security, AIConfig, Upgrade, Admin, ...
    ├── components/       # MenuBar/Toolbar/Sidebar/PDFCanvas, modals, dashboard/, editor/, signature/
    ├── hooks/            # useSession, useTextEdit, useAnnotation, useRedact, useDocumentHistory, ...
    ├── api/              # เรียก backend แยกตามหมวด (client.js จัดการ token/ข้อผิดพลาด) — api.js รวม export
    ├── utils/            # textSelectionUtils (ลากเลือก/คัดลอกข้อความไทย), viewport, format, ...
    ├── __tests__/        # Vitest
    ├── styles.css        # design tokens + layout หลัก (ฟอนต์หน้าจอ --font-ui)
    └── tailwind.css
```

## ข้อตกลงที่ใช้ในโค้ด

- ทุกคำขอไป backend ผ่าน `src/api/*` ไม่เรียก `fetch` ตรง ๆ ในคอมโพเนนต์
- React 18 StrictMode เรียก updater ของ `setState(prev => …)` สองครั้งตอน dev — ห้ามใส่ side effect (เรียก API ฯลฯ) ในนั้น
- การลาก (ย้าย/ปรับขนาด/เลือกพื้นที่) ใช้ `onPointerDown` + `window.addEventListener("pointermove"/"pointerup")`
- ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย · นามสกุลไฟล์ Office ที่รับต้องตรงกับ `OFFICE_EXTS` ใน `backend/app/api/pdf/files.py`
