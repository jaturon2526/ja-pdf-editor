// ช่วงหน้าแบบที่ผู้ใช้พิมพ์ "1-3, 5, 8-" ↔ ชุดเลขหน้า (1-based) — ใช้ในหน้าต่างแทรกหน้า
// ตรวจละเอียดอีกชั้นที่ backend (pdf_service.parse_page_range) — ตรงนี้แค่ไฮไลต์ภาพย่อให้ตรงกับที่พิมพ์

const THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙";

function toAscii(text) {
  return [...(text || "")].map((ch) => {
    const i = THAI_DIGITS.indexOf(ch);
    if (i >= 0) return String(i);
    return "–—".includes(ch) ? "-" : ch;
  }).join("");
}

/** "1-3, 5" → [1, 2, 3, 5] (ตามลำดับที่พิมพ์ ไม่ซ้ำ) · รูปแบบผิดหรือเกินจำนวนหน้า → null */
export function parsePageRange(text, maxPages) {
  const out = [];
  const seen = new Set();
  const add = (n) => { if (!seen.has(n)) { seen.add(n); out.push(n); } };
  const parts = toAscii(text).replace(/\s+/g, "").split(",").filter(Boolean);
  for (const part of parts) {
    const m = /^(\d*)-(\d*)$/.exec(part);
    if (m) {
      if (!m[1] && !m[2]) return null;
      const a = m[1] ? Number(m[1]) : 1;
      const b = m[2] ? Number(m[2]) : maxPages;
      if (a < 1 || b < 1 || a > maxPages || b > maxPages) return null;
      const step = b >= a ? 1 : -1;
      for (let i = a; i !== b + step; i += step) add(i);
    } else if (/^\d+$/.test(part)) {
      const n = Number(part);
      if (n < 1 || n > maxPages) return null;
      add(n);
    } else {
      return null;
    }
  }
  return out;
}

/** [1, 2, 3, 5, 8, 9] → "1-3, 5, 8-9" (เรียงจากน้อยไปมาก) */
export function formatPageRange(pages) {
  const sorted = [...new Set(pages)].sort((a, b) => a - b);
  const out = [];
  let start = null;
  let prev = null;
  for (const p of sorted) {
    if (start === null) start = p;
    else if (p !== prev + 1) { out.push(start === prev ? `${start}` : `${start}-${prev}`); start = p; }
    prev = p;
  }
  if (start !== null) out.push(start === prev ? `${start}` : `${start}-${prev}`);
  return out.join(", ");
}
