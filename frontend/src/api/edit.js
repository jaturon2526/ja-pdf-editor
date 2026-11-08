// แก้ไขข้อความ/รูปภาพ/ฟอนต์/ลายน้ำ (/edit)
import { BASE, fetchWithAuth, handle, fetchBlob } from "./client.js";

export async function getFonts() {
  const res = await fetchWithAuth(`${BASE}/edit/fonts`);
  return handle(res);
}

// รายชื่อฟอนต์จัดกลุ่มเป็น "1 family เลือกสไตล์ regular/bold/italic/bold_italic ได้" (ผู้ใช้แจ้งขอเพิ่ม
// — เดิม GET /edit/fonts คืนมาแบบ flat เห็นเป็นหลาย option แยกกัน เช่น "Sarabun"/"Sarabun Bold"/
// "Sarabun Italic" คนละแถวกัน) ใช้กับ properties panel ตอนแก้ไขข้อความ (เลือก family แล้วกดปุ่มสไตล์)
// และ InstallFontModal (โชว์/ลบฟอนต์ที่ติดตั้งเองเป็นกลุ่ม ไม่ใช่ทีละไฟล์) — ดู backend
// routes_edit.list_font_families / fonts.list_font_families
export async function getFontFamilies() {
  const res = await fetchWithAuth(`${BASE}/edit/font-families`);
  return handle(res);
}

// จัดการฟอนต์ที่ติดตั้งเอง (เมนู File > ติดตั้งฟอนต์ใหม่... — ผู้ใช้แจ้งขอ กรณีมีฟอนต์ที่ซื้อมาเองต้องการ
// ใช้เพิ่ม) ไม่ผูกกับ session ใดๆ (เป็นฟอนต์ระดับแอป ใช้ได้กับทุกเอกสารทันทีหลังติดตั้ง/ลบ)
//
// installFont รองรับติดตั้งได้หลายไฟล์/หลายสไตล์ต่อ 1 font family (ผู้ใช้แจ้งขอเพิ่ม — เหมือนปุ่ม
// Bold/Italic/Bold Italic บน toolbar ไม่ใช่ตัวหนา/เอียงปลอมจากไฟล์เดียว): เรียกครั้งแรกไม่ส่ง opts.familyKey
// มา (สร้าง family ใหม่ ต้องเป็นไฟล์ตัวปกติ/Regular เท่านั้น) แล้วเอา `installed.key` จาก response มา
// เป็น opts.familyKey ตอนอัปโหลดไฟล์สไตล์ถัดไป (Bold/Italic/Bold Italic) เข้า family เดียวกัน —
// response คืน { installed, fonts } เสมอ (fonts = รายการฟอนต์ทั้งชุดล่าสุดแบบ flat เหมือนเดิม)
export async function installFont(file, label, opts = {}) {
  const form = new FormData();
  form.append("file", file);
  if (label) form.append("label", label);
  if (opts.familyKey) form.append("family_key", opts.familyKey);
  if (opts.style) form.append("style", opts.style);
  const res = await fetchWithAuth(`${BASE}/edit/fonts/install`, { method: "POST", body: form });
  return handle(res);
}

// ติดตั้งฟอนต์จากลิงก์ Google Fonts (https เท่านั้น — ดู backend services/font_url.py)
// ขั้น 1: ตรวจลิงก์ → { token, family, styles: [{style, size, has_thai, file_url}], has_thai, exists, missing_styles }
export async function previewFontUrl(url) {
  const res = await fetchWithAuth(`${BASE}/edit/fonts/url/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  return handle(res);
}

// ขั้น 2: ติดตั้งทุกสไตล์ที่ตรวจไว้ → { installed, fonts }
export async function installFontUrl(token, label) {
  const res = await fetchWithAuth(`${BASE}/edit/fonts/url/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, label: label || undefined }),
  });
  return handle(res);
}

// ลบฟอนต์ที่ติดตั้งเองทั้ง family เดียว (ทุกสไตล์ที่มี — ไม่ใช่ทีละไฟล์) คืนรายการฟอนต์ทั้งชุดล่าสุด
// แบบ flat เหมือนเดิม
export async function removeFontFamily(familyKey) {
  const res = await fetchWithAuth(`${BASE}/edit/fonts/${encodeURIComponent(familyKey)}`, { method: "DELETE" });
  return handle(res);
}

// URL ของไฟล์ font ที่มากับระบบ (สำรอง — ปกติใช้ font.file_url จาก getFonts() ซึ่งมี token ของฟอนต์ส่วนตัวแนบมา)
// URL ของไฟล์ font จริง (.ttf/.otf) ตาม key — ใช้ประกาศ @font-face ให้พรีวิวตอนแก้ไขข้อความ (ดู App.jsx
// useEffect ที่ inject <style> ด้วย fonts state) ใช้ไฟล์เดียวกันเป๊ะกับที่ backend ใช้เรนเดอร์จริงเสมอ
// (ดูหมายเหตุ routes_edit.get_font_file — แก้บั๊กที่ผู้ใช้แจ้งว่าขนาดฟอนต์ตอนแก้ไขกับตอนบันทึกจริงไม่ตรงกัน)
export function fontFileUrl(key) {
  return `${BASE}/edit/fonts/${encodeURIComponent(key)}/file`;
}

export async function getTextBlocks(sessionId, pageNumber) {
  const ts = new Date().getTime();
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page/${pageNumber}/text-blocks?_t=${ts}`, { cache: "no-store" });
  return handle(res);
}

export async function editText(sessionId, payload) {
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

// ---------- Image editing ----------

export async function getImages(sessionId, pageNumber) {
  const ts = new Date().getTime();
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page/${pageNumber}/images?_t=${ts}`, { cache: "no-store" });
  return handle(res);
}

export async function deleteImage(sessionId, pageNumber, xref, rect = null) {
  let query = "";
  if (rect && typeof rect.x0 === "number") {
    query = `?x0=${rect.x0}&y0=${rect.y0}&x1=${rect.x1}&y1=${rect.y1}`;
  }
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page/${pageNumber}/image/${xref}${query}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Delete image failed");
  return res.json();
}

export async function replaceImage(sessionId, pageNumber, xref, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page/${pageNumber}/image/${xref}`, {
    method: "POST",
    body: form,
  });
  return handle(res);
}

// แทรกรูปภาพใหม่ลงหน้า (ปุ่ม Insert Image) — คนละ endpoint กับ replaceImage ด้านบน (ซึ่ง "แทนที่"
// รูปที่มีอยู่แล้วเท่านั้น) rect ส่งเป็น form field แยก (x0/y0/x1/y1) เพราะ multipart ผสม pydantic
// body model ตรงๆ ไม่ได้
export async function insertImage(sessionId, pageNumber, rect, file) {
  const form = new FormData();
  form.append("file", file);
  form.append("x0", rect.x0);
  form.append("y0", rect.y0);
  form.append("x1", rect.x1);
  form.append("y1", rect.y1);
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page/${pageNumber}/image`, {
    method: "POST",
    body: form,
  });
  return handle(res);
}

// ย้าย/ปรับขนาดรูปภาพที่มีอยู่แล้ว (ลากกล่อง/handle) — ไม่เปลี่ยนเนื้อรูป แค่ขยับ/ย่อ-ขยายกรอบ
export async function repositionImage(sessionId, pageNumber, xref, oldRect, newRect) {
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page/${pageNumber}/image/${xref}/reposition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_rect: oldRect, new_rect: newRect }),
  });
  return handle(res);
}

// object URL (blob:) ของเนื้อรูปดิบ (ตาม xref) ใช้เป็น src ของ <img> ตอนโชว์พรีวิวในกล่องลากย้าย/ปรับขนาด
// ผู้เรียกต้อง URL.revokeObjectURL() เองเมื่อเลิกใช้ (useImageEdit จัดการ blob: URL ทั้งหมดอยู่แล้ว)
export async function fetchImageRawObjectUrl(sessionId, pageNumber, xref) {
  const { blob } = await fetchBlob(`${BASE}/edit/${sessionId}/page/${pageNumber}/image/${xref}/raw`, "image");
  return URL.createObjectURL(blob);
}

// ---------- Digital Signature (เมนู Digital Signature ถัดจาก Tools — ผู้ใช้แจ้งขอ) ----------

export async function applyWatermark(sessionId, payload) {
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/watermark`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

// ใส่เลขหน้า (เมนูแทรก › เลขหน้า) — payload ดู PageNumberModal / backend PageNumberRequest · คืน {status, count}
export async function applyPageNumbers(sessionId, payload) {
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page-numbers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle(res);
}

// ---------- บาร์โค้ด (เมนูแทรก › บาร์โค้ด) ----------
// spec = { type, data, ec_level, show_text, bar_color, bg_color } (ดู backend BarcodeRequest)

export async function getBarcodeTypes() {
  return handle(await fetchWithAuth(`${BASE}/edit/barcode/types`));
}

/** ตรวจข้อมูล + ภาพตัวอย่าง → { blob, data (ข้อมูลหลังปรับ เช่น เติมเลขตรวจสอบ) } · ข้อมูลไม่ถูกต้อง → throw ข้อความเหตุผล */
export async function previewBarcode(spec, { signal } = {}) {
  const res = await fetchWithAuth(`${BASE}/edit/barcode/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
    signal,
  });
  if (!res.ok) await handle(res);
  const data = decodeURIComponent(res.headers.get("X-Barcode-Data") || "") || spec.data;
  return { blob: await res.blob(), data };
}

export async function insertBarcode(sessionId, pageNumber, rect, spec) {
  const res = await fetchWithAuth(`${BASE}/edit/${sessionId}/page/${pageNumber}/barcode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...spec, x0: rect.x0, y0: rect.y0, x1: rect.x1, y1: rect.y1 }),
  });
  return handle(res);
}
