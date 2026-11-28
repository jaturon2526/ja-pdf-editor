// แยกหน้าเอกสาร (เมนู หน้า > แยกหน้าเอกสาร) — ระบุหน้า เช่น "1-3, 5" แล้วดาวน์โหลดเป็น PDF (ไฟล์เดียว/ไฟล์ละหน้า .zip)
// หรือรูปภาพ PNG/JPG หน้าละรูป (หน้าเดียว = ไฟล์รูปตรง ๆ ใช้บนมือถือสะดวก · หลายหน้า = .zip)
// - ลำดับตามที่พิมพ์ ("5, 1-3" → หน้า 5,1,2,3) · ช่วงถอยหลังได้ ("6-4") · "-3" = หน้า 1-3 · "8-" = หน้า 8 ถึงหน้าสุดท้าย
// - ตรวจเลขหน้ากับจำนวนหน้าจริงก่อนส่ง และแสดงสรุปว่าจะได้หน้าไหนบ้าง (กฎเดียวกับ backend parse_page_range)
// - ไฟล์ที่ได้มีการแก้ไขล่าสุด (ยังไม่บันทึกก็ได้) ช่องกรอกฟอร์ม/ลิงก์/บุ๊กมาร์กยังอยู่ และใส่รหัสผ่านเดียวกับเอกสาร ถ้าตั้งไว้
import { useEffect, useRef, useState } from "react";  // Esc ปิดผ่าน useEscapeStack ใน Editor
import { useI18n } from "../i18n/I18nContext.jsx";
import { translate } from "../i18n/index.js";
import thDict from "../i18n/locales/th.json";

const defaultT = (key, params) => translate(thDict, thDict, key, params);

/** แปลงข้อความช่วงหน้าเป็นเลขหน้า (1-based) ตามลำดับที่พิมพ์ ไม่ซ้ำ — คืน { pages } หรือ { error } */
export function parsePageRange(text, total, t = defaultT) {
  const norm = String(text || "")
    .replace(/[\u0E50-\u0E59]/g, (d) => String(d.charCodeAt(0) - 0x0E50))
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
    if (!/^\d+$/.test(tok)) throw new Error(t("editor.modals.extract.errInvalidPage", { part }));
    const n = Number(tok);
    if (n < 1 || n > total) throw new Error(t("editor.modals.extract.errNoPage", { page: n, total }));
    return n;
  };
  try {
    for (const part of norm.split(",")) {
      if (!part) continue;
      if (part.includes("-")) {
        const bits = part.split("-");
        if (bits.length !== 2 || (!bits[0] && !bits[1])) {
          throw new Error(t("editor.modals.extract.errInvalidRange", { part }));
        }
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
  return pages.length ? { pages } : { error: t("editor.modals.extract.errEmptyRange") };
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
  { value: "single", labelKey: "editor.modals.extract.modeSingleLabel", hintKey: "editor.modals.extract.modeSingleHint" },
  { value: "split", labelKey: "editor.modals.extract.modeSplitLabel", hintKey: "editor.modals.extract.modeSplitHint" },
];

const FORMATS = [
  { value: "pdf", labelKey: "editor.modals.extract.formatPdf" },
  { value: "png", labelKey: "editor.modals.extract.formatPng" },
  { value: "jpg", labelKey: "editor.modals.extract.formatJpg" },
];

const QUALITIES = [
  { value: 100, labelKey: "editor.modals.extract.dpi100" },
  { value: 150, labelKey: "editor.modals.extract.dpi150" },
  { value: 300, labelKey: "editor.modals.extract.dpi300" },
];

function getSubmitLabel({ submitting, isImage, mode, count, t }) {
  if (submitting) {
    return isImage ? t("editor.modals.extract.submittingImages") : t("editor.modals.extract.submittingPages");
  }
  if (isImage) {
    return count > 1
      ? t("editor.modals.extract.downloadImagesZip", { count })
      : t("editor.modals.extract.downloadImage");
  }
  if (mode === "split" && count > 1) {
    return t("editor.modals.extract.downloadFilesZip", { count });
  }
  return t("editor.modals.extract.download");
}

function ExtractPagesForm({ onClose, onExtract, totalPages, currentPage }) {
  const { t } = useI18n();
  const [pageRange, setPageRange] = useState("");
  const [mode, setMode] = useState("single");
  const [format, setFormat] = useState("pdf");
  const [dpi, setDpi] = useState(150);
  const isImage = format !== "pdf";
  const [touched, setTouched] = useState(false);
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const rangeInputRef = useRef(null);

  useEffect(() => {
    rangeInputRef.current?.focus();
  }, []);

  const parsed = parsePageRange(pageRange, totalPages, t);
  const showError = (touched || pageRange.trim()) && parsed.error;

  async function handleSubmit(e) {
    e.preventDefault();
    setTouched(true);
    if (parsed.error || submitting) return;
    setSubmitting(true);
    setServerError("");
    try {
      await onExtract(pageRange, mode, format, dpi);
    } catch (err) {
      setServerError(err.message || t("editor.modals.extract.errFailed"));
      setSubmitting(false);
    }
  }

  const chip = "px-2.5 py-1 min-h-[32px] text-xs rounded-full border border-gray-300 text-gray-700 hover:bg-gray-50";
  const count = parsed.pages?.length || 0;
  const submitLabel = getSubmitLabel({ submitting, isImage, mode, count, t });

  return (
    <div role="presentation" className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && onClose()}>
      <form role="dialog" aria-modal="true" aria-labelledby="extract-title" onSubmit={(e) => void handleSubmit(e)}
        className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92dvh]">
        <div className="p-4 border-b border-gray-100">
          <h2 id="extract-title" className="text-lg font-bold text-gray-900">{t("editor.modals.extract.title")}</h2>
          <p className="mt-1 text-sm text-gray-500">{t("editor.modals.extract.subtitle")}</p>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto">
          <div>
            <label htmlFor="extract-range" className="block text-sm font-medium text-gray-800">
              {t("editor.modals.extract.pagesLabel")}{" "}
              <span className="font-normal text-gray-500">{t("editor.modals.extract.totalPagesHint", { total: totalPages })}</span>
            </label>
            <input ref={rangeInputRef} id="extract-range" type="text" inputMode="text" autoComplete="off" maxLength={500}
              placeholder={t("editor.modals.extract.rangePlaceholder")}
              aria-invalid={showError ? "true" : "false"}
              value={pageRange}
              onChange={(e) => { setPageRange(e.target.value); setServerError(""); }}
              className={`mt-1 block w-full px-3 py-2 border rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-1 ${showError ? "border-red-400 focus:ring-red-500 focus:border-red-500" : "border-gray-300 focus:ring-blue-500 focus:border-blue-500"}`} />
            <div className="mt-2 flex flex-wrap gap-1.5">
              {currentPage >= 1 && totalPages > 1 && (
                <button type="button" className={chip} onClick={() => setPageRange(String(currentPage))}>
                  {t("editor.modals.extract.thisPage", { page: currentPage })}
                </button>
              )}
              <button type="button" className={chip} onClick={() => setPageRange(`1-${totalPages}`)}>
                {t("editor.modals.extract.allPages")}
              </button>
              {totalPages > 1 && (
                <button type="button" className={chip} onClick={() => setPageRange(`${totalPages}-1`)}>
                  {t("editor.modals.extract.allPagesReversed")}
                </button>
              )}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              {t("editor.modals.extract.rangeHelpPrefix")} <code>5, 1-3</code> {t("editor.modals.extract.rangeHelpSuffix")}
            </p>
            {showError && (
              <p className="mt-1 text-sm text-red-600" role="alert">{parsed.error}</p>
            )}
            {!showError && count > 0 && (
              <p className="mt-1 text-sm text-gray-700" data-testid="extract-summary">
                {t("editor.modals.extract.summaryPrefix")}{" "}
                <strong>{t("editor.modals.extract.summaryCount", { count })}</strong>: {rangeLabel(parsed.pages)}
              </p>
            )}
          </div>

          <fieldset>
            <legend className="text-sm font-medium text-gray-800 mb-1.5">{t("editor.modals.extract.fileTypeLabel")}</legend>
            <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t("editor.modals.extract.fileTypeLabel")}>
              {FORMATS.map((f) => (
                <button key={f.value} type="button" role="radio" aria-checked={format === f.value}
                  onClick={() => { setFormat(f.value); setServerError(""); }}
                  className={`min-h-[40px] rounded-lg border text-sm font-medium ${format === f.value ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`}>
                  {t(f.labelKey)}
                </button>
              ))}
            </div>
          </fieldset>

          {isImage ? (
            <div data-testid="extract-image-options">
              <label htmlFor="extract-dpi" className="block text-sm font-medium text-gray-800">{t("editor.modals.extract.resolutionLabel")}</label>
              <select id="extract-dpi" value={dpi} onChange={(e) => setDpi(Number(e.target.value))}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white">
                {QUALITIES.map((q) => <option key={q.value} value={q.value}>{t(q.labelKey)}</option>)}
              </select>
              <p className="mt-2 text-xs text-gray-500">
                {t("editor.modals.extract.imageHintBase")}
                {format === "jpg" ? t("editor.modals.extract.imageHintJpg") : t("editor.modals.extract.imageHintPng")}
              </p>
            </div>
          ) : (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-gray-800 mb-1">{t("editor.modals.extract.fileModeLabel")}</legend>
              {MODES.map((m) => (
                <label key={m.value}
                  className={`grid grid-cols-[auto_1fr] gap-x-3 items-start p-3 rounded-lg border cursor-pointer ${mode === m.value ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:bg-gray-50"}`}>
                  <input type="radio" name="extract-mode" className="mt-1 row-span-2" value={m.value} checked={mode === m.value}
                    onChange={() => setMode(m.value)} />
                  <span className="block text-sm font-medium text-gray-900">{t(m.labelKey)}</span>
                  <span className="block text-xs text-gray-500">{t(m.hintKey)}</span>
                </label>
              ))}
            </fieldset>
          )}
          {serverError && <p className="text-sm text-red-600" role="alert">{serverError}</p>}
        </div>

        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
            {t("editor.modals.extract.cancel")}
          </button>
          <button type="submit" disabled={submitting || (touched && !!parsed.error)}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
            {submitLabel}
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
