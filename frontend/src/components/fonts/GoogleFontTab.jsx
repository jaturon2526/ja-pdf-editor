// แท็บ "จาก Google Fonts" ในหน้าต่างติดตั้งฟอนต์: วางลิงก์/ชื่อฟอนต์ → ตรวจลิงก์ (ดูตัวอย่าง) → ติดตั้ง
// รับเฉพาะ Google Fonts + https (ผู้ใช้กำหนดเรื่องความปลอดภัย — ดู backend services/font_url.py)
import { useEffect, useState } from "react";

import { previewFontUrl } from "../../api/edit.js";
import { useI18n } from "../../i18n/I18nContext.jsx";

const STYLE_KEY = {
  regular: "installFont.styleShortRegular",
  bold: "installFont.styleShortBold",
  italic: "installFont.styleShortItalic",
  bold_italic: "installFont.styleShortBoldItalic",
};
const SAMPLE = "สวัสดีครับ ภาษาไทย ฟอนต์สวยงาม ABC abc 0123";
const GOOGLE_FONTS_THAI = "https://fonts.google.com/?subset=thai";

function kb(n) {
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

export default function GoogleFontTab({ submitting, error, onInstall }) {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const [preview, setPreview] = useState(null);
  const [label, setLabel] = useState("");
  const [done, setDone] = useState("");

  // ฟอนต์ตัวอย่าง: ประกาศ @font-face จากไฟล์ชั่วคราวของขั้นตรวจลิงก์
  useEffect(() => {
    if (!preview) return undefined;
    const el = document.createElement("style");
    el.textContent = preview.styles
      .map((s) => `@font-face { font-family: 'gfp-${preview.token}-${s.style}'; src: url('${s.file_url}'); font-display: block; }`)
      .join("\n");
    document.head.appendChild(el);
    return () => el.remove();
  }, [preview]);

  async function check(e) {
    e.preventDefault();
    if (!url.trim() || checking) return;
    setChecking(true);
    setCheckError("");
    setPreview(null);
    setDone("");
    try {
      const p = await previewFontUrl(url.trim());
      setPreview(p);
      setLabel(p.exists ? `${p.family} (Google)` : p.family);
    } catch (err) {
      setCheckError(err.message || t("installFont.google.checkError"));
    } finally {
      setChecking(false);
    }
  }

  async function install() {
    const name = label.trim() || preview.family;
    const ok = await onInstall(preview.token, name);
    if (ok) {
      setDone(t("installFont.google.done", { name, count: preview.styles.length }));
      setPreview(null);
      setUrl("");
    }
  }

  return (
    <div className="space-y-5" data-testid="google-font-tab">
      <form onSubmit={(e) => void check(e)} className="space-y-2">
        <label htmlFor="google-font-url" className="block text-sm font-medium text-gray-700">{t("installFont.google.urlLabel")}</label>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            id="google-font-url"
            type="text"
            inputMode="url"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            className="flex-1 min-w-0 px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm text-base focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder={t("installFont.google.urlPh")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button type="submit" disabled={!url.trim() || checking}
            className="px-5 py-2.5 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 whitespace-nowrap">
            {checking ? t("installFont.google.checking") : t("installFont.google.checkBtn")}
          </button>
        </div>
        <p className="text-xs text-gray-500">
          {t("installFont.google.hintBefore")}{" "}
          <a href={GOOGLE_FONTS_THAI} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{t("installFont.google.hintLink")}</a>
          {" "}{t("installFont.google.hintAfter")}
        </p>
      </form>

      {checkError && <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded text-red-700 text-sm" role="alert">{checkError}</div>}
      {done && <div className="bg-emerald-50 border-l-4 border-emerald-500 p-3 rounded text-emerald-800 text-sm" role="status">{done}</div>}

      {preview && (
        <div className="rounded-xl border border-gray-200 overflow-hidden" data-testid="google-font-preview">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex flex-wrap items-center gap-2">
            <span className="font-semibold text-gray-900">{preview.family}</span>
            <span className="text-xs text-gray-500">{t("installFont.google.fromGoogle")}</span>
            <span className="ml-auto flex flex-wrap gap-1">
              {preview.styles.map((s) => (
                <span key={s.style} className="px-2 py-0.5 rounded bg-blue-100 text-blue-700 text-xs font-medium">{STYLE_KEY[s.style] ? t(STYLE_KEY[s.style]) : s.style} · {kb(s.size)}</span>
              ))}
            </span>
          </div>
          <div className="p-4 space-y-2">
            {preview.styles.map((s) => (
              <p key={s.style} className="text-xl text-gray-900 break-words"
                style={{ fontFamily: `'gfp-${preview.token}-${s.style}', sans-serif` }}>
                {SAMPLE}
              </p>
            ))}
          </div>
          <div className="px-4 pb-4 space-y-3">
            {!preview.has_thai && (
              <p className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
                {t("installFont.google.noThaiBefore")}<strong>{t("installFont.google.noThaiStrong")}</strong> {t("installFont.google.noThaiAfter")}
              </p>
            )}
            {preview.missing_styles?.length > 0 && (
              <p className="text-xs text-gray-500">
                {t("installFont.google.missingStyles", { styles: preview.missing_styles.map((s) => (STYLE_KEY[s] ? t(STYLE_KEY[s]) : s)).join(" / ") })}
              </p>
            )}
            {preview.exists && (
              <p className="text-xs text-amber-700">
                {preview.exists === "global" ? t("installFont.google.existsGlobal") : t("installFont.google.existsUser")}{t("installFont.google.existsSuffix")}
              </p>
            )}
            <label className="block text-sm font-medium text-gray-700">
              {t("installFont.google.displayLabel")}
              <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80}
                className="mt-1 w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm text-base focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </label>
            {error && <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded text-red-700 text-sm">{error}</div>}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-gray-500">{t("installFont.google.licenseHint")}</p>
              <button type="button" onClick={() => void install()} disabled={submitting}
                className="px-6 py-2.5 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50">
                {submitting ? t("installFont.installing") : t("installFont.google.installStyles", { count: preview.styles.length })}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
