import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import thDict from "./locales/th.json";
import {
  DEFAULT_LANG,
  SUPPORTED_LANGS,
  getStoredLanguage,
  setStoredLanguage,
  translate,
} from "./index.js";

const LOADERS = {
  th: async () => thDict,
  en: async () => (await import("./locales/en.json")).default,
};

const I18nContext = createContext({
  lang: DEFAULT_LANG,
  setLanguage: () => {},
  syncLanguageFromUser: () => {},
  t: (key, params) => translate(thDict, thDict, key, params),
  supportedLangs: SUPPORTED_LANGS,
});

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(() => getStoredLanguage());
  const [dicts, setDicts] = useState(() => ({ th: thDict }));

  // โหลดไฟล์ภาษาแบบ lazy เมื่อผู้ใช้เลือกภาษาอื่นนอกจาก th
  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = lang;
    }
    if (dicts[lang]) return undefined;
    let cancelled = false;
    const loader = LOADERS[lang] || LOADERS[DEFAULT_LANG];
    loader()
      .then((loaded) => {
        if (!cancelled && loaded) {
          setDicts((prev) => (prev[lang] ? prev : { ...prev, [lang]: loaded }));
        }
      })
      .catch(() => {
        /* fallback ไปภาษาไทยอัตโนมัติ */
      });
    return () => {
      cancelled = true;
    };
  }, [lang, dicts]);

  const setLanguage = useCallback((nextLang) => {
    const norm = setStoredLanguage(nextLang);
    setLangState(norm);
  }, []);

  const syncLanguageFromUser = useCallback((userLang) => {
    if (!userLang) return;
    const norm = setStoredLanguage(userLang);
    setLangState((prev) => (prev === norm ? prev : norm));
  }, []);

  const activeDict = dicts[lang] || thDict;
  const t = useCallback((key, params) => translate(activeDict, thDict, key, params), [activeDict]);

  const value = useMemo(
    () => ({ lang, setLanguage, syncLanguageFromUser, t, supportedLangs: SUPPORTED_LANGS }),
    [lang, setLanguage, syncLanguageFromUser, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
