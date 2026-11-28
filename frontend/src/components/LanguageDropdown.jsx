// ปุ่มเลือกภาษาแบบธงชาติ + Dropdown (รองรับทั้งเดสก์ท็อปและมือถือ 390×844)
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n/I18nContext.jsx";

export default function LanguageDropdown({ className = "" }) {
  const { lang, setLanguage, supportedLangs } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const current = supportedLangs.find((item) => item.code === lang) || supportedLangs[0];

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative inline-block ${className}`} data-testid="login-lang-switcher">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={current.nativeLabel}
        title={current.nativeLabel}
        className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-gray-200 rounded-lg shadow-sm hover:bg-gray-50 text-xs font-semibold text-gray-700 transition-colors"
      >
        <span className="text-base leading-none" aria-hidden="true">{current.flag}</span>
        <span>{current.shortLabel}</span>
        <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Language"
          className="absolute right-0 mt-1.5 w-60 max-w-[calc(100vw-2rem)] max-h-80 overflow-y-auto bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-30"
        >
          {supportedLangs.map((item) => {
            const active = item.code === lang;
            return (
              <button
                key={item.code}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  setLanguage(item.code);
                  setOpen(false);
                }}
                className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm transition-colors ${
                  active ? "bg-blue-50 text-blue-700 font-semibold" : "text-gray-700 hover:bg-gray-50"
                }`}
              >
                <span className="flex items-center gap-2.5 min-w-0">
                  <span className="text-lg leading-none shrink-0" aria-hidden="true">{item.flag}</span>
                  <span className="truncate">{item.nativeLabel}</span>
                </span>
                {active && (
                  <svg className="w-4 h-4 text-blue-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
