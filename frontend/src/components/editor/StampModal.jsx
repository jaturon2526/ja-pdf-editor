import React, { useEffect, useRef, useState } from "react";
import {
  STAMP_ANGLES,
  STAMP_COLORS,
  STAMP_OPACITIES,
  STAMP_PRESETS,
  drawStamp,
  formatThaiDate,
  renderStampPngFile,
} from "../../utils/stampRenderer.js";

/**
 * หน้าต่างเลือกและปรับแต่งตราประทับสำเร็จรูป (Stamps)
 * แสดงตัวอย่างแบบเรียลไทม์บน <canvas> แล้วสร้าง PNG โปร่งใสส่งเข้าโหมดวางรูป (ลาก ย่อ/ขยาย Undo ได้)
 */
export default function StampModal({ onClose, onSubmit }) {
  const firstPreset = STAMP_PRESETS[0];
  const [presetId, setPresetId] = useState(firstPreset.id);
  const [text, setText] = useState(firstPreset.text);
  const [includeDate, setIncludeDate] = useState(firstPreset.includeDate);
  const [subText, setSubText] = useState(firstPreset.includeDate ? formatThaiDate() : "");
  const [color, setColor] = useState(firstPreset.color);
  const [angleDeg, setAngleDeg] = useState(firstPreset.angleDeg);
  const [opacity, setOpacity] = useState(0.85);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const previewRef = useRef(null);

  useEffect(() => {
    const canvas = previewRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    drawStamp(ctx, canvas.width, canvas.height, {
      text,
      subText: includeDate ? subText : "",
      color,
      angleDeg,
      opacity,
    });
  }, [text, subText, includeDate, color, angleDeg, opacity]);

  function selectPreset(preset) {
    setPresetId(preset.id);
    setText(preset.text);
    setColor(preset.color);
    setAngleDeg(preset.angleDeg);
    setIncludeDate(preset.includeDate);
    setSubText(preset.includeDate ? formatThaiDate() : "");
    setError("");
  }

  function handleToggleDate(checked) {
    setIncludeDate(checked);
    if (checked && !subText.trim()) {
      setSubText(formatThaiDate());
    }
  }

  async function handleConfirm() {
    if (!text.trim()) {
      setError("กรุณากรอกข้อความบนตราประทับ");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const file = await renderStampPngFile({
        text: text.trim(),
        subText: includeDate ? subText.trim() : "",
        color,
        angleDeg,
        opacity,
      });
      onSubmit(file, text.trim());
    } catch (err) {
      setError(err?.message || "สร้างตราประทับไม่สำเร็จ");
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 flex items-end sm:items-center justify-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="ตราประทับสำเร็จรูป"
    >
      <div className="bg-white w-full sm:max-w-lg rounded-t-2xl sm:rounded-xl shadow-2xl border border-slate-200 max-h-[92dvh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 shrink-0">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M5 20h14" />
              <path d="M5 17h14v-2a3 3 0 0 0-3-3h-1.5a2 2 0 0 1-1.9-2.6l.6-2.1a3 3 0 1 0-5.4 0l.6 2.1A2 2 0 0 1 6.5 12H5a3 3 0 0 0-3 3v2z" />
            </svg>
            <h2 className="text-base font-semibold text-slate-800">ตราประทับสำเร็จรูป</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิดหน้าต่างตราประทับ"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4 overflow-y-auto">
          {/* Live Preview */}
          <div
            className="rounded-xl border border-slate-200 flex items-center justify-center p-2 overflow-hidden"
            style={{
              backgroundImage:
                "linear-gradient(45deg, #f8fafc 25%, transparent 25%), linear-gradient(-45deg, #f8fafc 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #f8fafc 75%), linear-gradient(-45deg, transparent 75%, #f8fafc 75%)",
              backgroundSize: "16px 16px",
              backgroundPosition: "0 0, 0 8px, 8px -8px, -8px 0px",
              backgroundColor: "#ffffff",
            }}
          >
            <canvas
              ref={previewRef}
              width={480}
              height={220}
              className="w-full max-w-[360px] h-auto"
              aria-label="ตัวอย่างตราประทับ"
            />
          </div>

          {/* Preset Chips */}
          <div>
            <div className="text-xs font-medium text-slate-600 mb-1.5">เลือกแบบสำเร็จรูป</div>
            <div className="flex flex-wrap gap-1.5">
              {STAMP_PRESETS.map((preset) => {
                const active = presetId === preset.id;
                return (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => selectPreset(preset)}
                    className={`px-2.5 py-1.5 rounded-lg text-xs font-medium border transition ${
                      active
                        ? "bg-blue-600 text-white border-blue-600 shadow-sm"
                        : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                    }`}
                  >
                    {preset.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Main Text */}
          <div>
            <label htmlFor="stamp-main-text" className="block text-xs font-medium text-slate-600 mb-1">
              ข้อความบนตราประทับ
            </label>
            <input
              id="stamp-main-text"
              type="text"
              value={text}
              maxLength={40}
              onChange={(e) => {
                setText(e.target.value);
                setError("");
              }}
              placeholder="เช่น สำเนาถูกต้อง, อนุมัติแล้ว, ลับ"
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Optional Date / Subtitle */}
          <div className="space-y-1.5">
            <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeDate}
                onChange={(e) => handleToggleDate(e.target.checked)}
                className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              <span>แสดงบรรทัดรอง / วันที่อัตโนมัติ (พ.ศ.)</span>
            </label>
            {includeDate && (
              <input
                type="text"
                aria-label="ข้อความบรรทัดรองหรือวันที่"
                value={subText}
                maxLength={48}
                onChange={(e) => setSubText(e.target.value)}
                placeholder={`เช่น ${formatThaiDate()} หรือ ลงชื่อ ................`}
                className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            )}
          </div>

          {/* Color & Angle & Opacity */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <div className="text-xs font-medium text-slate-600 mb-1.5">สีหมึก</div>
              <div className="flex items-center gap-2">
                {STAMP_COLORS.map((c) => {
                  const active = color === c.value;
                  return (
                    <button
                      key={c.value}
                      type="button"
                      onClick={() => setColor(c.value)}
                      aria-label={`สี${c.name}`}
                      title={c.name}
                      className={`w-7 h-7 rounded-full border-2 transition ${
                        active ? "ring-2 ring-offset-1 ring-blue-500 border-white scale-105" : "border-slate-200"
                      }`}
                      style={{ backgroundColor: c.value }}
                    />
                  );
                })}
              </div>
            </div>

            <div>
              <label htmlFor="stamp-angle" className="block text-xs font-medium text-slate-600 mb-1.5">
                มุมเอียง
              </label>
              <select
                id="stamp-angle"
                value={angleDeg}
                onChange={(e) => setAngleDeg(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {STAMP_ANGLES.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="stamp-opacity" className="block text-xs font-medium text-slate-600 mb-1.5">
                ความทึบ
              </label>
              <select
                id="stamp-opacity"
                value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
                className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {STAMP_OPACITIES.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-slate-200 bg-slate-50 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200/70 rounded-lg"
          >
            ยกเลิก
          </button>
          <button
            type="button"
            disabled={submitting || !text.trim()}
            onClick={() => void handleConfirm()}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
          >
            {submitting ? "กำลังสร้าง..." : "วางตราประทับ"}
          </button>
        </div>
      </div>
    </div>
  );
}
