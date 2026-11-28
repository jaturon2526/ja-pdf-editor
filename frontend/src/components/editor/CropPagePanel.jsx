import React, { useState } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";
import { ptToMm } from "../../utils/cropGeometry.js";

const PRESETS = [
  { labelKey: "editor.panels.crop.preset10mm", mm: 10 },
  { labelKey: "editor.panels.crop.preset20mm", mm: 20 },
  { labelKey: "editor.panels.crop.presetFull", mm: 0 },
];

const SIDES = [
  { key: "top", labelKey: "editor.panels.crop.sideTop" },
  { key: "bottom", labelKey: "editor.panels.crop.sideBottom" },
  { key: "left", labelKey: "editor.panels.crop.sideLeft" },
  { key: "right", labelKey: "editor.panels.crop.sideRight" },
];

/**
 * แผงควบคุมการตัดขอบหน้ากระดาษ (เดสก์ท็อป: แผงด้านขวา · มือถือ: bottom sheet ย่อ/ขยายได้)
 */
export default function CropPagePanel({ hook, onClose }) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);

  const remainW = ptToMm(Math.max(0, hook.pageWidthPt - hook.margins.left - hook.margins.right));
  const remainH = ptToMm(Math.max(0, hook.pageHeightPt - hook.margins.top - hook.margins.bottom));

  return (
    <aside
      aria-label={t("editor.panels.crop.panelAria")}
      className="w-72 bg-white border-l border-slate-200 flex flex-col shrink-0 z-30 shadow-sm phone:fixed phone:inset-x-0 phone:bottom-0 phone:w-full phone:border-l-0 phone:border-t phone:rounded-t-2xl phone:shadow-2xl phone:z-40 phone:max-h-[55dvh]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-slate-800 truncate">{t("editor.panels.crop.title")}</span>
          <span className="text-[11px] text-slate-500 whitespace-nowrap">
            {t("editor.panels.crop.sizeCompact", { w: remainW, h: remainH })}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="desk:hidden px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
            aria-label={collapsed ? t("editor.panels.crop.expandAria") : t("editor.panels.crop.collapseAria")}
          >
            {collapsed ? t("editor.panels.crop.expand") : t("editor.panels.crop.collapse")}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("editor.panels.crop.closeAria")}
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
            <div className="text-slate-600 font-medium mb-1.5">{t("editor.panels.crop.quickPresets")}</div>
            <div className="flex gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p.mm}
                  type="button"
                  onClick={() => hook.setPresetMm(p.mm)}
                  className="flex-1 px-2 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-700 font-medium"
                >
                  {t(p.labelKey)}
                </button>
              ))}
            </div>
          </div>

          {/* 4 Margin Inputs (mm) */}
          <div>
            <div className="text-slate-600 font-medium mb-1.5">{t("editor.panels.crop.marginsLabel")}</div>
            <div className="grid grid-cols-2 gap-2">
              {SIDES.map((side) => {
                const sideLabel = t(side.labelKey);
                return (
                  <label key={side.key} className="block">
                    <span className="text-[11px] text-slate-500">{sideLabel}</span>
                    <input
                      type="number"
                      min="0"
                      step="1"
                      aria-label={t("editor.panels.crop.sideAria", { side: sideLabel })}
                      value={ptToMm(hook.margins[side.key])}
                      onChange={(e) => hook.setSideMm(side.key, e.target.value)}
                      className="mt-0.5 w-full px-2 py-1.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </label>
                );
              })}
            </div>
          </div>

          {/* Scope */}
          <div>
            <div className="text-slate-600 font-medium mb-1.5">{t("editor.panels.crop.applyToPages")}</div>
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="crop-scope"
                  value="current"
                  checked={hook.scope === "current"}
                  onChange={() => hook.setScope("current")}
                />
                <span>{t("editor.panels.crop.scopeCurrent", { page: hook.currentPage + 1 })}</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="crop-scope"
                  value="all"
                  checked={hook.scope === "all"}
                  onChange={() => hook.setScope("all")}
                />
                <span>{t("editor.panels.crop.scopeAll", { count: hook.pageCount })}</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="crop-scope"
                  value="range"
                  checked={hook.scope === "range"}
                  onChange={() => hook.setScope("range")}
                />
                <span>{t("editor.panels.crop.scopeRange")}</span>
              </label>
              {hook.scope === "range" && (
                <input
                  type="text"
                  aria-label={t("editor.panels.crop.rangeAria")}
                  value={hook.rangeText}
                  onChange={(e) => {
                    hook.setRangeText(e.target.value);
                    hook.setError("");
                  }}
                  placeholder={t("editor.panels.crop.rangePlaceholder", { count: hook.pageCount })}
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
          {t("editor.panels.crop.cancel")}
        </button>
        <button
          type="button"
          disabled={hook.applying}
          onClick={() => void hook.apply()}
          className="flex-1 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
        >
          {hook.applying ? t("editor.panels.crop.applying") : t("editor.panels.crop.apply")}
        </button>
      </div>
    </aside>
  );
}
