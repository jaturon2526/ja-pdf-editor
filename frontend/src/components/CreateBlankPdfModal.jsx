import React, { useEffect, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

const PT_PER_MM = 72 / 25.4;
const MIN_MM = 26; // ≈ 73.7 pt (backend >= 72 pt)
const MAX_MM = 5000; // ≈ 14,173 pt (backend <= 14,400 pt)

const PAPER_SIZES = [
  { id: "a4", labelKey: "createBlank.sizeA4", widthMm: 210, heightMm: 297 },
  { id: "letter", labelKey: "createBlank.sizeLetter", widthMm: 215.9, heightMm: 279.4 },
  { id: "a5", labelKey: "createBlank.sizeA5", widthMm: 148, heightMm: 210 },
  { id: "a3", labelKey: "createBlank.sizeA3", widthMm: 297, heightMm: 420 },
  { id: "custom", labelKey: "createBlank.sizeCustom", widthMm: 210, heightMm: 297 },
];

/**
 * หน้าต่างสร้างเอกสาร PDF หน้าเปล่า (v1.47.0, รองรับกำหนดขนาดเอง + แนวตั้ง/แนวนอน v1.47.1)
 */
export default function CreateBlankPdfModal({ onClose, onCreated, defaultOpenFormBuilder = true }) {
  const { t } = useI18n();
  const [filename, setFilename] = useState(() => t("createBlank.defaultFilename"));
  const [sizeId, setSizeId] = useState("a4");
  const [orientation, setOrientation] = useState("portrait"); // "portrait" | "landscape"
  const [customW, setCustomW] = useState("210");
  const [customH, setCustomH] = useState("297");
  const [pageCount, setPageCount] = useState(1);
  const [openFormBuilder, setOpenFormBuilder] = useState(defaultOpenFormBuilder);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  function handleSelectOrientation(nextOrient) {
    if (nextOrient === orientation) return;
    setOrientation(nextOrient);
    if (sizeId === "custom") {
      const w = Number(customW);
      const h = Number(customH);
      if (Number.isFinite(w) && Number.isFinite(h)) {
        const shouldSwap = (nextOrient === "landscape" && w < h) || (nextOrient === "portrait" && w > h);
        if (shouldSwap) {
          setCustomW(String(h));
          setCustomH(String(w));
        }
      }
    }
  }

  function resolveDimensionsPt() {
    if (sizeId === "custom") {
      const wMm = Number(customW);
      const hMm = Number(customH);
      if (!Number.isFinite(wMm) || !Number.isFinite(hMm) || wMm < MIN_MM || hMm < MIN_MM || wMm > MAX_MM || hMm > MAX_MM) {
        return { error: t("createBlank.dimError", { min: MIN_MM, max: MAX_MM }) };
      }
      return {
        width: Math.round(wMm * PT_PER_MM * 100) / 100,
        height: Math.round(hMm * PT_PER_MM * 100) / 100,
      };
    }
    const preset = PAPER_SIZES.find((s) => s.id === sizeId) || PAPER_SIZES[0];
    const wMm = orientation === "landscape" ? preset.heightMm : preset.widthMm;
    const hMm = orientation === "landscape" ? preset.widthMm : preset.heightMm;
    return {
      width: Math.round(wMm * PT_PER_MM * 100) / 100,
      height: Math.round(hMm * PT_PER_MM * 100) / 100,
    };
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    const dims = resolveDimensionsPt();
    if (dims.error) {
      setError(dims.error);
      return;
    }
    const cleanName = filename.trim() || t("createBlank.defaultFilename");
    const pages = Math.max(1, Math.min(50, Number(pageCount) || 1));

    setSubmitting(true);
    setError("");
    try {
      const res = await api.createBlankPdf({
        filename: cleanName,
        width: dims.width,
        height: dims.height,
        pageCount: pages,
      });
      onCreated(res, { openFormBuilder });
    } catch (err) {
      setError(err?.message || t("createBlank.createError"));
      setSubmitting(false);
    }
  }

  const preset = PAPER_SIZES.find((s) => s.id === sizeId) || PAPER_SIZES[0];
  let previewW = orientation === "landscape" ? preset.heightMm : preset.widthMm;
  let previewH = orientation === "landscape" ? preset.widthMm : preset.heightMm;
  if (sizeId === "custom") {
    previewW = customW || "?";
    previewH = customH || "?";
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 flex items-end sm:items-center justify-center sm:p-4"
      role="presentation"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && onClose()}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label={t("createBlank.ariaLabel")}
        onSubmit={(e) => void handleSubmit(e)}
        className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl shadow-2xl border border-slate-200 overflow-hidden"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
          <h2 className="text-base font-semibold text-slate-800">{t("createBlank.title")}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("createBlank.closeAria")}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            ✕
          </button>
        </div>

        <div className="p-4 space-y-3.5 text-sm">
          <div>
            <label htmlFor="blank-pdf-filename" className="block text-xs font-medium text-slate-600 mb-1">
              {t("createBlank.filenameLabel")}
            </label>
            <input
              id="blank-pdf-filename"
              type="text"
              value={filename}
              maxLength={200}
              onChange={(e) => setFilename(e.target.value)}
              placeholder={t("createBlank.filenamePlaceholder")}
              className="w-full h-10 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-3 items-end">
            <div className="col-span-2">
              <label htmlFor="blank-pdf-size" className="block text-xs font-medium text-slate-600 mb-1">
                {t("createBlank.paperSizeLabel")}
              </label>
              <select
                id="blank-pdf-size"
                value={sizeId}
                onChange={(e) => {
                  setSizeId(e.target.value);
                  setError("");
                }}
                className="w-full h-10 px-2.5 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PAPER_SIZES.map((s) => (
                  <option key={s.id} value={s.id}>
                    {t(s.labelKey)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="blank-pdf-pages" className="block text-xs font-medium text-slate-600 mb-1">
                {t("createBlank.pageCountLabel")}
              </label>
              <input
                id="blank-pdf-pages"
                type="number"
                min={1}
                max={50}
                value={pageCount}
                onChange={(e) => setPageCount(e.target.value)}
                className="w-full h-10 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* แนวตั้ง / แนวนอน */}
          <div>
            <div className="flex items-center justify-between text-xs font-medium text-slate-600 mb-1">
              <span>{t("createBlank.orientationLabel")}</span>
              <span className="text-[11px] font-normal text-slate-500">
                {previewW} × {previewH} {t("createBlank.mmUnit")}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                aria-pressed={orientation === "portrait"}
                onClick={() => handleSelectOrientation("portrait")}
                className={`h-9 rounded-lg border text-xs font-medium transition ${
                  orientation === "portrait"
                    ? "bg-blue-50 border-blue-500 text-blue-700"
                    : "bg-white border-slate-300 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {t("createBlank.portrait")}
              </button>
              <button
                type="button"
                aria-pressed={orientation === "landscape"}
                onClick={() => handleSelectOrientation("landscape")}
                className={`h-9 rounded-lg border text-xs font-medium transition ${
                  orientation === "landscape"
                    ? "bg-blue-50 border-blue-500 text-blue-700"
                    : "bg-white border-slate-300 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {t("createBlank.landscape")}
              </button>
            </div>
          </div>

          {/* ขนาดกำหนดเอง (มม.) */}
          {sizeId === "custom" && (
            <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200">
              <div>
                <label htmlFor="blank-pdf-custom-w" className="block text-xs font-medium text-slate-600 mb-1">
                  {t("createBlank.widthLabel")}
                </label>
                <input
                  id="blank-pdf-custom-w"
                  type="number"
                  min={MIN_MM}
                  max={MAX_MM}
                  step="1"
                  value={customW}
                  onChange={(e) => {
                    setCustomW(e.target.value);
                    setError("");
                  }}
                  className="w-full h-10 px-3 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label htmlFor="blank-pdf-custom-h" className="block text-xs font-medium text-slate-600 mb-1">
                  {t("createBlank.heightLabel")}
                </label>
                <input
                  id="blank-pdf-custom-h"
                  type="number"
                  min={MIN_MM}
                  max={MAX_MM}
                  step="1"
                  value={customH}
                  onChange={(e) => {
                    setCustomH(e.target.value);
                    setError("");
                  }}
                  className="w-full h-10 px-3 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none pt-1">
            <input
              type="checkbox"
              checked={openFormBuilder}
              onChange={(e) => setOpenFormBuilder(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <span>{t("createBlank.openFormBuilder")}</span>
          </label>

          {error && (
            <div role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-slate-200 bg-slate-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200/70 rounded-lg"
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
          >
            {submitting ? t("createBlank.creating") : t("createBlank.createBtn")}
          </button>
        </div>
      </form>
    </div>
  );
}
