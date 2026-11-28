// รายการฟอนต์ทั้งเอกสาร (แบบ Acrobat › คุณสมบัติ › ฟอนต์) — ชนิด การฝัง และหน้าที่ใช้ (ตรวจฟอนต์ v1.38.0)
import { useEffect, useState } from "react";
import * as api from "../../api.js";
import { useI18n } from "../../i18n/I18nContext.jsx";
import { embedLabel, embedTone, pagesLabel } from "../../utils/fontInfo.js";

export default function DocumentFontsModal({ sessionId, onClose }) {
  const { t } = useI18n();
  const [fonts, setFonts] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.getDocumentFonts(sessionId)
      .then((list) => { if (!cancelled) setFonts(list); })
      .catch((e) => { if (!cancelled) { setFonts([]); setError(e.message || t("editor.panels.fontInspector.docFontsLoadFailed")); } });
    return () => { cancelled = true; };
  }, [sessionId, t]);

  const notEmbedded = (fonts || []).filter((f) => embedTone(f) === "warn").length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" role="presentation" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="doc-fonts-title" onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[85dvh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
          <h3 id="doc-fonts-title" className="text-lg font-bold text-slate-900">{t("editor.panels.fontInspector.docFontsTitle")}</h3>
          <button type="button" onClick={onClose} aria-label={t("editor.panels.fontInspector.close")} className="icon-btn">✕</button>
        </div>
        <div className="px-5 py-4 overflow-y-auto">
          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          {fonts === null && <p className="text-sm text-slate-500">{t("editor.panels.fontInspector.docFontsLoading")}</p>}
          {fonts?.length === 0 && !error && <p className="text-sm text-slate-600">{t("editor.panels.fontInspector.docFontsEmpty")}</p>}
          {fonts?.length > 0 && (
            <>
              <p className="text-sm text-slate-600 mb-3">
                {t("editor.panels.fontInspector.docFontsCount", { count: fonts.length })}
                {notEmbedded > 0 && (
                  <span className="text-amber-700">
                    {t("editor.panels.fontInspector.docFontsNotEmbedded", { count: notEmbedded })}
                  </span>
                )}
              </p>
              <ul className="divide-y divide-slate-100 border border-slate-200 rounded-lg" data-testid="document-fonts">
                {fonts.map((f) => (
                  <li key={`${f.name}-${f.type}`} className="px-3 py-2 text-sm">
                    <span className="block font-medium text-slate-900 break-all">{f.name}</span>
                    <span className="block text-xs text-slate-600">
                      {t("editor.panels.fontInspector.docFontsMeta", { type: f.type, pages: pagesLabel(f.pages) })}
                    </span>
                    <span className={`block text-xs ${embedTone(f) === "warn" ? "text-amber-700" : "text-slate-500"}`}>{embedLabel(f, t)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
