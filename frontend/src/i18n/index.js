// โครงสร้างกลาง i18n (Zero-dependency) — รองรับ dot-key, {{param}} interpolation และ fallback เป็นภาษาไทย

export const DEFAULT_LANG = "th";
export const LANG_STORAGE_KEY = "ja_lang";

export const SUPPORTED_LANGS = Object.freeze([
  { code: "th", shortLabel: "TH", flag: "🇹🇭", dir: "ltr", label: "ภาษาไทย", nativeLabel: "ภาษาไทย (Thai)" },
  { code: "en", shortLabel: "EN", flag: "🇺🇸", dir: "ltr", label: "English", nativeLabel: "English" },
  { code: "ko", shortLabel: "KO", flag: "🇰🇷", dir: "ltr", label: "한국어", nativeLabel: "한국어 (Korean)" },
  { code: "ja", shortLabel: "JA", flag: "🇯🇵", dir: "ltr", label: "日本語", nativeLabel: "日本語 (Japanese)" },
  { code: "zh", shortLabel: "中文", flag: "🇨🇳", dir: "ltr", label: "简体中文", nativeLabel: "简体中文 (Chinese)" },
  { code: "vi", shortLabel: "VI", flag: "🇻🇳", dir: "ltr", label: "Tiếng Việt", nativeLabel: "Tiếng Việt (Vietnamese)" },
  { code: "id", shortLabel: "ID", flag: "🇮🇩", dir: "ltr", label: "Bahasa Indonesia", nativeLabel: "Bahasa Indonesia (Indonesian)" },
  { code: "hi", shortLabel: "HI", flag: "🇮🇳", dir: "ltr", label: "हिन्दी", nativeLabel: "हिन्दी (Hindi)" },
  { code: "ar", shortLabel: "AR", flag: "🇸🇦", dir: "rtl", label: "العربية", nativeLabel: "العربية (Arabic)" },
  { code: "es", shortLabel: "ES", flag: "🇪🇸", dir: "ltr", label: "Español", nativeLabel: "Español (Spanish)" },
  { code: "pt", shortLabel: "PT", flag: "🇧🇷", dir: "ltr", label: "Português", nativeLabel: "Português (Portuguese)" },
  { code: "fr", shortLabel: "FR", flag: "🇫🇷", dir: "ltr", label: "Français", nativeLabel: "Français (French)" },
  { code: "de", shortLabel: "DE", flag: "🇩🇪", dir: "ltr", label: "Deutsch", nativeLabel: "Deutsch (German)" },
  { code: "it", shortLabel: "IT", flag: "🇮🇹", dir: "ltr", label: "Italiano", nativeLabel: "Italiano (Italian)" },
  { code: "ru", shortLabel: "RU", flag: "🇷🇺", dir: "ltr", label: "Русский", nativeLabel: "Русский (Russian)" },
]);

const DATE_LOCALES = {
  th: "th-TH",
  en: "en-US",
  ko: "ko-KR",
  ja: "ja-JP",
  zh: "zh-CN",
  vi: "vi-VN",
  id: "id-ID",
  hi: "hi-IN",
  ar: "ar-SA",
  es: "es-ES",
  pt: "pt-BR",
  fr: "fr-FR",
  de: "de-DE",
  it: "it-IT",
  ru: "ru-RU",
};

export function dateLocale(lang) {
  return DATE_LOCALES[lang] || "th-TH";
}

export function langDir(lang) {
  return SUPPORTED_LANGS.find((l) => l.code === lang)?.dir || "ltr";
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
