# 2. Specification (ออกแบบระบบ) — `<ชื่อฟีเจอร์>` (vX.Y.Z)

## 2.1 ประสบการณ์ผู้ใช้และหน้าจอ (UX / UI Flow)
- **จุดเข้าใช้งาน (Entry point):** เมนู ... / ปุ่มแถบเครื่องมือ ...
- **มุมมองเดสก์ท็อป (`1400×850`):** ...
- **มุมมองมือถือ (`390×844` / `phone:` variant):** (เช่น เปิดจากปุ่ม `เมนูหลัก`, แสดงเป็น bottom sheet ไม่บังพื้นที่ทำงานหลัก, รองรับการลากด้วยนิ้ว `touch-none`)
- **การใช้งานด้วยคีย์บอร์ด / Accessibility:** (เช่น `aria-label`, ปุ่มลูกศร, `Escape` เพื่อปิด)

## 2.2 API Endpoints & Schemas (Backend)
- `GET /api/...`
  - **Response:** `{ ... }`
- `POST /api/...`
  - **Request (`schemas.py`):** `{ ... }`
  - **Response:** `{ ... }`
  - **Error cases:** `400` (ข้อมูลไม่ถูกต้อง), `403/404` (ไม่ใช่เจ้าของเอกสาร/ไม่พบ), `409` (ข้อมูลชนกัน), `429` (เกิน rate limit)

## 2.3 โครงสร้างข้อมูลและสถานะ (Data Model / Session / Redis)
- **Database Migration (Alembic):** มี / ไม่มี (ถ้าระบุหมายเลข migration และการรองรับ rollback)
- **Session / History (`push_history`):** รองรับ Undo / Redo หรือไม่ · กระทบ `text_edits` หรือ render cache อย่างไร
- **งานหนัก (`heavy_slot`):** ต้องครอบด้วย `heavy_slot` หรือไม่ (กรณีเรียก Ghostscript / LibreOffice / Tesseract)

## 2.4 ความปลอดภัยและสัญญาอนุญาต (Security & Licensing)
- **Authentication / Authorization:** ตรวจเจ้าของเอกสาร/ข้อมูลทุกจุด + รองรับ CSRF cookie
- **Rate Limit:** ต้องจำกัดความถี่หรือไม่
- **CSP (`frontend/security-headers.conf`):** ห้ามมี inline script/handler
- **ไลบรารีใหม่:** ไม่มี / มี (ต้องเข้ากับ AGPL-3.0 ได้ และเพิ่มใน `THIRD_PARTY_LICENSES.md` + `AboutModal.jsx`)

## 2.5 กรณีขอบและข้อจำกัดที่ยอมรับได้ (Edge Cases & Known Limitations)
- หน้าที่หมุน (rotated page): ...
- เอกสารที่เข้ารหัสหรือเซ็นดิจิทัลแล้ว: ...
- ข้อจำกัดที่ควรแจ้งผู้ใช้ในคู่มือ: ...
