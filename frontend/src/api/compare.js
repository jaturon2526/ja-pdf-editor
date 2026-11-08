// เปรียบเทียบเอกสาร (backend: app/api/routes_compare.py)
import { BASE, fetchBlob, fetchWithAuth, handle } from "./client.js";

/** side = { fileId, version: "current"|"previous" } | { sessionId, version?: "saved"|"previous" } | { file: File } */
function appendSide(form, prefix, side) {
  if (!side) return;
  if (side.file) form.append(`${prefix}_upload`, side.file, side.file.name);
  else if (side.sessionId) {
    form.append(`${prefix}_session_id`, side.sessionId);
    if (side.version) form.append(`${prefix}_version`, side.version); // "saved" | "previous" ของไฟล์ที่เปิดอยู่
  }
  else if (side.fileId != null) {
    form.append(`${prefix}_file_id`, String(side.fileId));
    if (side.version) form.append(`${prefix}_version`, side.version);
  }
}

export async function startCompare(a, b, options = {}) {
  const form = new FormData();
  appendSide(form, "a", a);
  appendSide(form, "b", b);
  for (const [k, v] of Object.entries(options)) form.append(k, v ? "true" : "false");
  return handle(await fetchWithAuth(`${BASE}/compare`, { method: "POST", body: form }));
}

export async function getCompare(taskId) {
  return handle(await fetchWithAuth(`${BASE}/compare/${taskId}`));
}

export async function deleteCompare(taskId) {
  return handle(await fetchWithAuth(`${BASE}/compare/${taskId}`, { method: "DELETE" }));
}

/** ภาพหน้า (JPEG) เป็น object URL — ผู้เรียกต้อง URL.revokeObjectURL เอง */
export async function comparePageUrl(taskId, side, page, zoom) {
  const { blob } = await fetchBlob(`${BASE}/compare/${taskId}/page/${side}/${page}?zoom=${zoom}`);
  return URL.createObjectURL(blob);
}

export async function downloadCompareReport(taskId) {
  return fetchBlob(`${BASE}/compare/${taskId}/report`, "compare-report.pdf");
}
