import { describe, expect, it } from "vitest";
import th from "../i18n/locales/th.json";
import en from "../i18n/locales/en.json";
import { flattenKeys, normalizeLang, translate } from "../i18n/index.js";

describe("i18n dictionaries and helpers", () => {
  it("keeps th.json and en.json keys 100% in sync", () => {
    const thKeys = flattenKeys(th);
    const enKeys = flattenKeys(en);
    expect(enKeys).toEqual(thKeys);
  });

  it("interpolates parameters and falls back cleanly", () => {
    expect(translate(en, th, "auth.resendWait", { seconds: 15 })).toBe("Please wait 15s to resend");
    expect(translate({}, th, "common.save")).toBe("บันทึกข้อมูล");
    expect(translate(en, th, "nonexistent.key")).toBe("nonexistent.key");
  });

  it("normalizes language codes safely", () => {
    expect(normalizeLang("en-US")).toBe("en");
    expect(normalizeLang("TH")).toBe("th");
    expect(normalizeLang("xx")).toBe("th");
    expect(normalizeLang(null)).toBe("th");
  });
});
