import { describe, expect, it } from "vitest";
import th from "../i18n/locales/th.json";
import en from "../i18n/locales/en.json";
import ko from "../i18n/locales/ko.json";
import ja from "../i18n/locales/ja.json";
import zh from "../i18n/locales/zh.json";
import vi from "../i18n/locales/vi.json";
import id from "../i18n/locales/id.json";
import { flattenKeys, normalizeLang, translate } from "../i18n/index.js";

describe("i18n dictionaries and helpers", () => {
  it("keeps all locale dictionaries 100% in sync with th.json", () => {
    const thKeys = flattenKeys(th);
    for (const dict of [en, ko, ja, zh, vi, id]) {
      expect(flattenKeys(dict)).toEqual(thKeys);
    }
  });

  it("interpolates parameters and falls back cleanly", () => {
    expect(translate(en, th, "auth.resendWait", { seconds: 15 })).toBe("Please wait 15s to resend");
    expect(translate(ko, th, "auth.resendWait", { seconds: 15 })).toContain("15");
    expect(translate(ja, th, "auth.resendWait", { seconds: 15 })).toContain("15");
    expect(translate(zh, th, "auth.resendWait", { seconds: 15 })).toContain("15");
    expect(translate(vi, th, "auth.resendWait", { seconds: 15 })).toContain("15");
    expect(translate(id, th, "auth.resendWait", { seconds: 15 })).toContain("15");
    expect(translate({}, th, "common.save")).toBe("บันทึกข้อมูล");
    expect(translate(en, th, "nonexistent.key")).toBe("nonexistent.key");
  });

  it("normalizes language codes safely", () => {
    expect(normalizeLang("en-US")).toBe("en");
    expect(normalizeLang("ko-KR")).toBe("ko");
    expect(normalizeLang("ja-JP")).toBe("ja");
    expect(normalizeLang("zh-CN")).toBe("zh");
    expect(normalizeLang("vi-VN")).toBe("vi");
    expect(normalizeLang("id-ID")).toBe("id");
    expect(normalizeLang("TH")).toBe("th");
    expect(normalizeLang("xx")).toBe("th");
    expect(normalizeLang(null)).toBe("th");
  });
});
