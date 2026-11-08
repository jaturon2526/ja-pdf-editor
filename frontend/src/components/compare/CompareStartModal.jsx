// เลือกไฟล์ 2 ฝั่งก่อนเปรียบเทียบ — A = ไฟล์เดิม, B = ไฟล์ใหม่
// แต่ละฝั่งเลือกได้จาก: ไฟล์ในบัญชี · อัปโหลด · ตัวเลือกพิเศษจากหน้าที่เปิด (Editor: เอกสารที่กำลังแก้ / ไฟล์ที่บันทึกไว้ / เวอร์ชันก่อนหน้า)
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { startCompare } from "../../api";

const OPTION_LABELS = [
  ["text", "เทียบข้อความ", "คำที่เพิ่ม ลบ หรือแก้"],
  ["visual", "เทียบภาพ", "รูป ลายเซ็น ตราประทับ เส้นตาราง"],
  ["ocr", "อ่านหน้าสแกนด้วย OCR", "หน้าที่เป็นภาพจะอ่านข้อความก่อนเทียบ (ช้ากว่า)"],
  ["ignore_case", "ไม่สนตัวพิมพ์เล็ก/ใหญ่", "A กับ a ถือว่าเหมือนกัน"],
];

function SidePicker({ id, title, hint, files, presets, value, onChange }) {
  const kind = value?.kind || "file";
  return (
    <fieldset className="border border-gray-200 rounded-lg p-3" aria-labelledby={`${id}-legend`}>
      <legend id={`${id}-legend`} className="px-1 text-sm font-semibold text-gray-900">{title}</legend>
      <p className="text-xs text-gray-500 mb-2">{hint}</p>
      <div className="space-y-2">
        {presets.map((p, i) => (
          <label key={p.label} className="flex items-start gap-2 text-sm cursor-pointer">
            <input type="radio" name={id} className="mt-1" checked={kind === `preset:${i}`}
              disabled={p.disabled} onChange={() => onChange({ kind: `preset:${i}`, side: p.side })} />
            <span className={p.disabled ? "text-gray-400" : ""}>{p.label}{p.note && <span className="block text-xs text-gray-500">{p.note}</span>}</span>
          </label>
        ))}
        <label className="flex items-start gap-2 text-sm cursor-pointer">
          <input type="radio" name={id} className="mt-1" checked={kind === "file"}
            onChange={() => onChange({ kind: "file", side: value?.fileSide || null })} />
          <span className="flex-1 min-w-0">
            ไฟล์ในเอกสารของฉัน
            <select aria-label={`${title}: เลือกไฟล์`} className="mt-1 block w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm"
              value={value?.kind === "file" && value.side ? String(value.side.fileId) : ""}
              onChange={(e) => {
                const side = e.target.value ? { fileId: Number(e.target.value), version: "current" } : null;
                onChange({ kind: "file", side, fileSide: side });
              }}
              onFocus={() => kind !== "file" && onChange({ kind: "file", side: value?.fileSide || null })}>
              <option value="">— เลือกไฟล์ —</option>
              {files.map((f) => <option key={f.id} value={f.id}>{f.filename}</option>)}
            </select>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm cursor-pointer">
          <input type="radio" name={id} className="mt-1" checked={kind === "upload"}
            onChange={() => onChange({ kind: "upload", side: value?.uploadSide || null })} />
          <span className="flex-1 min-w-0">
            อัปโหลดไฟล์ PDF
            <input type="file" accept="application/pdf,.pdf" aria-label={`${title}: อัปโหลดไฟล์`}
              className="mt-1 block w-full text-sm text-gray-600 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-gray-100"
              onChange={(e) => {
                const file = e.target.files?.[0];
                const side = file ? { file } : null;
                onChange({ kind: "upload", side, uploadSide: side });
              }} />
          </span>
        </label>
      </div>
    </fieldset>
  );
}

function firstPreset(presets) {
  const i = presets.findIndex((p) => !p.disabled);
  return i >= 0 ? { kind: `preset:${i}`, side: presets[i].side } : { kind: "file", side: null };
}

/**
 * files: ไฟล์ในบัญชี [{id, filename}] · presetsA/presetsB: [{label, note?, side, disabled?}] แสดงก่อน "ไฟล์ของฉัน"
 * initialA / initialB: {kind, side} ค่าเริ่มต้น (เช่น Dashboard เลือก 2 ไฟล์ไว้แล้ว)
 */
export default function CompareStartModal({ files = [], presetsA = [], presetsB = [], initialA = null, initialB = null, onClose }) {
  const navigate = useNavigate();
  const [a, setA] = useState(() => initialA || firstPreset(presetsA));
  const [b, setB] = useState(() => initialB || firstPreset(presetsB));
  const [options, setOptions] = useState({ text: true, visual: true, ocr: true, ignore_case: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ready = useMemo(() => !!(a?.side && b?.side) && (options.text || options.visual), [a, b, options]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function submit(e) {
    e.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError("");
    try {
      const res = await startCompare(a.side, b.side, options);
      navigate(`/compare/${res.task_id}`);
    } catch (err) {
      setError(err.message || "เริ่มเปรียบเทียบไม่สำเร็จ");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm" onClick={() => !busy && onClose()}>
      <form role="dialog" aria-modal="true" aria-labelledby="compare-start-title" onSubmit={submit}
        className="bg-white w-full sm:max-w-2xl rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92vh]"
        onClick={(e) => e.stopPropagation()} data-testid="compare-start">
        <div className="p-4 border-b border-gray-100">
          <h3 id="compare-start-title" className="text-lg font-bold text-gray-900">เปรียบเทียบเอกสาร</h3>
          <p className="mt-1 text-sm text-gray-500">เลือกไฟล์เดิมและไฟล์ใหม่ ระบบจะไฮไลต์ข้อความที่เพิ่ม ลบ แก้ และจุดที่ภาพต่างกัน</p>
        </div>
        <div className="p-4 overflow-y-auto space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <SidePicker id="cmp-a" title="ไฟล์เดิม (A)" hint="ฉบับก่อนแก้ไข" files={files} presets={presetsA} value={a} onChange={setA} />
            <SidePicker id="cmp-b" title="ไฟล์ใหม่ (B)" hint="ฉบับที่ต้องการตรวจ" files={files} presets={presetsB} value={b} onChange={setB} />
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {OPTION_LABELS.map(([key, label, note]) => (
              <label key={key} className="flex items-start gap-2 text-sm cursor-pointer">
                <input type="checkbox" className="mt-1" checked={options[key]}
                  onChange={(e) => setOptions((o) => ({ ...o, [key]: e.target.checked }))} />
                <span>{label}<span className="block text-xs text-gray-500">{note}</span></span>
              </label>
            ))}
          </div>
          {!options.text && !options.visual && <p className="text-sm text-amber-700">เลือกเทียบข้อความหรือภาพอย่างน้อย 1 อย่าง</p>}
          {error && <p className="text-sm text-red-700 bg-red-50 rounded p-2" role="alert">{error}</p>}
        </div>
        <div className="p-4 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={busy} className="px-4 py-2 text-sm border border-gray-300 rounded-lg bg-white hover:bg-gray-50">ยกเลิก</button>
          <button type="submit" disabled={!ready || busy} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {busy ? "กำลังเริ่ม..." : "เปรียบเทียบ"}
          </button>
        </div>
      </form>
    </div>
  );
}
