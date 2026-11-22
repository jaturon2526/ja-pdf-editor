import React, { useState } from "react";
import { ptToMm } from "../../utils/cropGeometry.js";

const PRESETS = [
  { label: "10 มม.", mm: 10 },
  { label: "20 มม.", mm: 20 },
  { label: "เต็มหน้า", mm: 0 },
];

/**
 * แผงควบคุมการตัดขอบหน้ากระดาษ (เดสก์ท็อป: แผงด้านขวา · มือถือ: bottom sheet ย่อ/ขยายได้)
 */
export default function CropPagePanel({ hook, onClose }) {
  const [collapsed, setCollapsed] = useState(false);

  const remainW = ptToMm(Math.max(0, hook.pageWidthPt - hook.margins.left - hook.margins.right));
  const remainH = ptToMm(Math.max(0, hook.pageHeightPt - hook.margins.top - hook.margins.bottom));

  return (
    <aside
      aria-label="แผงตัดขอบหน้ากระดาษ"
      className="w-72 bg-white border-l border-slate-200 flex flex-col shrink-0 z-30 shadow-sm phone:fixed phone:inset-x-0 phone:bottom-0 phone:w-full phone:border-l-0 phone:border-t phone:rounded-t-2xl phone:shadow-2xl phone:z-40 phone:max-h-[55dvh]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-slate-800 truncate">ตัดขอบหน้ากระดาษ</span>
          <span className="text-[11px] text-slate-500 whitespace-nowrap">
            {remainW}×{remainH} มม.
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="desk:hidden px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
            aria-label={collapsed ? "ขยายแผงตัดขอบ" : "ย่อแผงตัดขอบ"}
          >
            {collapsed ? "ขยาย" : "ย่อ"}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิดแผงตัดขอบหน้ากระดาษ"
            className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="p-3.5 space-y-3.5 overflow-y-auto flex-1 text-xs">
          {/* Quick Presets */}
          <div>
            <div className="text-slate-600 font-medium mb-1.5">ระยะตัดขอบด่วน</div>
            <div className="flex gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p.mm}
                  type="button"
                  onClick={() => hook.setPresetMm(p.mm)}
                  className="flex-1 px-2 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 font-medium"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* 4 Margin Inputs (mm) */}
          <div>
            <div className="text-slate-600 font-medium mb-1.5">ระยะตัดขอบแต่ละด้าน (มม.)</div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { key: "top", label: "บน" },
                { key: "bottom", label: "ล่าง" },
                { key: "left", label: "ซ้าย" },
                { key: "right", label: "ขวา" },
              ].map((side) => (
                <label key={side.key} className="block">
                  <span className="text-[11px] text-slate-500">{side.label}</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    aria-label={`ระยะตัดขอบด้าน${side.label} (มม.)`}
                    value={ptToMm(hook.margins[side.key])}
                    onChange={(e) => hook.setSideMm(side.key, e.target.value)}
                    className="mt-0.5 w-full px-2 py-1.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </label>
              ))}
            </div>
          </div>

          {/* Scope */}
          <div>
            <div className="text-slate-600 font-medium mb-1.5">ใช้กับหน้า</div>
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="crop-scope"
                  value="current"
                  checked={hook.scope === "current"}
                  onChange={() => hook.setScope("current")}
                />
                <span>หน้านี้ (หน้า {hook.currentPage + 1})</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="crop-scope"
                  value="all"
                  checked={hook.scope === "all"}
                  onChange={() => hook.setScope("all")}
                />
                <span>ทุกหน้า ({hook.pageCount} หน้า)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="crop-scope"
                  value="range"
                  checked={hook.scope === "range"}
                  onChange={() => hook.setScope("range")}
                />
                <span>ช่วงหน้า</span>
              </label>
              {hook.scope === "range" && (
                <input
                  type="text"
                  aria-label="ระบุช่วงหน้าที่จะตัดขอบ"
                  value={hook.rangeText}
                  onChange={(e) => {
                    hook.setRangeText(e.target.value);
                    hook.setError("");
                  }}
                  placeholder={`เช่น 1-${hook.pageCount} หรือ 1-3, 5`}
                  className="w-full px-2.5 py-1.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}
            </div>
          </div>

          {hook.error && (
            <div role="alert" className="text-red-600 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2">
              {hook.error}
            </div>
          )}
        </div>
      )}

      {/* Footer Actions */}
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-t border-slate-200 bg-slate-50 shrink-0">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-300 hover:bg-slate-100 rounded-lg"
        >
          ยกเลิก
        </button>
        <button
          type="button"
          disabled={hook.applying}
          onClick={() => void hook.apply()}
          className="flex-1 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
        >
          {hook.applying ? "กำลังตัดขอบ..." : "ตัดขอบ"}
        </button>
      </div>
    </aside>
  );
}
