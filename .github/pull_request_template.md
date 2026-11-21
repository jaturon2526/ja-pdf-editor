## 1. เป้าหมายและสเป็ก (Intent & Spec Compliance)
- **สรุปสิ่งที่เปลี่ยน:** ...
- **อ้างอิงสเป็ก/แผน (ถ้ามี):** `docs/features/...`
- [ ] ทำงานครบตามขอบเขตที่ตกลง (`intent.md` / `spec.md`) และไม่กระทบส่วนที่อยู่นอกขอบเขต

## 2. ผลเทสต์อัตโนมัติ 3 ชั้น (Automated Tests)
- [ ] **Backend (`pytest -q`)**: เพิ่มเทสต์ครอบคลุม happy path, validation (400/403/404/409), และ undo/redo แล้ว
- [ ] **Frontend (`eslint` + `vitest` + `vite build`)**: ผ่านครบ 0 error
- [ ] **E2E (`playwright`)**: ผ่านทั้งมุมมองเดสก์ท็อป (`1400×850`) และมือถือ (`390×844`)

## 3. คุณภาพโค้ดและช่องโหว่ (Bug, Quality & Security Review)
- [ ] **SonarQube Quality Gate:** `PASSED` (ไม่มี floating promise S9383, nested ternary S3358, unused param S1172)
- [ ] **Security & Auth:** ตรวจสิทธิ์เจ้าของข้อมูล/เอกสารทุก endpoint, รองรับ CSRF cookie, ไม่มี inline script ที่ผิด CSP
- [ ] **Privacy & Secrets:** Fixture สร้างจากข้อมูลสมมติเท่านั้น (ไม่มีเอกสารจริง/ข้อมูลส่วนบุคคลจริง), ผ่าน `detect-secrets` และ `gitleaks`
- [ ] **Dependencies & License:** (ถ้ามีไลบรารีใหม่) lock hash ด้วย `scripts/lock-backend-deps.sh`, ผ่าน `pip-audit`, และเข้ากับ AGPL-3.0 ได้

## 4. เอกสาร เวอร์ชัน และความรู้ของทีม (Docs, Version & Team Memory)
- [ ] อัปเดต `APP_VERSION` ใน `frontend/src/components/AboutModal.jsx`
- [ ] อัปเดตคู่มือ `frontend/public/manual.html` และ build `frontend/public/manual.css` ใหม่แล้ว
- [ ] อัปเดต `README.md` (และ `.env*.template` / `THIRD_PARTY_LICENSES.md` ถ้าเกี่ยวข้อง)
- [ ] อัปเดต `CLAUDE.md` / `GEMINI.md` (พร้อมจดลงหมวด "กับดักที่ห้ามซ้ำ" หากพบปัญหาเรื่องเดิมซ้ำ 2 ครั้ง)
