// ข้อความแสดงข้อมูลฟอนต์จริงในไฟล์ (ตรวจฟอนต์ v1.38.0) — ใช้ร่วมแผงคุณสมบัติ / เครื่องมือตรวจฟอนต์ / รายการฟอนต์ทั้งเอกสาร

export function embedLabel(f) {
  if (f.embedded) return f.subset ? "ฝังในไฟล์ (เฉพาะตัวอักษรที่ใช้)" : "ฝังในไฟล์ทั้งชุด";
  if (f.base14) return "ฟอนต์มาตรฐาน PDF (ไม่ต้องฝัง)";
  return "ไม่ได้ฝังในไฟล์ — เครื่องอื่นอาจแสดงด้วยฟอนต์อื่น";
}

export function embedTone(f) {
  return f.embedded || f.base14 ? "ok" : "warn";
}

export function styleLabel(f) {
  if (f.bold && f.italic) return "ตัวหนาเอียง";
  if (f.bold) return "ตัวหนา";
  if (f.italic) return "ตัวเอียง";
  return "ปกติ";
}

export function sizeLabel(size) {
  return `${Number.isInteger(size) ? size : size.toFixed(1)} pt`;
}

// "1, 2, 3, 5, 7, 8, 9" → "1–3, 5, 7–9"
export function pagesLabel(pages = []) {
  const out = [];
  let start = null;
  let prev = null;
  for (const p of pages) {
    if (start === null) start = p;
    else if (p !== prev + 1) {
      out.push(start === prev ? `${start}` : `${start}–${prev}`);
      start = p;
    }
    prev = p;
  }
  if (start !== null) out.push(start === prev ? `${start}` : `${start}–${prev}`);
  return out.join(", ");
}
