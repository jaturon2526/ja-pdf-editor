import { describe, expect, it } from "vitest";
import th from "../i18n/locales/th.json";
import en from "../i18n/locales/en.json";
import ko from "../i18n/locales/ko.json";
import ja from "../i18n/locales/ja.json";
import zh from "../i18n/locales/zh.json";
import vi from "../i18n/locales/vi.json";
import id from "../i18n/locales/id.json";
import hi from "../i18n/locales/hi.json";
import ar from "../i18n/locales/ar.json";
import es from "../i18n/locales/es.json";
import pt from "../i18n/locales/pt.json";
import fr from "../i18n/locales/fr.json";
import de from "../i18n/locales/de.json";
import itDict from "../i18n/locales/it.json";
import ru from "../i18n/locales/ru.json";
import { flattenKeys, langDir, normalizeLang, translate } from "../i18n/index.js";

const ALL_NON_TH = [en, ko, ja, zh, vi, id, hi, ar, es, pt, fr, de, itDict, ru];

describe("i18n dictionaries and helpers", () => {
  it("keeps all 15 locale dictionaries 100% in sync with th.json", () => {
    const thKeys = flattenKeys(th);
    for (const dict of ALL_NON_TH) {
      expect(flattenKeys(dict)).toEqual(thKeys);
    }
  });

  it("interpolates parameters and falls back cleanly", () => {
    expect(translate(en, th, "auth.resendWait", { seconds: 15 })).toBe("Please wait 15s to resend");
    for (const dict of ALL_NON_TH) {
      expect(translate(dict, th, "auth.resendWait", { seconds: 15 })).toContain("15");
    }
    expect(translate({}, th, "common.save")).toBe("บันทึกข้อมูล");
    expect(translate(en, th, "nonexistent.key")).toBe("nonexistent.key");
  });

  it("normalizes language codes and directions safely", () => {
    for (const [raw, expected] of [
      ["en-US", "en"], ["ko-KR", "ko"], ["ja-JP", "ja"], ["zh-CN", "zh"],
      ["vi-VN", "vi"], ["id-ID", "id"], ["hi-IN", "hi"], ["ar-SA", "ar"],
      ["es-ES", "es"], ["pt-BR", "pt"], ["fr-FR", "fr"], ["de-DE", "de"],
      ["it-IT", "it"], ["ru-RU", "ru"], ["TH", "th"], ["xx", "th"], [null, "th"],
    ]) {
      expect(normalizeLang(raw)).toBe(expected);
    }
    expect(langDir("ar")).toBe("rtl");
    expect(langDir("en")).toBe("ltr");
    expect(langDir("th")).toBe("ltr");
  });
});
