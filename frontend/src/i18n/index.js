// โครงสร้างกลาง i18n (Zero-dependency) — รองรับ dot-key, {{param}} interpolation และ fallback เป็นภาษาไทย

export const DEFAULT_LANG = "th";
export const LANG_STORAGE_KEY = "ja_lang";

export const SUPPORTED_LANGS = Object.freeze([
  { code: "th", shortLabel: "TH", label: "ภาษาไทย", nativeLabel: "ภาษาไทย (Thai)" },
  { code: "en", shortLabel: "EN", label: "English", nativeLabel: "English" },
  { code: "ko", shortLabel: "KO", label: "한국어", nativeLabel: "한국어 (Korean)" },
  { code: "ja", shortLabel: "JA", label: "日本語", nativeLabel: "日本語 (Japanese)" },
  { code: "zh", shortLabel: "中文", label: "简体中文", nativeLabel: "简体中文 (Chinese)" },
  { code: "vi", shortLabel: "VI", label: "Tiếng Việt", nativeLabel: "Tiếng Việt (Vietnamese)" },
  { code: "id", shortLabel: "ID", label: "Bahasa Indonesia", nativeLabel: "Bahasa Indonesia (Indonesian)" },
]);

const DATE_LOCALES = {
  th: "th-TH",
  en: "en-US",
  ko: "ko-KR",
  ja: "ja-JP",
  zh: "zh-CN",
  vi: "vi-VN",
  id: "id-ID",
};

export function dateLocale(lang) {
  return DATE_LOCALES[lang] || "th-TH";
}

const SUPPORTED_CODES = new Set(SUPPORTED_LANGS.map((l) => l.code));

export function normalizeLang(code) {
  if (!code || typeof code !== "string") return DEFAULT_LANG;
  const clean = code.trim().toLowerCase().split("-")[0];
  return SUPPORTED_CODES.has(clean) ? clean : DEFAULT_LANG;
}

export function getStoredLanguage() {
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(LANG_STORAGE_KEY) : null;
    if (raw) return normalizeLang(raw);
  } catch {
    /* localStorage ถูกปิดใช้งาน */
  }
  return DEFAULT_LANG;
}

export function setStoredLanguage(code) {
  const norm = normalizeLang(code);
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(LANG_STORAGE_KEY, norm);
    }
  } catch {
    /* localStorage ถูกปิดใช้งาน */
  }
  return norm;
}

function lookupKey(dict, key) {
  if (!dict || !key) return undefined;
  let cur = dict;
  for (const part of key.split(".")) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = cur[part];
  }
  return typeof cur === "string" ? cur : undefined;
}

export function translate(dict, fallbackDict, key, params) {
  const template = lookupKey(dict, key) ?? lookupKey(fallbackDict, key) ?? key;
  if (!params) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_match, name) => (
    params[name] === undefined || params[name] === null ? "" : String(params[name])
  ));
}

export function flattenKeys(obj, prefix = "") {
  const out = [];
  for (const [k, v] of Object.entries(obj || {})) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      out.push(...flattenKeys(v, path));
    } else {
      out.push(path);
    }
  }
  return out.sort((a, b) => a.localeCompare(b));
}
