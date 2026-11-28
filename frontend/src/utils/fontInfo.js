// ข้อความแสดงข้อมูลฟอนต์จริงในไฟล์ (ตรวจฟอนต์ v1.38.0) — ใช้ร่วมแผงคุณสมบัติ / เครื่องมือตรวจฟอนต์ / รายการฟอนต์ทั้งเอกสาร

export function embedLabel(f, t) {
  if (f.embedded) {
    if (f.subset) return t ? t("fontInfo.embeddedSubset") : "ฝังในไฟล์ (เฉพาะตัวอักษรที่ใช้)";
    return t ? t("fontInfo.embeddedFull") : "ฝังในไฟล์ทั้งชุด";
  }
  if (f.base14) return t ? t("fontInfo.base14") : "ฟอนต์มาตรฐาน PDF (ไม่ต้องฝัง)";
  return t ? t("fontInfo.notEmbedded") : "ไม่ได้ฝังในไฟล์ — เครื่องอื่นอาจแสดงด้วยฟอนต์อื่น";
}

export function embedTone(f) {
  return f.embedded || f.base14 ? "ok" : "warn";
}

export function styleLabel(f, t) {
  if (f.bold && f.italic) return t ? t("fontInfo.boldItalic") : "ตัวหนาเอียง";
  if (f.bold) return t ? t("fontInfo.bold") : "ตัวหนา";
  if (f.italic) return t ? t("fontInfo.italic") : "ตัวเอียง";
  return t ? t("fontInfo.regular") : "ปกติ";
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
