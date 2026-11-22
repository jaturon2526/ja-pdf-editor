import React, { useState } from "react";

function renderFieldControl(field, val, onChange) {
  if (field.type === "checkbox" || field.type === "radio") {
    return (
      <label className="inline-flex items-center gap-2 cursor-pointer select-none">
        <input
          type={field.type}
          name={field.type === "radio" ? `panel-radio-${field.name}` : undefined}
          disabled={field.read_only}
          checked={!!val}
          onChange={(e) => onChange(field, e.target.checked)}
          className="w-4 h-4 accent-blue-600"
        />
        <span className="text-xs text-slate-700">{field.label}</span>
      </label>
    );
  }
  if (field.type === "dropdown" || field.type === "listbox") {
    return (
      <label className="block">
        <span className="text-[11px] font-medium text-slate-600">{field.label}</span>
        <select
          disabled={field.read_only}
          value={String(val ?? "")}
          onChange={(e) => onChange(field, e.target.value)}
          className="mt-0.5 w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {field.options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (field.multiline) {
    return (
      <label className="block">
        <span className="text-[11px] font-medium text-slate-600">{field.label}</span>
        <textarea
          rows={2}
          disabled={field.read_only}
          maxLength={field.max_len || undefined}
          value={String(val ?? "")}
          onChange={(e) => onChange(field, e.target.value)}
          className="mt-0.5 w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </label>
    );
  }
  return (
    <label className="block">
      <span className="text-[11px] font-medium text-slate-600">{field.label}</span>
      <input
        type="text"
        disabled={field.read_only}
        maxLength={field.max_len || undefined}
        value={String(val ?? "")}
        onChange={(e) => onChange(field, e.target.value)}
        className="mt-0.5 w-full px-2 py-1.5 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </label>
  );
}

/**
 * แผงกรอกแบบฟอร์ม PDF (เดสก์ท็อป: แผงขวา · มือถือ: bottom sheet ย่อ/ขยายได้)
 */
export default function FormFillPanel({
  hook,
  currentPage,
  onSelectPage,
  onSwitchToInsertText,
  onClose,
}) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      aria-label="แผงกรอกแบบฟอร์ม PDF"
      className="w-72 bg-white border-l border-slate-200 flex flex-col shrink-0 z-30 shadow-sm phone:fixed phone:inset-x-0 phone:bottom-0 phone:w-full phone:border-l-0 phone:border-t phone:rounded-t-2xl phone:shadow-2xl phone:z-40 phone:max-h-[55dvh]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-slate-800 truncate">กรอกแบบฟอร์ม</span>
          <span className="text-[11px] text-slate-500 whitespace-nowrap">
            {hook.fields.length} ช่อง
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="desk:hidden px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded"
            aria-label={collapsed ? "ขยายแผงแบบฟอร์ม" : "ย่อแผงแบบฟอร์ม"}
          >
            {collapsed ? "ขยาย" : "ย่อ"}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิดแผงกรอกแบบฟอร์ม"
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
        <div className="p-3.5 space-y-3 overflow-y-auto flex-1 text-xs">
          {hook.loading && (
            <div className="text-slate-500 py-4 text-center">กำลังตรวจหาช่องแบบฟอร์ม...</div>
          )}

          {!hook.loading && hook.fields.length === 0 && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2 text-slate-600">
              <p className="font-medium text-slate-700">ไม่พบช่องแบบฟอร์ม (AcroForm) ในเอกสารนี้</p>
              <p className="leading-relaxed">
                เอกสารนี้อาจเป็นไฟล์ PDF ทั่วไปที่ไม่ได้สร้างช่องกรอกไว้ คุณสามารถใช้เครื่องมือ <strong>แทรกข้อความ</strong> เพื่อพิมพ์ทับลงบนแบบฟอร์มได้ทันที
              </p>
              <button
                type="button"
                onClick={onSwitchToInsertText}
                className="w-full px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg"
              >
                เปลี่ยนไปใช้ “แทรกข้อความ”
              </button>
            </div>
          )}

          {!hook.loading && hook.pagesWithFields.length > 1 && (
            <div>
              <div className="text-[11px] text-slate-500 mb-1">หน้าที่มีช่องแบบฟอร์ม</div>
              <div className="flex flex-wrap gap-1">
                {hook.pagesWithFields.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => onSelectPage(p)}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium border ${
                      p === currentPage
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                    }`}
                  >
                    หน้า {p + 1}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!hook.loading && hook.fields.length > 0 && hook.pageFields.length === 0 && (
            <div className="text-slate-500 text-center py-3">
              หน้า {currentPage + 1} ไม่มีช่องกรอกฟอร์ม — เลือกหน้าที่มีฟอร์มด้านบน
            </div>
          )}

          {!hook.loading && hook.pageFields.length > 0 && (
            <div className="space-y-2.5">
              {hook.pageFields.map((field) => {
                const val = hook.draftValues[field.xref] ?? field.value;
                return (
                  <div
                    key={field.xref}
                    className={`p-2 rounded-lg border ${
                      val !== field.value ? "border-blue-300 bg-blue-50/40" : "border-slate-200 bg-white"
                    }`}
                  >
                    {renderFieldControl(field, val, hook.setFieldValue)}
                  </div>
                );
              })}
            </div>
          )}

          {hook.error && (
            <div role="alert" className="text-red-600 bg-red-50 border border-red-200 rounded-lg px-2.5 py-2">
              {hook.error}
            </div>
          )}
        </div>
      )}

      {/* Footer Actions */}
      <div className="flex items-center gap-2 px-3.5 py-2.5 border-t border-slate-200 bg-slate-50 shrink-0">
        {hook.dirtyCount > 0 ? (
          <button
            type="button"
            onClick={hook.resetDraft}
            className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-300 hover:bg-slate-100 rounded-lg"
          >
            ล้างค่าที่แก้
          </button>
        ) : (
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-300 hover:bg-slate-100 rounded-lg"
          >
            ปิด
          </button>
        )}
        <button
          type="button"
          disabled={hook.saving || hook.dirtyCount === 0}
          onClick={() => void hook.save()}
          className="flex-1 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
        >
          {hook.saving
            ? "กำลังบันทึก..."
            : `บันทึกแบบฟอร์ม${hook.dirtyCount > 0 ? ` (${hook.dirtyCount})` : ""}`}
        </button>
      </div>
    </aside>
  );
}
