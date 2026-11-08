// แยกหน้าเอกสาร (เมนู หน้า > แยกหน้าเอกสาร) — ระบุหน้า เช่น "1-3, 5" แล้วดาวน์โหลดเป็นไฟล์เดียว หรือไฟล์ละหน้า (.zip)
// - ลำดับตามที่พิมพ์ ("5, 1-3" → หน้า 5,1,2,3) · ช่วงถอยหลังได้ ("6-4") · "-3" = หน้า 1-3 · "8-" = หน้า 8 ถึงหน้าสุดท้าย
// - ตรวจเลขหน้ากับจำนวนหน้าจริงก่อนส่ง และแสดงสรุปว่าจะได้หน้าไหนบ้าง (กฎเดียวกับ backend parse_page_range)
// - ไฟล์ที่ได้มีการแก้ไขล่าสุด (ยังไม่บันทึกก็ได้) ช่องกรอกฟอร์ม/ลิงก์/บุ๊กมาร์กยังอยู่ และใส่รหัสผ่านเดียวกับเอกสาร ถ้าตั้งไว้
import { useState } from "react";  // Esc ปิดผ่าน useEscapeStack ใน Editor

const THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙";

/** แปลงข้อความช่วงหน้าเป็นเลขหน้า (1-based) ตามลำดับที่พิมพ์ ไม่ซ้ำ — คืน { pages } หรือ { error } */
export function parsePageRange(text, total) {
  const norm = String(text || "")
    .replace(/[๐-๙]/g, (d) => String(THAI_DIGITS.indexOf(d)))
    .replace(/[–—−~]/g, "-")
    .replace(/[，、;]/g, ",")
    .replace(/\s+/g, "");
  const pages = [];
  const seen = new Set();
  const add = (n) => {
    if (!seen.has(n)) {
      seen.add(n);
      pages.push(n);
    }
  };
  const num = (tok, part) => {
    if (!/^\d+$/.test(tok)) throw new Error(`รูปแบบเลขหน้าไม่ถูกต้อง: ${part}`);
    const n = Number(tok);
    if (n < 1 || n > total) throw new Error(`ไม่มีหน้า ${n} (เอกสารมี ${total} หน้า)`);
    return n;
  };
  try {
    for (const part of norm.split(",")) {
      if (!part) continue;
      if (part.includes("-")) {
        const bits = part.split("-");
        if (bits.length !== 2 || (!bits[0] && !bits[1])) throw new Error(`รูปแบบช่วงหน้าไม่ถูกต้อง: ${part}`);
        const start = bits[0] ? num(bits[0], part) : 1;
        const end = bits[1] ? num(bits[1], part) : total;
        const step = end >= start ? 1 : -1;
        for (let i = start; i !== end + step; i += step) add(i);
      } else {
        add(num(part, part));
      }
    }
  } catch (e) {
    return { error: e.message };
  }
  return pages.length ? { pages } : { error: "กรุณาระบุเลขหน้า" };
}

/** [1,2,3,5] → "1-3, 5" */
export function rangeLabel(pages) {
  const parts = [];
  for (let i = 0; i < pages.length; ) {
    let j = i;
    while (j + 1 < pages.length && pages[j + 1] === pages[j] + 1) j++;
    parts.push(i === j ? `${pages[i]}` : `${pages[i]}-${pages[j]}`);
    i = j + 1;
  }
  return parts.join(", ");
}

const MODES = [
  { value: "single", label: "รวมเป็นไฟล์เดียว", hint: "หน้าที่เลือกทั้งหมดเป็น PDF ไฟล์เดียว เรียงตามลำดับที่พิมพ์" },
  { value: "split", label: "แยกไฟล์ละหน้า", hint: "PDF หน้าละ 1 ไฟล์ ดาวน์โหลดรวมเป็นไฟล์ .zip" },
];

function ExtractPagesForm({ onClose, onExtract, totalPages }) {
  const [pageRange, setPageRange] = useState("");
  const [mode, setMode] = useState("single");
  const [touched, setTouched] = useState(false);
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const parsed = parsePageRange(pageRange, totalPages);
  const showError = (touched || pageRange.trim()) && parsed.error;

  async function handleSubmit(e) {
    e.preventDefault();
    setTouched(true);
    if (parsed.error || submitting) return;
    setSubmitting(true);
    setServerError("");
    try {
      await onExtract(pageRange, mode);
    } catch (err) {
      setServerError(err.message || "แยกหน้าเอกสารไม่สำเร็จ");
      setSubmitting(false);
    }
  }

  const chip = "px-2.5 py-1 min-h-[32px] text-xs rounded-full border border-gray-300 text-gray-700 hover:bg-gray-50";
  const count = parsed.pages?.length || 0;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && onClose()}>
      <form role="dialog" aria-modal="true" aria-labelledby="extract-title" onSubmit={handleSubmit}
        className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92dvh]">
        <div className="p-4 border-b border-gray-100">
          <h2 id="extract-title" className="text-lg font-bold text-gray-900">แยกหน้าเอกสาร</h2>
          <p className="mt-1 text-sm text-gray-500">ดาวน์โหลดเฉพาะหน้าที่ต้องการเป็นไฟล์ใหม่ — เอกสารที่เปิดอยู่ไม่ถูกแก้</p>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto">
          <div>
            <label htmlFor="extract-range" className="block text-sm font-medium text-gray-800">
              หน้าที่ต้องการ <span className="font-normal text-gray-500">(เอกสารมี {totalPages} หน้า)</span>
            </label>
            <input id="extract-range" type="text" inputMode="text" autoFocus autoComplete="off" maxLength={500}
              placeholder="เช่น 1-3, 5, 8-10"
              aria-invalid={showError ? "true" : "false"}
              value={pageRange}
              onChange={(e) => { setPageRange(e.target.value); setServerError(""); }}
              className={`mt-1 block w-full px-3 py-2 border rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-1 ${showError ? "border-red-400 focus:ring-red-500 focus:border-red-500" : "border-gray-300 focus:ring-blue-500 focus:border-blue-500"}`} />
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button type="button" className={chip} onClick={() => setPageRange(`1-${totalPages}`)}>ทุกหน้า</button>
              {totalPages > 1 && <button type="button" className={chip} onClick={() => setPageRange(`${totalPages}-1`)}>ทุกหน้า (กลับลำดับ)</button>}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              คั่นด้วยจุลภาค (,) และใช้ขีด (-) สำหรับช่วงหน้า · เรียงตามลำดับที่พิมพ์ เช่น <code>5, 1-3</code> = หน้า 5 ก่อน
            </p>
            {showError ? (
              <p className="mt-1 text-sm text-red-600" role="alert">{parsed.error}</p>
            ) : count > 0 ? (
              <p className="mt-1 text-sm text-gray-700" data-testid="extract-summary">
                จะได้ <strong>{count} หน้า</strong>: {rangeLabel(parsed.pages)}
              </p>
            ) : null}
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-gray-800 mb-1">รูปแบบไฟล์</legend>
            {MODES.map((m) => (
              <label key={m.value}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${mode === m.value ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:bg-gray-50"}`}>
                <input type="radio" name="extract-mode" className="mt-1" value={m.value} checked={mode === m.value}
                  onChange={() => setMode(m.value)} />
                <span>
                  <span className="block text-sm font-medium text-gray-900">{m.label}</span>
                  <span className="block text-xs text-gray-500">{m.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          {serverError && <p className="text-sm text-red-600" role="alert">{serverError}</p>}
        </div>

        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">ยกเลิก</button>
          <button type="submit" disabled={submitting || (touched && !!parsed.error)}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
            {submitting ? "กำลังแยกหน้า…" : mode === "split" && count > 1 ? `ดาวน์โหลด ${count} ไฟล์ (.zip)` : "ดาวน์โหลด"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ฟอร์มถูกสร้างใหม่ทุกครั้งที่เปิด — ค่าเดิม/ข้อผิดพลาดจากครั้งก่อนไม่ค้าง
export default function ExtractPagesModal({ isOpen, ...props }) {
  return isOpen ? <ExtractPagesForm {...props} /> : null;
}
