// useFonts.js — โหลด/ติดตั้ง/ลบ font และ inject @font-face CSS อัตโนมัติ

import { useEffect, useState } from "react";
import * as api from "../api.js";
import { cssFontFamilyName } from "../utils/textEditUtils.js";

export function useFonts({ setStatusMessage }) {
  const [fonts, setFonts] = useState([]);
  const [fontFamilies, setFontFamilies] = useState([]);
  const [installFontOpen, setInstallFontOpen] = useState(false);
  const [installFontError, setInstallFontError] = useState(null);
  const [installFontSubmitting, setInstallFontSubmitting] = useState(false);
  // คำเตือนหลังติดตั้งสำเร็จ (ฟอนต์ไม่มีตัวอักษรไทย / ผู้ออกแบบห้ามฝังลงเอกสาร) — แสดงในหน้าต่างติดตั้ง
  const [installFontNotice, setInstallFontNotice] = useState([]);

  // โหลดรายชื่อ font (flat + family) ครั้งเดียวตอนเปิดแอป
  useEffect(() => {
    api.getFonts().then(setFonts).catch(() => setFonts([]));
    api.getFontFamilies().then(setFontFamilies).catch(() => setFontFamilies([]));
  }, []);

  // ประกาศ @font-face ชี้ไปไฟล์ font จริงจาก backend เพื่อให้ preview ตรงกับของจริง
  // รันใหม่ทุกครั้งที่รายชื่อฟอนต์เปลี่ยน (หลังติดตั้ง/ลบ)
  useEffect(() => {
    if (!fonts.length) return;
    const styleEl =
      document.getElementById("pdfedit-font-faces") || document.createElement("style");
    styleEl.id = "pdfedit-font-faces";
    styleEl.textContent = fonts
      .map(
        (f) =>
          `@font-face { font-family: '${cssFontFamilyName(f.key)}'; src: url('${f.file_url || api.fontFileUrl(f.key)}'); font-display: block; }`
      )
      .join("\n");
    if (!styleEl.parentNode) document.head.appendChild(styleEl);
  }, [fonts]);

  // รีเฟรชทั้ง fonts (flat) และ fontFamilies (จัดกลุ่ม) พร้อมกัน
  // เรียกหลัง install/ลบฟอนต์สำเร็จ กัน state สองตัวไม่ตรงกัน
  async function refreshFontsAndFamilies(flatFontsFromResponse) {
    setFonts(flatFontsFromResponse);
    try {
      setFontFamilies(await api.getFontFamilies());
    } catch {
      /* ไม่ critical — dropdown ปกติ (fonts flat) อัปเดตไปแล้ว */
    }
  }

  function handleOpenInstallFont() {
    setInstallFontError(null);
    setInstallFontNotice([]);
    setInstallFontOpen(true);
    // Refresh ฟอนต์ล่าสุดทุกครั้งที่เปิด modal — ป้องกันกรณีติดตั้งฟอนต์จาก session อื่นแล้วยังไม่อัปเดต
    api.getFontFamilies().then(setFontFamilies).catch(() => {});
    api.getFonts().then(setFonts).catch(() => {});
  }

  function handleCloseInstallFont() {
    setInstallFontOpen(false);
    setInstallFontError(null);
    setInstallFontNotice([]);
  }

  // ติดตั้งฟอนต์ family ใหม่ (regular บังคับ, bold/italic/bold_italic ไม่บังคับ)
  // อัปโหลดทีละไฟล์ Regular ก่อนเสมอ (ได้ familyKey กลับมา) แล้วส่งสไตล์ที่เหลือเข้า family เดียวกัน
  // คืน true/false บอกผล ให้ InstallFontModal ตัดสินใจเคลียร์ฟอร์มเอง
  async function handleInstallFontFamily(label, filesByStyle) {
    if (!filesByStyle.regular) return false;
    setInstallFontSubmitting(true);
    setInstallFontError(null);
    setInstallFontNotice([]);
    const warnings = new Set();
    try {
      const first = await api.installFont(filesByStyle.regular, label, { style: "regular" });
      (first.warnings || []).forEach((w) => warnings.add(w));
      setInstallFontNotice([...warnings]);
      const familyKey = first.installed.key;
      let latestFonts = first.fonts;
      for (const style of ["bold", "italic", "bold_italic"]) {
        const file = filesByStyle[style];
        if (!file) continue;
        try {
          const res = await api.installFont(file, null, { familyKey, style });
          (res.warnings || []).forEach((w) => warnings.add(w));
          latestFonts = res.fonts;
        } catch (err) {
          await refreshFontsAndFamilies(latestFonts);
          setInstallFontError(
            `ติดตั้งไฟล์สไตล์ "${style}" ไม่สำเร็จ: ${err.message} (สไตล์ก่อนหน้าที่สำเร็จแล้วยังใช้ได้ปกติ)`
          );
          return false;
        }
      }
      await refreshFontsAndFamilies(latestFonts);
      setInstallFontNotice([...warnings]);
      setStatusMessage("ติดตั้งฟอนต์ใหม่สำเร็จ");
      return true;
    } catch (err) {
      setInstallFontError(err.message);
      return false;
    } finally {
      setInstallFontSubmitting(false);
    }
  }

  // เพิ่มสไตล์ใหม่ (bold/italic/bold_italic) เข้าฟอนต์ family ที่ติดตั้งไว้แล้ว
  // ติดตั้งจากลิงก์ Google Fonts (ขั้นตรวจลิงก์ทำใน InstallFontModal เอง) — คืน true/false
  async function handleInstallFromUrl(token, label) {
    setInstallFontSubmitting(true);
    setInstallFontError(null);
    try {
      const res = await api.installFontUrl(token, label);
      await refreshFontsAndFamilies(res.fonts);
      return true;
    } catch (err) {
      setInstallFontError(err.message || "ติดตั้งฟอนต์ไม่สำเร็จ");
      return false;
    } finally {
      setInstallFontSubmitting(false);
    }
  }

  async function handleAddFontStyle(familyKey, style, file) {
    setInstallFontSubmitting(true);
    setInstallFontError(null);
    try {
      const res = await api.installFont(file, null, { familyKey, style });
      await refreshFontsAndFamilies(res.fonts);
      setInstallFontNotice(res.warnings || []);
      setStatusMessage("เพิ่มสไตล์ฟอนต์สำเร็จ");
      return true;
    } catch (err) {
      setInstallFontError(err.message);
      return false;
    } finally {
      setInstallFontSubmitting(false);
    }
  }

  async function handleRemoveFontFamily(familyKey) {
    try {
      const updated = await api.removeFontFamily(familyKey);
      await refreshFontsAndFamilies(updated);
      setStatusMessage("ลบฟอนต์สำเร็จ");
    } catch (err) {
      setInstallFontError(err.message);
    }
  }

  return {
    fonts,
    setFonts,
    fontFamilies,
    setFontFamilies,
    installFontOpen,
    installFontError,
    installFontSubmitting,
    installFontNotice,
    handleOpenInstallFont,
    handleCloseInstallFont,
    handleInstallFontFamily,
    handleAddFontStyle,
    handleInstallFromUrl,
    handleRemoveFontFamily,
    refreshFontsAndFamilies,
  };
}
