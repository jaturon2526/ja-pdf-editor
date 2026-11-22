// เอกสารที่เปิดอยู่ (/pdf/{session}): render, unlock, undo/redo, หน้า, bookmark, รหัสผ่าน, redact, OCR, ดาวน์โหลด
import { BASE, fetchWithAuth, handle, fetchBlob, saveBlob, filenameFromDisposition } from "./client.js";

export async function unlockPdf(sessionId, password) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/unlock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return handle(res);
}

export async function compressPdf(sessionId, profile) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/compress`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile }),
  });
  return handle(res);
}

export async function flattenPdf(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/flatten`, {
    method: "POST",
  });
  return handle(res);
}

export async function getInfo(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/info`);
  return handle(res);
}

// จัดการรหัสผ่าน (เมนู File > เข้ารหัส PDF / ลบรหัสผ่าน — ผู้ใช้แจ้งขอ) ดู backend
// routes_pdf.add_password/remove_password — cืน {status, is_password_protected} ให้ frontend อัปเดต
// state ของเมนู File ทันทีโดยไม่ต้องเรียก getInfo ซ้ำ
// encryption: "aes256" (แนะนำ) | "aes128" (โปรแกรมรุ่นเก่า — รหัสผ่านต้องเป็นอักษรละติน)
export async function addPassword(sessionId, password, encryption = "aes256") {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/add-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, encryption }),
  });
  return handle(res);
}

export async function removePassword(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/remove-password`, { method: "POST" });
  return handle(res);
}

/** ความละเอียดที่เรนเดอร์เพิ่มตามจอ (Retina/มือถือ 2–3 เท่า) — จำกัดไว้ 2 เท่า (ขนาดไฟล์รูป ×4) */
export function renderPixelRatio() {
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  return Math.min(2, Math.max(1, dpr));
}

export async function renderPage(sessionId, pageNumber, zoom) {
  // ป้องกันเบราว์เซอร์แคชรูปหน้าเดิม ทำให้หน้าจอไม่ยอมอัปเดตเวลามีการแก้ไข annotation 
  const ts = new Date().getTime();
  // เรนเดอร์ละเอียดตามจอ แต่แสดงที่ขนาด หน้า×ซูม (PDFCanvas ตั้งความกว้างรูปเอง) — เดิมตัวหนังสือเบลอบนมือถือ
  const renderZoom = Math.round(Math.min(8, zoom * renderPixelRatio()) * 1000) / 1000;
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/page/${pageNumber}?zoom=${renderZoom}&_t=${ts}`, {
    cache: "no-store",
    headers: {
      "Pragma": "no-cache",
      "Cache-Control": "no-cache"
    }
  });
  return handle(res);
}

// ---------- ดาวน์โหลดไฟล์ที่ต้องยืนยันตัวตน ----------
// endpoint ของ session ทุกตัวต้องแนบ Authorization header (ดู backend app/api/deps.get_owned_session)
// จึงเปิดด้วย window.open(url) / <img src={url}> ตรงๆ ไม่ได้อีกต่อไป ต้องดึงเป็น Blob ผ่าน fetchWithAuth
// แล้วค่อยสร้าง object URL หรือสั่งบันทึกไฟล์เอง

// ไฟล์ PDF ปัจจุบันของ session เป็น Blob (inline=true สำหรับพิมพ์/เปิดดู)
export function fetchPdfBlob(sessionId, { inline = false } = {}) {
  return fetchBlob(`${BASE}/pdf/${sessionId}/download${inline ? "?inline=true" : ""}`, "document.pdf");
}

// PDF สำหรับพิมพ์ "ตามที่เห็นบนจอ" (หน้าที่หมุนแล้วไม่กลับหัว — ดู backend pdf_service.build_print_pdf)
export function fetchPrintBlob(sessionId, layout = "as_shown") {
  return fetchBlob(`${BASE}/pdf/${sessionId}/print?layout=${layout}`, "print.pdf");
}

export async function downloadPdf(sessionId) {
  const { blob, filename } = await fetchPdfBlob(sessionId);
  saveBlob(blob, filename);
}

// URL ดาวน์โหลดเฉพาะหน้าที่เลือกเป็นไฟล์ PDF ใหม่ (ผู้ใช้แจ้งขอ: เลือกหลายหน้าในแผงเอกสารซ้าย คลิกขวา
// ส่งออก) pageNumbers เป็น array เลขหน้า 0-based — ต่อเป็น query string คั่นด้วยจุลภาคให้ backend
// (ดู backend app/api/pdf/document.export_pages) ดึงผ่าน fetchWithAuth แล้วบันทึกเป็นไฟล์
export async function exportPages(sessionId, pageNumbers) {
  const { blob, filename } = await fetchBlob(
    `${BASE}/pdf/${sessionId}/export-pages?pages=${pageNumbers.join(",")}`,
    "pages.pdf",
  );
  saveBlob(blob, filename);
}

// keepalive: ส่งได้แม้หน้ากำลังปิด/รีเฟรช (pagehide) — sendBeacon ใส่ header Authorization ไม่ได้
export async function closeSession(sessionId, { keepalive = false } = {}) {
  await fetchWithAuth(`${BASE}/pdf/${sessionId}`, { method: "DELETE", keepalive });
}

// เลิกทำ/ทำซ้ำ (Undo/Redo) — ย้อน/เดินหน้าเอกสารทั้งฉบับหนึ่งขั้น ครอบคลุมทั้ง annotation และการแก้ไข
// ข้อความ/รูปภาพ (ดู backend app/core/session.py หมายเหตุ Undo/Redo) คืน {status, can_undo, can_redo}
export async function undo(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/undo`, { method: "POST" });
  return handle(res);
}

export async function redo(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/redo`, { method: "POST" });
  return handle(res);
}

// ย้ายตำแหน่งหน้าจริงในเอกสาร (ผู้ใช้แจ้งขอจากแผงหน้าเอกสารด้านซ้าย: กดเมาส์ค้างที่ thumbnail แล้วลากไป
// วาง หรือคลิกขวา > เลื่อนหน้าขึ้น/ลง) pageNumbers เป็น array เลขหน้า 0-based ที่จะย้าย (อาจมากกว่า 1 หน้า
// ถ้าเลือกไว้หลายหน้า) — ระบุปลายทางได้ 2 แบบ (ดู backend routes_pdf.reorder_pages /
// models.ReorderPagesRequest — ส่งมาอย่างใดอย่างหนึ่งเท่านั้น): targetPage (แทรกก่อนหน้าเลขนี้ นับตาม
// ลำดับเดิมก่อนย้าย ใช้ตอนลากวาง — ไม่ส่ง/undefined แปลว่าวางท้ายสุด) หรือ direction ("up"/"down" ใช้ตอน
// คลิกขวาเลื่อนขึ้น/ลงทีละ 1 ตำแหน่ง) คืน {status: "ok"|"no_change", page_count}

export async function deletePages(sessionId, pageNumbers) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/pages`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_numbers: pageNumbers }),
  });
  return handle(res);
}

export async function rotatePages(sessionId, pageNumbers, angle) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/pages/rotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_numbers: pageNumbers, angle }),
  });
  return handle(res);
}

export async function reorderPages(sessionId, pageNumbers, { targetPage, direction } = {}) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/reorder-pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page_numbers: pageNumbers,
      target_page: targetPage ?? null,
      direction: direction ?? null,
    }),
  });
  return handle(res);
}

// Bookmark — ผูกกับ PDF outline/TOC จริงของเอกสาร (ผู้ใช้แจ้งบั๊ก: bookmark หายหลังกด Save แล้ว
// Download แล้วเปิดไฟล์ใหม่ เพราะของเดิมเก็บเป็น React state ฝั่ง frontend ล้วนๆ ไม่เคยลงไปอยู่ในไฟล์
// จริงเลย) ดู backend routes_pdf.get_bookmarks/set_bookmarks — setBookmarks ส่ง "ทั้งชุด" ที่ต้องการ
// ไปแทนของเดิมเสมอ (ไม่ใช่ add/remove ทีละรายการ) แล้วต้องใช้ค่าที่ backend คืนกลับมาอัปเดต state เสมอ
// (ไม่ใช่ค่าที่ตัวเองส่งไป) คืน {bookmarks: [{page, label}, ...]}
export async function getBookmarks(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/bookmarks`);
  return handle(res);
}

export async function setBookmarks(sessionId, bookmarks) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/bookmarks`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bookmarks }),
  });
  return handle(res);
}

// คุณสมบัติเอกสาร (Document Properties) แบบเดียวกับ Acrobat Reader (ผู้ใช้แจ้งขอ — เมนู File และปุ่มบน
// toolbar) ดู backend routes_pdf.get_document_properties / pdf_service.get_document_properties —
// หลายฟิลด์อาจเป็น null ได้ตามข้อจำกัดของไฟล์แต่ละไฟล์ (frontend แสดง "-"/"ไม่ทราบ" แทน)
export async function getDocumentProperties(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/properties`);
  return handle(res);
}

export async function redactAreaBatch(sessionId, pageNumber, rects) {
  const res = await fetchWithAuth(`/api/pdf/${sessionId}/redact_batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pageNumber, rects }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || data.error || "Failed to redact areas");
  }
  return res.json();
}

export async function redactArea(sessionId, pageNumber, rect) {
  const res = await fetchWithAuth(`/api/pdf/${sessionId}/redact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pageNumber, rect }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || data.error || "Failed to redact area");
  }
  return res.json();
}

export async function extractTextOCR(sessionId, pageNumber, rect) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/extract_text_ocr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_number: pageNumber, rect }),
  });
  const data = await handle(res);
  return data.text;
}

export async function redactAllPagesBatch(sessionId, rects) {
  return fetchWithAuth(`${BASE}/pdf/${sessionId}/redact-all-pages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rects }),
  }).then(res => {
     if(!res.ok) throw new Error("Batch redact failed");
     return res.json();
  });
}

// แยกหน้าเอกสาร — คืน { blob, filename } ชื่อไฟล์จาก server เช่น "สัญญา (หน้า 1-3).pdf" / "สัญญา (แยก 3 หน้า).zip"
// format: "pdf" | "png" | "jpg" (รูปหน้าละไฟล์ — หน้าเดียวได้ไฟล์รูป หลายหน้าได้ .zip) · dpi 100/150/300 เฉพาะรูป
export async function extractPages(sessionId, pageRange, mode, format = "pdf", dpi = 150) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_range: pageRange, mode, format, dpi }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "แยกหน้าเอกสารไม่สำเร็จ");
  }
  const blob = await res.blob();
  const fallback = format !== "pdf" ? `page.${format}` : mode === "split" ? "pages.zip" : "pages.pdf";
  return { blob, filename: filenameFromDisposition(res.headers.get("Content-Disposition"), fallback) };
}

// PDPA — ตรวจหาข้อมูลส่วนบุคคล (ทำบนเซิร์ฟเวอร์ ไม่ส่งออกภายนอก) → {findings, pages_without_text, page_count}
export async function scanPii(sessionId) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/pii/scan`, { method: "POST" });
  return handle(res);
}

// ปิดทับถาวรเฉพาะรายการที่เลือก → {redacted, report: [{type,label,page,masked}], metadata_cleaned}
// เอกสารเปลี่ยนหลังสแกน → error.status === 409
export async function redactPii(sessionId, ids, cleanMetadata = false) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/pii/redact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, clean_metadata: cleanMetadata }),
  });
  if (res.status === 409) {
    const data = await res.json().catch(() => ({}));
    throw Object.assign(new Error(data.detail || "เอกสารเปลี่ยนแปลงหลังสแกน"), { status: 409 });
  }
  return handle(res);
}

// อ่านข้อความในรูปภาพ (OCR) แล้ววางเป็นข้อความล่องหน — ค้นหา/เซ็นเซอร์/คัดลอกข้อความในรูปได้ (backend: pdf_service.ocr)
export async function addOcrTextLayer(sessionId, pages = null) {
  const res = await fetchWithAuth(`${BASE}/pdf/${sessionId}/ocr-text-layer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pages ? { pages } : {}),
  });
  return handle(res);
}

// ---------- แทรกหน้า (v1.39.0) ----------
// ไฟล์ต้นทาง → session ชั่วคราว (ไม่บันทึกในเอกสารของฉัน) · ใช้ renderPage/unlockPdf/closeSession กับ session นี้ได้ตามปกติ
export async function createInsertSource(file) {
  const form = new FormData();
  form.append("file", file);
  return handle(await fetchWithAuth(`${BASE}/pdf/insert-source`, { method: "POST", body: form }));
}

export async function createInsertSourceFromFile(fileId) {
  return handle(await fetchWithAuth(`${BASE}/pdf/insert-source/from-file/${fileId}`, { method: "POST" }));
}

// body: { position, source_session_id, pages } หรือ { position, blank: { count, width, height } }
export async function insertPages(sessionId, body) {
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/pages/insert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

// ค้นหาข้อความทุกหน้าในเอกสาร (Ctrl+F, v1.42.0) → { query, total, truncated, matches: [{ index, page, rects }] }
export async function searchPdfText(sessionId, query, { matchCase = false } = {}) {
  const params = new URLSearchParams({ q: query, match_case: String(!!matchCase) });
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/search?${params.toString()}`));
}

// ตัดขอบหน้ากระดาษ (Crop Page, v1.44.0) → { status: "ok" | "no_change", cropped_pages }
export async function cropPages(sessionId, { pageNumbers, leftPt, topPt, rightPt, bottomPt }) {
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/pages/crop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page_numbers: pageNumbers,
      left_pt: leftPt,
      top_pt: topPt,
      right_pt: rightPt,
      bottom_pt: bottomPt,
    }),
  }));
}

// กรอกแบบฟอร์ม PDF (AcroForm, v1.45.0) → { total, fields: [...] }
export async function getFormFields(sessionId) {
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/forms`));
}

// บันทึกค่าลงช่องแบบฟอร์ม AcroForm → { status: "ok" | "no_change", updated }
export async function fillFormFields(sessionId, updates) {
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/forms/fill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  }));
}

// สร้างเอกสาร PDF หน้าเปล่า (v1.47.0) → UploadResponse ({ session_id, filename, page_count, page_sizes })
export async function createBlankPdf({ filename, width = 595, height = 842, pageCount = 1 }) {
  return handle(await fetchWithAuth(`${BASE}/pdf/blank`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename,
      width,
      height,
      page_count: pageCount,
    }),
  }));
}

// เพิ่มช่องกรอกแบบฟอร์ม AcroForm ใหม่ลงหน้าเอกสาร (v1.47.0) → { status, field }
export async function addFormField(sessionId, { page, type, name = "", label = "", rect, multiline = false, options = [] }) {
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/forms/fields`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page, type, name, label, rect, multiline, options }),
  }));
}

// ย้ายตำแหน่งหรือปรับขนาดช่องกรอกแบบฟอร์ม AcroForm ที่วางไว้แล้ว (v1.47.3) → { status, field }
export async function updateFormField(sessionId, xref, { page, rect, label = null }) {
  const body = label ? { page, rect, label } : { page, rect };
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/forms/fields/${xref}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

// ลบช่องกรอกแบบฟอร์ม AcroForm (v1.47.0) → { status }
export async function deleteFormField(sessionId, xref, page = 0) {
  return handle(await fetchWithAuth(`${BASE}/pdf/${sessionId}/forms/fields/${xref}?page=${page}`, {
    method: "DELETE",
  }));
}
