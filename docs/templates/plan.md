# 3. Implementation Plan (แผนเขียนโค้ดและเทสต์) — `<ชื่อฟีเจอร์>` (vX.Y.Z)

> ใช้เช็กความคืบหน้าทีละขั้น และใช้เป็นเอกสาร Handoff ส่งต่องานข้ามเซสชันระหว่าง Claude กับ Gemini ได้ทันที

## 3.1 ลำดับงาน Backend
- [ ] สร้าง/แก้ไข service ใน `backend/app/services/...`
- [ ] เพิ่ม schema ใน `backend/app/models/schemas.py`
- [ ] เพิ่ม route ใน `backend/app/api/routes_...` (พร้อมตรวจสิทธิ์ + `push_history`)
- [ ] (ถ้ามี) สร้างสคริปต์สร้าง fixture ข้อมูลสมมติใน `backend/scripts/create_*_fixture.py` *(ห้ามใช้เอกสารจริงที่มีข้อมูลส่วนบุคคล)*

## 3.2 ลำดับงาน Frontend
- [ ] เพิ่มฟังก์ชันเรียก API ใน `frontend/src/api/...`
- [ ] สร้าง hook จัดการสถานะใน `frontend/src/hooks/...`
- [ ] สร้าง UI component / layer / panel ใน `frontend/src/components/...` (รองรับทั้ง `desk:` และ `phone:`)
- [ ] เชื่อมเข้ากับหน้าหลัก / เมนู (`editorMenus.js`) / แถบเครื่องมือ (`Toolbar.jsx`) / ประวัติ (`TOOLS_KEPT_ON_HISTORY`)

## 3.3 แผนการทดสอบ 3 ชั้น (Testing Plan)
- [ ] **Backend (`pytest -q`)**: `backend/tests/test_<feature>.py` (happy path, validation 400/403/404, undo/redo, edge cases) + รันทั้งชุดผ่าน
- [ ] **Frontend (`eslint` + `vitest` + `vite build`)**: `cd frontend && npx eslint src e2e && npx vitest run && npm run build`
- [ ] **E2E (`playwright`)**: `frontend/e2e/<feature>.spec.js`
  - [ ] ทดสอบบนเดสก์ท็อป (`1400×850`)
  - [ ] ทดสอบบนมือถือ (`390×844` — ระวังใช้ `img.page-image` แทน `.first()` และเปิดเมนูผ่านปุ่ม `"เมนูหลัก"`)

## 3.4 เอกสารและเวอร์ชัน (Documentation & Version Checklist)
- [ ] `frontend/src/components/AboutModal.jsx` → อัปเดต `APP_VERSION = "vX.Y.Z"` (และ `OSS_CREDITS` ถ้ามีไลบรารีใหม่)
- [ ] `frontend/public/manual.html` → เพิ่มใน "✨ มีอะไรใหม่" + เนื้อหาคู่มือ แล้ว build CSS:
      `cd frontend && npx -y @tailwindcss/cli@4 -i manual.tailwind.css -o public/manual.css --minify`
- [ ] `README.md` (และ `.env*.template` ถ้ามีตัวแปรแวดล้อมใหม่)
- [ ] `CLAUDE.md` และ `GEMINI.md` (สรุปฟีเจอร์ + จดบทเรียนหากติดกับดักซ้ำ 2 ครั้ง)

## 3.5 ตรวจคุณภาพและส่งงาน (Quality Gate & Ship)
- [ ] ตรวจจุดเสี่ยง SonarQube (ไม่มี floating promise `void`, ไม่มี nested ternary, ไม่มีพารามิเตอร์เกิน, ปิด resource ใน `try/finally`)
- [ ] สแกน SonarQube ผ่าน (`QUALITY GATE STATUS: PASSED`)
- [ ] Pre-commit ผ่าน (`detect-secrets`, `end-of-file-fixer`)
- [ ] สร้าง bundle จาก commit ใน `main` (`git bundle create <name>.bundle <main-sha>..<branch>`) + อัปเดต `ship-now.command` และ `sonar-scan-bundle.command` (`chmod 755`) + สลับกลับ `main`
