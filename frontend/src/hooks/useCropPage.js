import { useCallback, useEffect, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";
import { clampMargins, mmToPt, resolveCropPages } from "../utils/cropGeometry.js";

const DEFAULT_INSET_MM = 10;

export function useCropPage({
  session,
  currentPage,
  active,
  runDocumentChange,
  onDone,
}) {
  const { t } = useI18n();
  const pageSize = session?.pageSizes?.[currentPage];
  const pageWidthPt = pageSize?.[0] || 595;
  const pageHeightPt = pageSize?.[1] || 842;

  const [margins, setMargins] = useState({ left: 0, top: 0, right: 0, bottom: 0 });
  const [scope, setScope] = useState("current"); // "current" | "all" | "range"
  const [rangeText, setRangeText] = useState("");
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");

  // เปิดโหมดตัดขอบหรือเปลี่ยนหน้า → ตั้งกรอบเริ่มต้น 10 มม. (ถ้าหน้าเล็กมากจะ clamp ให้เอง)
  useEffect(() => {
    if (!active) return;
    const inset = mmToPt(DEFAULT_INSET_MM);
    setMargins(clampMargins({ left: inset, top: inset, right: inset, bottom: inset }, pageWidthPt, pageHeightPt));
    setScope("current");
    setRangeText(`${currentPage + 1}`);
    setError("");
  }, [active, currentPage, pageWidthPt, pageHeightPt]);

  const updateMargins = useCallback(
    (next) => {
      setMargins(clampMargins(next, pageWidthPt, pageHeightPt));
      setError("");
    },
    [pageWidthPt, pageHeightPt],
  );

  const setSideMm = useCallback(
    (side, mmValue) => {
      const pt = mmToPt(mmValue);
      setMargins((prev) => clampMargins({ ...prev, [side]: pt }, pageWidthPt, pageHeightPt));
      setError("");
    },
    [pageWidthPt, pageHeightPt],
  );

  const setPresetMm = useCallback(
    (mm) => {
      const pt = mmToPt(mm);
      setMargins(clampMargins({ left: pt, top: pt, right: pt, bottom: pt }, pageWidthPt, pageHeightPt));
      setError("");
    },
    [pageWidthPt, pageHeightPt],
  );

  const apply = useCallback(async () => {
    if (!session || applying) return;
    const { pages, error: rangeErr } = resolveCropPages(scope, currentPage, session.pageCount, rangeText);
    if (rangeErr) {
      setError(rangeErr);
      return;
    }
    if (Math.max(margins.left, margins.top, margins.right, margins.bottom) < 0.5) {
      setError(t("editor.hooks.crop.minMarginRequired"));
      return;
    }
    setApplying(true);
    setError("");
    try {
      const changed = await runDocumentChange(
        (sid) =>
          api.cropPages(sid, {
            pageNumbers: pages,
            leftPt: margins.left,
            topPt: margins.top,
            rightPt: margins.right,
            bottomPt: margins.bottom,
          }),
        {
          busy: t("editor.hooks.crop.busy"),
          success: (res) => t("editor.hooks.crop.success", { count: res?.cropped_pages || pages.length }),
          failure: t("editor.hooks.crop.failed"),
          noChange: t("editor.hooks.crop.noChange"),
          rethrow: true,
        },
      );
      if (changed && onDone) onDone();
    } catch (err) {
      setError(err?.message || t("editor.hooks.crop.failed"));
    } finally {
      setApplying(false);
    }
  }, [session, applying, scope, currentPage, rangeText, margins, runDocumentChange, onDone, t]);

  return {
    margins,
    updateMargins,
    setSideMm,
    setPresetMm,
    scope,
    setScope,
    rangeText,
    setRangeText,
    applying,
    error,
    setError,
    pageWidthPt,
    pageHeightPt,
    pageCount: session?.pageCount || 1,
    currentPage,
    apply,
  };
}
