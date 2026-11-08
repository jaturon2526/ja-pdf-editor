// Annotation (/annotation/{session})
import { BASE, fetchWithAuth, handle } from "./client.js";

export async function addAnnotation(sessionId, payload) {
  const res = await fetchWithAuth(`${BASE}/annotation/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

export async function listAnnotations(sessionId, pageNumber) {
  const ts = new Date().getTime();
  const res = await fetchWithAuth(`${BASE}/annotation/${sessionId}/page/${pageNumber}?_t=${ts}`, { cache: "no-store" });
  return handle(res);
}

export async function deleteAnnotation(sessionId, pageNumber, xref) {
  const res = await fetchWithAuth(`${BASE}/annotation/${sessionId}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_number: pageNumber, xref }),
  });
  return handle(res);
}

// แก้ไข annotation ที่มีอยู่แล้ว — ไฮไลท์ (ย่อ/ขยาย+เปลี่ยนสี), กรอบสี่เหลี่ยม/กล่องข้อความ (ย่อ/ขยาย+
// แก้ข้อความ+เปลี่ยนสี), โน้ต (แก้ข้อความ+เปลี่ยนสี) — ส่งเฉพาะฟิลด์ที่ต้องการเปลี่ยน คืน annotation
// ใหม่เสมอ (xref เปลี่ยน — ดู backend annotation_service.update_annotation)
export async function updateAnnotation(sessionId, payload) {
  const res = await fetchWithAuth(`${BASE}/annotation/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

// คำทั้งหมดในหน้า พร้อมตำแหน่ง+line_key — ใช้คำนวณตอนผู้ใช้ลากเลือกข้อความด้วยเมาส์
// (เครื่องมือไฮไลท์/โน้ต) ว่าครอบคำไหนบ้าง แล้ว snap เป็นกรอบทีละบรรทัด (ดู utils/textSelectionUtils.js)
export async function getWords(sessionId, pageNumber) {
  const ts = new Date().getTime();
  const res = await fetchWithAuth(`${BASE}/annotation/${sessionId}/page/${pageNumber}/words?_t=${ts}`, { cache: "no-store" });
  return handle(res);
}

// ---------- Text editing ----------
