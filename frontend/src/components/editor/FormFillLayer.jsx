import React from "react";

/**
 * ชั้นช่องกรอกแบบฟอร์ม AcroForm ซ้อนตรงตำแหน่งฟิลด์จริงบน PDFCanvas
 * รองรับ Text (บรรทัดเดียว/หลายบรรทัด), Checkbox, Radio, Dropdown/Listbox
 */
export default function FormFillLayer({
  fields,
  draftValues,
  zoom,
  onChange,
}) {
  if (!fields || fields.length === 0) return null;

  return (
    <div
      className="absolute inset-0 z-30 pointer-events-none"
      data-testid="form-fill-layer"
    >
      {fields.map((field) => {
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
    </div>
  );
}
