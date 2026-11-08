// ไฟล์ของผู้ใช้ (Dashboard): upload/merge/convert, เปิด/บันทึก/คัดลอก/ลบ/เปลี่ยนชื่อ, PDF→Word, Auto-Gen
import { BASE, fetchBlob, fetchWithAuth, getToken, handle } from "./client.js";

export async function getMyFiles() {
  const res = await fetchWithAuth(`${BASE}/pdf/files`);
  return handle(res);
}

export async function uploadOffice(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithAuth(`${BASE}/pdf/convert-office`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "อัปโหลดและแปลงไฟล์ไม่สำเร็จ");
  }
  return res.json();
}

export async function uploadPdf(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithAuth(`${BASE}/pdf/upload`, { method: "POST", body: form });
  return handle(res);
}

/** รวม PDF — items: File (จากเครื่อง) หรือ {kind: "local", file} / {kind: "stored", id} (ไฟล์ในเอกสารของฉัน) ตามลำดับที่ต้องการ */
export async function mergePdfs(items) {
  const form = new FormData();
  const order = [];
  const ids = [];
  let u = 0;
  for (const it of items) {
    if (it instanceof Blob || it.kind === "local") {
      form.append("files", it instanceof Blob ? it : it.file);
      order.push(`u${u++}`);
    } else {
      ids.push(it.id);
      order.push(`f${it.id}`);
    }
  }
  form.append("file_ids", ids.join(","));
  form.append("order", order.join(","));
  const res = await fetchWithAuth(`${BASE}/pdf/merge`, { method: "POST", body: form });
  return handle(res);
}

export async function openFile(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/open`, { method: "POST" });
  return handle(res);
}

export async function deleteFile(fileId) {
  const res = await fetchWithAuth(`${BASE}/pdf/files/${fileId}`, {
    method: "DELETE"
  });
  return handle(res);
}

export async function saveToServer(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/save`, {
    method: "POST"
  });
  return handle(res);
}

function conversionTarget(target) {
  const { fileId, sessionId } = typeof target === "object" && target !== null ? target : { fileId: target };
  return sessionId ? { session_id: sessionId } : { file_record_id: fileId };
}

function jsonAuthHeaders() {
  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

// target: { fileId } ไฟล์ในเอกสารของฉัน หรือ { sessionId } เอกสารที่เปิดใน Editor (ต้องบันทึกก่อน)
// mode: "editable" (ค่าเดิม), "layout" (รักษาหน้าตาต้นฉบับ) หรือ "scan" (ไฟล์สแกน อ่านด้วย OCR)
// useAi: เฉพาะไฟล์สแกน — ให้ AI แก้คำไทยที่ OCR อ่านผิด (ใช้โควต้า AI)
export async function startConversionAsync(target, mode = "editable", { useAi = false } = {}) {
  const res = await fetch(`${BASE}/convert/pdf-to-word/async`, {
    method: "POST",
    headers: jsonAuthHeaders(),
    body: JSON.stringify({ ...conversionTarget(target), mode, use_ai: useAi }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "ไม่สามารถเริ่มงานแปลงไฟล์ได้");
  }
  return res.json();
}

// ไฟล์นี้เป็นไฟล์สแกนไหม → { scanned, pages, max_pages }
export async function inspectConversion(target) {
  const res = await fetch(`${BASE}/convert/pdf-to-word/inspect`, {
    method: "POST",
    headers: jsonAuthHeaders(),
    body: JSON.stringify(conversionTarget(target)),
  });
  if (!res.ok) throw new Error("ตรวจไฟล์ไม่สำเร็จ");
  return res.json();
}

export async function checkConversionStatus(taskId) {
  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  
  const res = await fetch(`${BASE}/convert/pdf-to-word/status/${taskId}`, { headers });
  if (!res.ok) throw new Error("ไม่สามารถอ่านสถานะได้");
  return res.json();
}

export async function downloadConversionResult(taskId) {
  const token = localStorage.getItem("token") || sessionStorage.getItem("token");
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  
  const res = await fetch(`${BASE}/convert/pdf-to-word/download/${taskId}`, { headers });
  if (!res.ok) throw new Error("ดาวน์โหลดไฟล์ไม่สำเร็จ");
  return res.blob();
}

// ---------- Auto-Gen (ต้อง login) ----------
export function autogenPreview(formData) {
  return fetchWithAuth(`${BASE}/autogen/preview`, { method: "POST", body: formData });
}

export function autogenGenerate(formData) {
  return fetchWithAuth(`${BASE}/autogen/`, { method: "POST", body: formData });
}

// pdfVersion: null = ไม่เปลี่ยนเวอร์ชัน, "1.4" | "1.5" | "1.6" | "1.7" | "2.0" = แปลงให้ตรงมาตรฐานเวอร์ชันนั้น
export async function saveAsCopy(sessionId, newFilename, pdfVersion = null) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/save-as-copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: newFilename, pdf_version: pdfVersion || undefined }),
  });
  return handle(res);
}

export async function renameFile(fileId, newFilename) {
  const res = await fetchWithAuth(`${BASE}/pdf/files/${fileId}/rename`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: newFilename })
  });
  return handle(res);
}

// ไฟล์นี้มีลายเซ็นดิจิทัลแล้วหรือยัง — {signed: true|false|null, count}
export async function getFileSignatureStatus(fileId) {
  return handle(await fetchWithAuth(`${BASE}/pdf/files/${fileId}/signature-status`));
}

// ใส่ลายน้ำ / เซ็นเซอร์ด้วยคำค้นหา จาก Dashboard → ได้ไฟล์ใหม่ (ไฟล์เดิมไม่ถูกแก้)
// ไฟล์ที่มีรหัสผ่าน: error.status === 423 (ต้องส่ง password มาด้วย)
export async function quickFileAction(fileId, body) {
  const res = await fetchWithAuth(`${BASE}/pdf/files/${fileId}/quick-action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 423) {
    const data = await res.json().catch(() => ({}));
    throw Object.assign(new Error(data.detail || "ไฟล์นี้มีรหัสผ่าน"), { status: 423 });
  }
  return handle(res);
}

// ดาวน์โหลดไฟล์เวอร์ชันที่บันทึกไว้ (เมนู ☰ บน Dashboard) — คืน {blob, filename}
export async function downloadStoredFile(fileId, fallbackName = "document.pdf") {
  return fetchBlob(`${BASE}/pdf/files/${fileId}/download`, fallbackName);
}

// คุณสมบัติเอกสารของไฟล์ที่บันทึกไว้ — ไฟล์มีรหัสผ่าน: error.status === 423
export async function getStoredFileProperties(fileId, password = null) {
  const res = await fetchWithAuth(`${BASE}/pdf/files/${fileId}/properties`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (res.status === 423) {
    const data = await res.json().catch(() => ({}));
    throw Object.assign(new Error(data.detail || "ไฟล์นี้มีรหัสผ่าน"), { status: 423 });
  }
  return handle(res);
}

// PDPA จาก Dashboard: สแกนไฟล์ที่บันทึกไว้ (ไม่แก้ไฟล์) — ไฟล์มีรหัสผ่าน: error.status === 423
// แล้วส่ง id ที่เลือกไปที่ quickFileAction(fileId, {action: "pdpa", pii_ids, clean_metadata, password})
export async function scanStoredFilePii(fileId, password = null) {
  const res = await fetchWithAuth(`${BASE}/pdf/files/${fileId}/pii-scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (res.status === 423) {
    const data = await res.json().catch(() => ({}));
    throw Object.assign(new Error(data.detail || "ไฟล์นี้มีรหัสผ่าน"), { status: 423 });
  }
  return handle(res);
}

// สแกนเอกสาร: ส่งภาพทุกหน้า (เรียงตามลำดับ) → งานเบื้องหลังสร้าง PDF + OCR — ดู backend api/pdf/scan.py
export async function createScan(filename, blobs, onUploadProgress, ocrBlobs = []) {
  const form = new FormData();
  form.append("filename", filename);
  const ext = (b) => (b.type === "image/png" ? "png" : "jpg");
  blobs.forEach((b, i) => form.append("pages", b, `page-${String(i + 1).padStart(3, "0")}.${ext(b)}`));
  // ภาพสำหรับอ่านข้อความ (ไม่บังคับ) — ชื่อไฟล์ระบุหน้าที่ (เริ่ม 1) หน้าที่ไม่มีใช้ภาพหน้าเอง
  ocrBlobs.forEach((b, i) => b && form.append("ocr_pages", b, `ocr-${String(i + 1).padStart(3, "0")}.${ext(b)}`));
  if (!onUploadProgress) {
    const res = await fetchWithAuth(`${BASE}/pdf/scan`, { method: "POST", body: form });
    return handle(res);
  }
  // XHR เพื่อแสดงความคืบหน้าการอัปโหลด (fetch ยังไม่มี upload progress)
  const token = getToken();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/pdf/scan`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onUploadProgress(e.loaded / e.total); };
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* ไม่ใช่ JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body?.detail || `อัปโหลดไม่สำเร็จ (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("อัปโหลดไม่สำเร็จ — ตรวจสอบการเชื่อมต่ออินเทอร์เน็ต"));
    xhr.send(form);
  });
}

export async function getScanStatus(taskId) {
  const res = await fetchWithAuth(`${BASE}/pdf/scan/status/${taskId}`);
  return handle(res);
}
