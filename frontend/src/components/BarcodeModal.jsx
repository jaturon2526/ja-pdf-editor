// แทรกบาร์โค้ด (เมนูแทรก › บาร์โค้ด): เลือกประเภท → กรอกข้อมูล → ตรวจข้อมูล + ตัวอย่างจริงจาก backend → ตกลง
// ตกลงแล้ววางกล่องกลางหน้าให้ลากย้าย/ย่อขยายได้เหมือนรูป (คงอัตราส่วน) · กด "บันทึกการแก้ไข" แล้วได้บาร์โค้ดเวกเตอร์
// ประเภท 2 มิติใส่ภาษาไทยได้ (backend เข้ารหัส UTF-8 + ECI) · ประเภท 1 มิติตรวจรูปแบบ/เลขตรวจสอบ
import { useEffect, useMemo, useRef, useState } from "react";
import { previewBarcode } from "../api/edit.js";

export const BARCODE_TYPES = [
  { key: "qrcode", label: "QR Code", twoD: true, unicode: true, hint: "ข้อความ ลิงก์ ภาษาไทยได้" },
  { key: "datamatrix", label: "Data Matrix", twoD: true, unicode: true, hint: "ภาษาไทยได้ ขนาดเล็ก" },
  { key: "pdf417", label: "PDF417", twoD: true, unicode: true, hint: "ข้อความยาว ภาษาไทยได้" },
  { key: "azteccode", label: "Aztec", twoD: true, unicode: true, hint: "ภาษาไทยได้ (ตั๋วเดินทาง)" },
  { key: "code128", label: "Code 128", hint: "อังกฤษ ตัวเลข สัญลักษณ์" },
  { key: "code39", label: "Code 39", hint: "A–Z 0–9 - . $ / + % ช่องว่าง" },
  { key: "ean13", label: "EAN-13", hint: "ตัวเลข 12–13 หลัก (สินค้า)" },
  { key: "ean8", label: "EAN-8", hint: "ตัวเลข 7–8 หลัก" },
  { key: "upca", label: "UPC-A", hint: "ตัวเลข 11–12 หลัก" },
  { key: "itf", label: "ITF", hint: "ตัวเลขจำนวนหลักเป็นคู่" },
  { key: "codabar", label: "Codabar", hint: "ตัวเลข และ - $ : / . +" },
];
const EC = [
  { v: "L", label: "L ~7%" }, { v: "M", label: "M ~15%" }, { v: "Q", label: "Q ~25%" }, { v: "H", label: "H ~30%" },
];
const COLOR_PRESETS = [
  ["#000000", "#FFFFFF"], ["#1E3A8A", "#FFFFFF"], ["#14532D", "#FFFFFF"], ["#7F1D1D", "#FEF3C7"],
];

/** ตรวจเบื้องต้นฝั่งหน้าเว็บ (ตอบทันทีระหว่างพิมพ์) — backend ตรวจซ้ำละเอียดกว่า (เลขตรวจสอบ, ความจุ, สี) */
export function quickCheck(type, raw) {
  const t = BARCODE_TYPES.find((x) => x.key === type);
  const data = t?.twoD ? raw : raw.trim();
  if (!data.trim()) return "กรุณากรอกข้อมูล";
  if (data.length > 1000) return "ข้อมูลยาวเกิน 1000 ตัวอักษร";
  if (!t.unicode && /[^\x20-\x7E]/.test(data)) return `${t.label} ใส่ได้เฉพาะตัวอักษรภาษาอังกฤษ/ตัวเลข — ข้อความภาษาไทยให้ใช้ QR Code หรือ Data Matrix`;
  const digits = /^\d+$/.test(data);
  if (type === "ean13" && !(digits && (data.length === 12 || data.length === 13))) return "EAN-13 ต้องเป็นตัวเลข 12 หลัก (ระบบเติมเลขตรวจสอบให้) หรือ 13 หลัก";
  if (type === "ean8" && !(digits && (data.length === 7 || data.length === 8))) return "EAN-8 ต้องเป็นตัวเลข 7 หรือ 8 หลัก";
  if (type === "upca" && !(digits && (data.length === 11 || data.length === 12))) return "UPC-A ต้องเป็นตัวเลข 11 หรือ 12 หลัก";
  if (type === "itf" && !(digits && data.length % 2 === 0)) return "ITF ต้องเป็นตัวเลขจำนวนหลักเป็นคู่ — เติม 0 ข้างหน้าได้";
  if (type === "code39" && !/^[0-9A-Z \-.$/+%]+$/.test(data.toUpperCase())) return "Code 39 ใช้ได้เฉพาะ A–Z, 0–9, ช่องว่าง และ - . $ / + %";
  return null;
}

export default function BarcodeModal({ onClose, onSubmit }) {
  const [type, setType] = useState("qrcode");
  const [data, setData] = useState("");
  const [ec, setEc] = useState("M");
  const [showText, setShowText] = useState(true);
  const [barColor, setBarColor] = useState("#000000");
  const [bgColor, setBgColor] = useState("#FFFFFF");
  const [preview, setPreview] = useState(null); // { url, blob, data, w, h }
  const [serverError, setServerError] = useState("");
  const [checking, setChecking] = useState(false);
  const t = BARCODE_TYPES.find((x) => x.key === type);
  const localError = data ? quickCheck(type, data) : null;
  const spec = useMemo(
    () => ({ type, data, ec_level: ec, show_text: showText, bar_color: barColor, bg_color: bgColor }),
    [type, data, ec, showText, barColor, bgColor],
  );
  const urlRef = useRef(null);

  // ตัวอย่างจริงจาก backend (หน่วง 450ms หลังพิมพ์) — ได้ทั้งผลตรวจข้อมูลและภาพเดียวกับที่จะวางลงเอกสาร
  useEffect(() => {
    setServerError("");
    if (!data || localError) {
      setPreview(null);
      return undefined;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setChecking(true);
      try {
        const res = await previewBarcode(spec, { signal: ctrl.signal });
        const url = URL.createObjectURL(res.blob);
        const img = new Image();
        img.onload = () => {
          if (ctrl.signal.aborted) { URL.revokeObjectURL(url); return; }
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          urlRef.current = url;
          setPreview({ url, blob: res.blob, data: res.data, w: img.naturalWidth, h: img.naturalHeight });
        };
        img.src = url;
      } catch (err) {
        if (!ctrl.signal.aborted) { setPreview(null); setServerError(err.message); }
      } finally {
        if (!ctrl.signal.aborted) setChecking(false);
      }
    }, 450);
    return () => { ctrl.abort(); clearTimeout(timer); };
  }, [spec, data, localError]);

  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }, []);
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ready = !!preview && !localError && !serverError && !checking;
  function handleSubmit(e) {
    e.preventDefault();
    if (!ready) return;
    // ขนาดเริ่มต้นบนหน้า: 2 มิติกว้าง ~1.3 นิ้ว, 1 มิติกว้าง ~2.5 นิ้ว (ย่อ/ขยายต่อได้)
    const widthPt = t.twoD ? (type === "pdf417" ? 200 : 96) : 180;
    const heightPt = (preview.h / preview.w) * widthPt;
    onSubmit({ spec: { ...spec, data: preview.data }, blob: preview.blob, widthPt, heightPt });
  }

  const chip = (active) =>
    `px-2.5 py-1 min-h-[32px] text-xs rounded-full border ${active ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`;
  const error = localError || serverError;
  const adjusted = preview && preview.data !== (t.twoD ? data : data.trim()) ? preview.data : null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form role="dialog" aria-modal="true" aria-labelledby="bc-title" onSubmit={handleSubmit}
        className="bg-white w-full sm:max-w-2xl rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92dvh]">
        <div className="p-4 border-b border-gray-100">
          <h2 id="bc-title" className="text-lg font-bold text-gray-900">แทรกบาร์โค้ด</h2>
          <p className="mt-1 text-xs text-gray-500">ตกลงแล้วลากวางและย่อขยายบนหน้าได้ — บันทึกเป็นภาพเวกเตอร์ คมทุกขนาด</p>
        </div>
        <div className="p-4 overflow-y-auto grid gap-5 sm:grid-cols-[1fr_220px]">
          <div className="space-y-4 min-w-0">
            <div>
              <label htmlFor="bc-type" className="block text-sm font-medium text-gray-800">ประเภท</label>
              <select id="bc-type" value={type} onChange={(e) => setType(e.target.value)}
                className="mt-1 block w-full px-2.5 py-2 border border-gray-300 rounded-lg text-sm">
                <optgroup label="2 มิติ — ใส่ภาษาไทยได้">
                  {BARCODE_TYPES.filter((x) => x.twoD).map((x) => <option key={x.key} value={x.key}>{x.label} — {x.hint}</option>)}
                </optgroup>
                <optgroup label="1 มิติ — อังกฤษ/ตัวเลข">
                  {BARCODE_TYPES.filter((x) => !x.twoD).map((x) => <option key={x.key} value={x.key}>{x.label} — {x.hint}</option>)}
                </optgroup>
              </select>
            </div>
            <div>
              <label htmlFor="bc-data" className="block text-sm font-medium text-gray-800">ข้อมูล</label>
              {t.twoD ? (
                <textarea id="bc-data" rows={3} maxLength={1000} autoFocus value={data} onChange={(e) => setData(e.target.value)}
                  placeholder="เช่น https://example.com หรือ ข้อความภาษาไทย"
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
              ) : (
                <input id="bc-data" autoFocus maxLength={200} value={data} onChange={(e) => setData(e.target.value)}
                  placeholder={t.hint} inputMode={["ean13", "ean8", "upca", "itf"].includes(type) ? "numeric" : undefined}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono" />
              )}
              <p className="mt-1 text-xs text-gray-500">{data.length}/{t.twoD ? 1000 : 200} ตัวอักษร</p>
            </div>
            {type === "qrcode" && (
              <fieldset>
                <legend className="text-sm font-medium text-gray-800">ระดับแก้ไขข้อผิดพลาด (สแกนได้แม้เสียหายบางส่วน)</legend>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {EC.map((x) => <button key={x.v} type="button" aria-pressed={ec === x.v} className={chip(ec === x.v)} onClick={() => setEc(x.v)}>{x.label}</button>)}
                </div>
              </fieldset>
            )}
            {!t.twoD && (
              <label className="flex items-center gap-2 text-sm text-gray-800">
                <input type="checkbox" checked={showText} onChange={(e) => setShowText(e.target.checked)} />
                แสดงตัวเลข/ข้อความใต้บาร์โค้ด
              </label>
            )}
            <fieldset>
              <legend className="text-sm font-medium text-gray-800">สี</legend>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {COLOR_PRESETS.map(([b, g]) => (
                  <button key={b + g} type="button" aria-label={`สีเส้น ${b} พื้น ${g}`} aria-pressed={barColor === b && bgColor === g}
                    className={`${chip(barColor === b && bgColor === g)} inline-flex items-center`} onClick={() => { setBarColor(b); setBgColor(g); }}>
                    <span className="inline-block w-5 h-5 rounded border border-gray-300" style={{ background: g }}>
                      <span className="block w-2.5 h-5 rounded-l" style={{ background: b }} />
                    </span>
                  </button>
                ))}
                <label className="text-xs text-gray-700 inline-flex items-center gap-1 ml-2">เส้น
                  <input type="color" aria-label="สีเส้น" value={barColor} onChange={(e) => setBarColor(e.target.value.toUpperCase())} className="w-8 h-8 p-0 border-0 bg-transparent" />
                </label>
                <label className="text-xs text-gray-700 inline-flex items-center gap-1">พื้น
                  <input type="color" aria-label="สีพื้นหลัง" value={bgColor} onChange={(e) => setBgColor(e.target.value.toUpperCase())} className="w-8 h-8 p-0 border-0 bg-transparent" />
                </label>
              </div>
            </fieldset>
          </div>
          <div className="flex flex-col items-center gap-2" data-testid="barcode-preview">
            <div className="w-[200px] h-[200px] border border-gray-200 rounded-lg bg-gray-50 flex items-center justify-center overflow-hidden">
              {preview ? <img src={preview.url} alt="ตัวอย่างบาร์โค้ด" className="max-w-full max-h-full" />
                : <span className="text-xs text-gray-400 px-3 text-center">{checking ? "กำลังสร้างตัวอย่าง…" : "ตัวอย่างจะแสดงเมื่อข้อมูลถูกต้อง"}</span>}
            </div>
            {adjusted && <p className="text-xs text-blue-700 text-center" data-testid="barcode-adjusted">ข้อมูลจริง: <span className="font-mono">{adjusted}</span></p>}
          </div>
        </div>
        {error && <p className="mx-4 mb-2 text-sm text-red-700 bg-red-50 rounded p-2" role="alert">{error}</p>}
        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">ยกเลิก</button>
          <button type="submit" disabled={!ready}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
            ตกลง
          </button>
        </div>
      </form>
    </div>
  );
}
