// api.js — จุดรวม API ทั้งหมด (โค้ดเดิม import * as api from "../api.js" ใช้ต่อได้เหมือนเดิม)
// ตัวจริงแยกตามหมวดอยู่ใน src/api/*.js — เพิ่ม endpoint ใหม่ในไฟล์หมวดที่ตรงกัน
// ระหว่าง dev เรียกผ่าน /api ซึ่ง vite proxy ไปยัง backend (ดู vite.config.js)
export * from "./api/client.js";
export * from "./api/auth.js";
export * from "./api/files.js";
export * from "./api/document.js";
export * from "./api/annotation.js";
export * from "./api/edit.js";
export * from "./api/signature.js";
export * from "./api/admin.js";
export * from "./api/signing.js";
export * from "./api/passkey.js";
export * from "./api/line.js";
export * from "./api/config.js";
export * from "./api/compare.js";
