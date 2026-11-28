import React, { useState } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";

function computeDraggedRect(startRect, kind, dx, dy, pageWidthPt, pageHeightPt) {
  if (kind === "move") {
    const w = startRect.x1 - startRect.x0;
    const h = startRect.y1 - startRect.y0;
    const nx0 = Math.max(0, Math.min(pageWidthPt - w, startRect.x0 + dx));
    const ny0 = Math.max(0, Math.min(pageHeightPt - h, startRect.y0 + dy));
    return { x0: Math.round(nx0), y0: Math.round(ny0), x1: Math.round(nx0 + w), y1: Math.round(ny0 + h) };
  }
  const nx1 = Math.max(startRect.x0 + 16, Math.min(pageWidthPt, startRect.x1 + dx));
  const ny1 = Math.max(startRect.y0 + 16, Math.min(pageHeightPt, startRect.y1 + dy));
  return { ...startRect, x1: Math.round(nx1), y1: Math.round(ny1) };
}

function DraftFieldBox({ draftField, zoom, pageWidthPt, pageHeightPt, onRectChange, onConfirm, onCancel }) {
  const { t } = useI18n();
  const { rect, label } = draftField;
  const left = rect.x0 * zoom;
  const top = rect.y0 * zoom;
  const width = Math.max(16, (rect.x1 - rect.x0) * zoom);
  const height = Math.max(16, (rect.y1 - rect.y0) * zoom);

  function startPointer(kind, e) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...rect };
    const pointerId = e.pointerId;

    function onMove(ev) {
      if (ev.pointerId !== pointerId) return;
      const dx = (ev.clientX - startX) / zoom;
      const dy = (ev.clientY - startY) / zoom;
      onRectChange(computeDraggedRect(startRect, kind, dx, dy, pageWidthPt, pageHeightPt));
    }

    function onUp(ev) {
      if (ev.pointerId !== pointerId) return;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  return (
    <div
      data-testid="form-draft-box"
      className="absolute pointer-events-auto border-2 border-dashed border-blue-600 bg-blue-100/70 rounded cursor-move touch-none select-none z-40"
      style={{ left, top, width, height }}
      onPointerDown={(e) => startPointer("move", e)}
    >
      <span className="block px-1.5 py-0.5 text-[11px] font-medium text-blue-900 truncate pointer-events-none">
        {label}
      </span>
      <div
        role="presentation"
        title={t("editor.panels.formFill.resizeDraftTitle")}
        onPointerDown={(e) => startPointer("resize", e)}
        className="absolute -right-2 -bottom-2 w-4 h-4 rounded-full bg-blue-600 border-2 border-white cursor-nwse-resize touch-none shadow"
      />
      <div
        className="absolute left-0 flex items-center gap-1 mt-1"
        style={{ top: "100%" }}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={() => void onConfirm()}
          className="px-2 py-0.5 text-[11px] font-medium bg-blue-600 hover:bg-blue-700 text-white rounded shadow whitespace-nowrap"
        >
          {t("editor.panels.formFill.placeBoxBtn")}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-2 py-0.5 text-[11px] font-medium bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 rounded shadow whitespace-nowrap"
        >
          {t("editor.panels.formFill.cancelBtn")}
        </button>
      </div>
    </div>
  );
}

/**
 * ช่องฟอร์มที่วางไปแล้วในโหมด "ออกแบบฟอร์ม" — ลากย้ายตำแหน่งและดึงมุมขวาล่างเพื่อปรับขนาดได้ทันที (v1.47.3)
 */
function PlacedDesignBox({ field, zoom, pageWidthPt, pageHeightPt, onMoveField }) {
  const { t } = useI18n();
  const [liveRect, setLiveRect] = useState(null);
  const rect = liveRect || field.rect;
  const left = rect.x0 * zoom;
  const top = rect.y0 * zoom;
  const width = Math.max(16, (rect.x1 - rect.x0) * zoom);
  const height = Math.max(16, (rect.y1 - rect.y0) * zoom);

  function startPointer(kind, e) {
    if (field.read_only) return;
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...field.rect };
    const pointerId = e.pointerId;
    let latestRect = startRect;
    let changed = false;

    function onMove(ev) {
      if (ev.pointerId !== pointerId) return;
      const dx = (ev.clientX - startX) / zoom;
      const dy = (ev.clientY - startY) / zoom;
      if (!changed && Math.hypot(dx, dy) < 2) return;
      changed = true;
      latestRect = computeDraggedRect(startRect, kind, dx, dy, pageWidthPt, pageHeightPt);
      setLiveRect(latestRect);
    }

    function onUp(ev) {
      if (ev.pointerId !== pointerId) return;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      setLiveRect(null);
      if (changed && onMoveField) {
        void onMoveField(field, latestRect);
      }
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  return (
    <div
      data-testid={`form-design-field-${field.xref}`}
      title={t("editor.panels.formFill.moveOrResizeFieldTitle", { label: field.label })}
      onPointerDown={(e) => startPointer("move", e)}
      className={`absolute pointer-events-auto rounded border-2 cursor-move touch-none select-none transition-colors ${
        liveRect
          ? "border-blue-600 bg-blue-100/75 shadow-md z-40"
          : "border-dashed border-sky-500 bg-sky-100/45 hover:bg-sky-100/75 hover:border-blue-600 z-30"
      }`}
      style={{ left, top, width, height }}
    >
      <span className="block px-1 py-0.5 text-[10px] font-medium text-sky-900 truncate pointer-events-none">
        {field.label}
      </span>
      {!field.read_only && (
        <div
          role="presentation"
          title={t("editor.panels.formFill.resizeFieldTitle", { label: field.label })}
          onPointerDown={(e) => startPointer("resize", e)}
          className="absolute -right-2 -bottom-2 w-4 h-4 rounded-full bg-white border-2 border-blue-600 cursor-nwse-resize touch-none shadow"
        />
      )}
    </div>
  );
}

/**
 * ชั้นช่องกรอกแบบฟอร์ม AcroForm ซ้อนตรงตำแหน่งฟิลด์จริงบน PDFCanvas
 * - mode === "fill": แสดงอินพุตจริงให้กรอกบนหน้า (v1.45.0)
 * - mode === "design": แสดงกล่องลากย้าย/ปรับขนาดได้สำหรับทุกช่องที่วางไว้ + กล่องวางช่องใหม่ (v1.47.3)
 */
export default function FormFillLayer({
  fields,
  draftValues,
  mode = "fill",
  draftField = null,
  zoom,
  pageWidthPt = 595,
  pageHeightPt = 842,
  onChange,
  onMoveField,
  onDraftRectChange,
  onCommitDraftField,
  onCancelDraftField,
}) {
  if ((!fields || fields.length === 0) && !draftField) return null;

  return (
    <div
      className="absolute inset-0 z-30 pointer-events-none"
      data-testid="form-fill-layer"
    >
      {mode === "design"
        ? (fields || []).map((field) => (
          <PlacedDesignBox
            key={field.xref}
            field={field}
            zoom={zoom}
            pageWidthPt={pageWidthPt}
            pageHeightPt={pageHeightPt}
            onMoveField={onMoveField}
          />
        ))
        : (fields || []).map((field) => {
          const left = field.rect.x0 * zoom;
          const top = field.rect.y0 * zoom;
          const width = Math.max(16, (field.rect.x1 - field.rect.x0) * zoom);
          const height = Math.max(16, (field.rect.y1 - field.rect.y0) * zoom);
          const val = draftValues[field.xref] ?? field.value;
          const isDirty = val !== field.value;
          const borderClass = isDirty
            ? "border-blue-600 ring-2 ring-blue-300/60 bg-blue-50/90"
            : "border-sky-400/80 bg-sky-50/75 hover:bg-white/90 focus:bg-white";

          if (field.type === "checkbox" || field.type === "radio") {
            return (
              <label
                key={field.xref}
                title={field.label}
                className={`absolute pointer-events-auto flex items-center justify-center rounded border cursor-pointer ${borderClass}`}
                style={{ left, top, width, height }}
              >
                <input
                  type={field.type}
                  name={field.type === "radio" ? `pdf-radio-${field.name}` : undefined}
                  aria-label={field.label}
                  disabled={field.read_only}
                  checked={!!val}
                  onChange={(e) => onChange(field, e.target.checked)}
                  className="w-4 h-4 accent-blue-600 cursor-pointer"
                />
              </label>
            );
          }

          if (field.type === "dropdown" || field.type === "listbox") {
            return (
              <select
                key={field.xref}
                aria-label={field.label}
                title={field.label}
                disabled={field.read_only}
                value={String(val ?? "")}
                onChange={(e) => onChange(field, e.target.value)}
                className={`absolute pointer-events-auto rounded border px-1 text-slate-900 focus:outline-none ${borderClass}`}
                style={{
                  left,
                  top,
                  width,
                  height,
                  fontSize: Math.max(10, Math.min(14, height * 0.55)),
                }}
              >
                {field.options.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            );
          }

          const fontSize = Math.max(10, Math.min(15, field.multiline ? 12 : height * 0.58));
          if (field.multiline) {
            return (
              <textarea
                key={field.xref}
                aria-label={field.label}
                title={field.label}
                disabled={field.read_only}
                maxLength={field.max_len || undefined}
                value={String(val ?? "")}
                onChange={(e) => onChange(field, e.target.value)}
                className={`absolute pointer-events-auto rounded border px-1.5 py-0.5 text-slate-900 resize-none focus:outline-none ${borderClass}`}
                style={{ left, top, width, height, fontSize }}
              />
            );
          }

          return (
            <input
              key={field.xref}
              type="text"
              aria-label={field.label}
              title={field.label}
              disabled={field.read_only}
              maxLength={field.max_len || undefined}
              value={String(val ?? "")}
              onChange={(e) => onChange(field, e.target.value)}
              className={`absolute pointer-events-auto rounded border px-1.5 text-slate-900 focus:outline-none ${borderClass}`}
              style={{ left, top, width, height, fontSize }}
            />
          );
        })}

      {draftField && (
        <DraftFieldBox
          draftField={draftField}
          zoom={zoom}
          pageWidthPt={pageWidthPt}
          pageHeightPt={pageHeightPt}
          onRectChange={onDraftRectChange}
          onConfirm={onCommitDraftField}
          onCancel={onCancelDraftField}
        />
      )}
    </div>
  );
}
