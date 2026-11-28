// แผง "ตรวจหาข้อมูลส่วนบุคคล (PDPA)" ใน Editor — ไม่บังหน้าเอกสาร เพื่อให้เห็นกรอบไฮไลต์ก่อนปิดจริง
// สแกน → ตรวจทาน/ติ๊ก (คลิกรายการเพื่อกระโดดไปหน้านั้น) → ปิดทับถาวร (undo ได้) → ดาวน์โหลดรายงาน
import { useCallback, useEffect, useState } from "react";
import * as api from "../../api.js";
import { useI18n } from "../../i18n/I18nContext.jsx";
import PiiReviewList, { defaultPiiSelection, downloadPiiReport } from "./PiiReviewList.jsx";

export default function PiiPanel({ sessionId, fileName, onGoToPage, onHighlights, onApplied, onClose }) {
  const { lang, t } = useI18n();
  const [phase, setPhase] = useState("scanning"); // scanning | review | applying | done | error
  const [scan, setScan] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [cleanMetadata, setCleanMetadata] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const runScan = useCallback(async () => {
    setPhase("scanning");
    setError("");
    setActiveId(null);
    try {
      const res = await api.scanPii(sessionId);
      setScan(res);
      setSelected(defaultPiiSelection(res.findings));
      setPhase("review");
    } catch (e) {
      setError(e.message || t("editor.panels.pii.scanFailed"));
      setPhase("error");
    }
  }, [sessionId, t]);

  useEffect(() => {
    void runScan();
  }, [runScan]);

  // ส่งกรอบไฮไลต์ให้ PDFCanvas (เฉพาะตอนตรวจทาน)
  useEffect(() => {
    if (phase !== "review" || !scan) {
      onHighlights([]);
      return;
    }
    onHighlights(scan.findings.map((f) => ({ id: f.id, page: f.page, rects: f.rects, selected: selected.has(f.id), active: f.id === activeId })));
  }, [phase, scan, selected, activeId, onHighlights]);

  useEffect(() => () => onHighlights([]), [onHighlights]);

  async function apply() {
    setPhase("applying");
    setError("");
    try {
      const res = await api.redactPii(sessionId, [...selected], cleanMetadata);
      setResult(res);
      setPhase("done");
      await onApplied(res);
    } catch (e) {
      setError(e.status === 409 ? t("editor.panels.pii.conflictError") : e.message || t("editor.panels.pii.redactFailed"));
      setPhase("review");
    }
  }

  function activate(f) {
    setActiveId(f.id);
    onGoToPage(f.page);
  }

  const nothing = selected.size === 0 && !cleanMetadata;
  let applyButtonLabel = t("editor.panels.pii.cleanMetadataOnly");
  if (phase === "applying") {
    applyButtonLabel = t("editor.panels.pii.applying");
  } else if (selected.size > 0) {
    applyButtonLabel = t("editor.panels.pii.redactCount", { count: selected.size });
  }

  return (
    <aside
      role="dialog"
      aria-label={t("editor.panels.pii.panelAria")}
      data-testid="pii-panel"
      className="fixed z-[45] inset-x-0 bottom-0 max-h-[70dvh] sm:inset-x-auto sm:right-4 sm:top-24 sm:bottom-4 sm:max-h-none sm:w-[380px] flex flex-col bg-white border border-gray-200 rounded-t-2xl sm:rounded-xl shadow-2xl"
    >
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
        <svg className="w-5 h-5 text-indigo-600 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
          <path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z" />
        </svg>
        <h3 className="flex-1 font-bold text-gray-900">{t("editor.panels.pii.title")}</h3>
        <button type="button" onClick={onClose} aria-label={t("editor.panels.pii.closeAria")} className="p-1 rounded hover:bg-gray-100 text-gray-500">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 text-sm text-gray-600 space-y-3">
        {phase === "scanning" && <p>{t("editor.panels.pii.scanning")}</p>}
        {phase === "error" && <p className="text-red-700">{error}</p>}
        {(phase === "review" || phase === "applying") && scan && (
          <>
            {scan.findings.length > 0 && (
              <p>
                {t("editor.panels.pii.foundPrefix")}<strong className="text-gray-900">{scan.findings.length}</strong>{t("editor.panels.pii.foundMiddle")}<span className="text-orange-600 font-semibold">{t("editor.panels.pii.foundOrange")}</span>{t("editor.panels.pii.foundSuffix")}
              </p>
            )}
            {error && <p className="p-2.5 rounded-lg bg-red-50 text-red-700 border border-red-200" role="alert">{error}</p>}
            <PiiReviewList
              scan={scan}
              selected={selected}
              onChange={setSelected}
              cleanMetadata={cleanMetadata}
              onCleanMetadata={setCleanMetadata}
              activeId={activeId}
              onActivate={activate}
              maxHeightClass="max-h-none"
            />
            <p className="text-xs text-gray-500">{t("editor.panels.pii.privacyNote")}</p>
          </>
        )}
        {phase === "done" && result && (
          <>
            <p className="p-3 rounded-lg bg-green-50 text-green-800 border border-green-200">
              {result.metadata_cleaned
                ? t("editor.panels.pii.doneSummaryWithMeta", { count: result.redacted })
                : t("editor.panels.pii.doneSummary", { count: result.redacted })}
            </p>
            {result.report.length > 0 && (
              <button type="button" className="text-blue-700 hover:underline" onClick={() => downloadPiiReport(result.report, fileName || "document.pdf", { t, lang })}>
                {t("editor.panels.pii.downloadReport")}
              </button>
            )}
          </>
        )}
      </div>

      <div className="flex flex-wrap justify-end gap-2 px-4 py-3 border-t border-gray-100">
        {(phase === "review" || phase === "applying") && (
          <>
            <button type="button" onClick={() => void runScan()} disabled={phase === "applying"} className="px-3 py-2 text-sm font-medium rounded-lg text-gray-700 border border-gray-300 hover:bg-gray-50 disabled:opacity-50">
              {t("editor.panels.pii.rescan")}
            </button>
            <button
              type="button"
              onClick={() => void apply()}
              disabled={nothing || phase === "applying"}
              className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            >
              {applyButtonLabel}
            </button>
          </>
        )}
        {(phase === "done" || phase === "error") && (
          <>
            <button type="button" onClick={() => void runScan()} className="px-3 py-2 text-sm font-medium rounded-lg text-gray-700 border border-gray-300 hover:bg-gray-50">
              {t("editor.panels.pii.scanAgain")}
            </button>
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700">
              {t("editor.panels.pii.done")}
            </button>
          </>
        )}
      </div>
    </aside>
  );
}
