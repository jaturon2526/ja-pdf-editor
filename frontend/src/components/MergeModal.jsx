// รวมไฟล์ PDF — เลือกได้ทั้งไฟล์จากเครื่องและไฟล์ใน "เอกสารของฉัน" เรียงลำดับ/ลบได้ แล้วรวมเป็นไฟล์ใหม่ในเอกสารของฉัน
import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";
import { formatBytes } from "../utils/format.js";

export const MERGE_MAX_FILES = 30;
// nginx รับ request ได้ 60 MB — ไฟล์จากเครื่องต้องอัปโหลด ส่วนไฟล์ในเอกสารของฉันอยู่บนเซิร์ฟเวอร์แล้ว
export const MERGE_MAX_UPLOAD = 55 * 1024 * 1024;

let seq = 0;
const isPdf = (f) => f.type === "application/pdf" || /\.pdf$/i.test(f.name);

export default function MergeModal({ onClose, onMerged, documents = [] }) {
  const { t } = useI18n();
  const [items, setItems] = useState([]); // {key, kind: "local"|"stored", file?, id?, name, size}
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState(() => new Set());
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const pdfDocs = useMemo(() => documents.filter((d) => /\.pdf$/i.test(d.filename || "")), [documents]);
  const uploadBytes = items.filter((i) => i.kind === "local").reduce((s, i) => s + (i.size || 0), 0);
  const totalBytes = items.reduce((s, i) => s + (i.size || 0), 0);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !loading && (picking ? setPicking(false) : onClose());
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, loading, picking]);

  function addLocal(fileList) {
    const all = Array.from(fileList || []);
    const pdfs = all.filter(isPdf);
    setError(all.length > pdfs.length ? t("mergeModal.skippedNonPdf", { count: all.length - pdfs.length }) : null);
    setItems((prev) => [...prev, ...pdfs.map((file) => ({ key: ++seq, kind: "local", file, name: file.name, size: file.size }))]);
  }

  function addPicked() {
    const add = pdfDocs.filter((d) => picked.has(d.id)).map((d) => ({ key: ++seq, kind: "stored", id: d.id, name: d.filename, size: d.file_size || 0 }));
    setItems((prev) => [...prev, ...add]);
    setPicked(new Set());
    setPicking(false);
    setError(null);
  }

  function move(index, delta) {
    setItems((prev) => {
      const j = index + delta;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[j]] = [next[j], next[index]];
      return next;
    });
  }

  const remove = (key) => setItems((prev) => prev.filter((i) => i.key !== key));

  let problem = null;
  if (items.length < 2) {
    problem = t("mergeModal.needTwoFiles");
  } else if (items.length > MERGE_MAX_FILES) {
    problem = t("mergeModal.tooManyFiles", { max: MERGE_MAX_FILES });
  } else if (uploadBytes > MERGE_MAX_UPLOAD) {
    problem = t("mergeModal.tooLargeUpload", { max: formatBytes(MERGE_MAX_UPLOAD) });
  }

  async function handleMerge() {
    if (problem) { setError(problem); return; }
    setLoading(true);
    setError(null);
    try {
      const res = await api.mergePdfs(items);
      await onMerged(res);
      onClose();
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  const shown = pdfDocs.filter((d) => d.filename.toLowerCase().includes(query.toLowerCase()));
  let mergeBtnLabel;
  if (loading) {
    mergeBtnLabel = t("mergeModal.merging");
  } else if (items.length >= 2) {
    mergeBtnLabel = t("mergeModal.mergeCountBtn", { count: items.length });
  } else {
    mergeBtnLabel = t("mergeModal.mergeBtn");
  }

  return (
    <div role="presentation" className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !loading && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="merge-title" data-testid="merge-modal"
        className={`bg-white w-full sm:max-w-lg rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[90vh] ${dragOver ? "ring-4 ring-blue-300" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); addLocal(e.dataTransfer.files); }}>
        <div className="p-4 border-b border-gray-100">
          <h3 id="merge-title" className="text-lg font-bold text-gray-900">{t("mergeModal.title")}</h3>
          <p className="mt-1 text-sm text-gray-500">{t("mergeModal.subtitle")}</p>
        </div>

        {picking ? (
          <>
            <div className="px-4 pt-3">
              {pdfDocs.length > 5 && (
                <input type="search" autoFocus placeholder={t("chooseFile.searchPlaceholder")} value={query} onChange={(e) => setQuery(e.target.value)}
                  className="block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-blue-500" />
              )}
            </div>
            <ul className="overflow-y-auto divide-y divide-gray-100 flex-1 min-h-[8rem]" data-testid="merge-doc-list">
              {shown.length === 0 && <li className="p-6 text-center text-sm text-gray-500">{pdfDocs.length ? t("chooseFile.notFound") : t("mergeModal.noPdfInDocs")}</li>}
              {shown.map((d) => (
                <li key={d.id}>
                  <label className="flex items-center gap-3 px-4 py-3 min-h-[44px] cursor-pointer hover:bg-blue-50">
                    <input type="checkbox" className="h-4 w-4" checked={picked.has(d.id)}
                      onChange={() => setPicked((s) => { const n = new Set(s); n.has(d.id) ? n.delete(d.id) : n.add(d.id); return n; })} />
                    <span className="flex-1 text-sm text-gray-900 truncate">{d.filename}</span>
                    {d.file_size > 0 && <span className="text-xs text-gray-400 shrink-0">{formatBytes(d.file_size)}</span>}
                  </label>
                </li>
              ))}
            </ul>
            <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
              <button type="button" onClick={() => setPicking(false)} className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">{t("common.back")}</button>
              <button type="button" onClick={addPicked} disabled={!picked.size} data-testid="merge-add-picked"
                className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">{t("mergeModal.addPickedBtn", { count: picked.size || "" })}</button>
            </div>
          </>
        ) : (
          <>
            <div className="px-4 pt-3 flex flex-wrap gap-2">
              <button type="button" onClick={() => fileInputRef.current?.click()} data-testid="merge-add-local"
                className="px-3 py-2 min-h-[40px] text-sm font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100">{t("mergeModal.addLocalBtn")}</button>
              <button type="button" onClick={() => setPicking(true)} data-testid="merge-add-stored"
                className="px-3 py-2 min-h-[40px] text-sm font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100">{t("mergeModal.addStoredBtn")}</button>
              <input type="file" multiple accept="application/pdf,.pdf" ref={fileInputRef} className="hidden" data-testid="merge-file-input"
                onChange={(e) => { addLocal(e.target.files); e.target.value = ""; }} />
            </div>
            <div className="px-4 py-3 overflow-y-auto flex-1">
              {items.length === 0 ? (
                <div className="py-8 text-center text-sm text-gray-500 border-2 border-dashed border-gray-200 rounded-xl">
                  {t("mergeModal.emptyDrop")}<span className="hidden sm:inline">{t("mergeModal.emptyDropHint")}</span>
                </div>
              ) : (
                <ol className="divide-y divide-gray-100 border border-gray-200 rounded-xl" data-testid="merge-list">
                  {items.map((it, i) => (
                    <li key={it.key} className="flex items-center gap-2 pl-3 pr-1 py-1.5">
                      <span className="w-6 text-sm text-gray-400 shrink-0">{i + 1}.</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-900 truncate" title={it.name}>{it.name}</p>
                        <p className="text-xs text-gray-400">{it.kind === "stored" ? t("mergeModal.sourceStored") : t("mergeModal.sourceLocal")}{it.size ? ` · ${formatBytes(it.size)}` : ""}</p>
                      </div>
                      <button type="button" aria-label={t("mergeModal.moveUpAria", { name: it.name })} disabled={i === 0} onClick={() => move(i, -1)}
                        className="w-10 h-10 rounded-lg text-gray-600 hover:bg-gray-100 disabled:opacity-30">↑</button>
                      <button type="button" aria-label={t("mergeModal.moveDownAria", { name: it.name })} disabled={i === items.length - 1} onClick={() => move(i, 1)}
                        className="w-10 h-10 rounded-lg text-gray-600 hover:bg-gray-100 disabled:opacity-30">↓</button>
                      <button type="button" aria-label={t("mergeModal.removeAria", { name: it.name })} onClick={() => remove(it.key)}
                        className="w-10 h-10 rounded-lg text-red-500 hover:bg-red-50">✕</button>
                    </li>
                  ))}
                </ol>
              )}
              {items.length > 0 && (
                <p className="mt-2 text-xs text-gray-500">{t("mergeModal.summary", { count: items.length, size: formatBytes(totalBytes) })}</p>
              )}
              {error && <p className="mt-2 text-sm text-red-600" role="alert">{error}</p>}
            </div>
            <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
              <button type="button" onClick={onClose} disabled={loading}
                className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">{t("common.cancel")}</button>
              <button type="button" onClick={() => void handleMerge()} disabled={loading || items.length < 2} data-testid="merge-submit"
                className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-40">
                {mergeBtnLabel}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
