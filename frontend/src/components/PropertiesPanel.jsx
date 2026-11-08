import React from "react";
import { resolveFamilyAndStyle } from "../utils/textEditUtils.js";

/**
 * PropertiesPanel — แถบด้านขวา แสดงตอนเลือกย่อหน้าเพื่อแก้ไข (Tools > แก้ไขข้อความ)
 *
 * เดิม panel นี้มีทั้ง textarea แก้ข้อความ + font/ขนาด/สี รวมกัน แต่ผู้ใช้แจ้งว่าอยากแก้ข้อความ
 * ตรงหน้าจอ (บนตำแหน่งจริงของย่อหน้า) ได้เลยแทน — เนื้อความจึงย้ายไปแก้ที่ EditableTextBox
 * (ดู PDFCanvas.jsx) panel นี้เหลือแค่ควบคุม font / ขนาด / สี เท่านั้น และกลายเป็น "controlled
 * component" ทั้งหมด ไม่มี state ภายในของตัวเองอีกต่อไป — ค่าปัจจุบันมาจาก draft ใน App.jsx
 * (ตัวเดียวกับที่ EditableTextBox ใช้พรีวิวบนจอ) ให้พิมพ์ข้อความ+ปรับ font พร้อมกันแล้วเห็นผลสดๆ
 *
 * เรื่องปุ่ม "ตกลง" (เดิมชื่อ "บันทึก"): ผู้ใช้แจ้งว่าอยากกดบันทึกครั้งเดียวหลังแก้ไขครบทุกย่อหน้า
 * ไม่ใช่ยิง API ทีละจุดที่แก้ (ดูหมายเหตุ pendingEdits ใน App.jsx) ปุ่มนี้จึงแค่ "ยืนยัน" ย่อหน้า
 * ที่กำลังแก้อยู่ตอนนี้เก็บไว้ในเครื่องก่อนเท่านั้น (ไม่ยิง network) ผู้ใช้ต้องกดปุ่ม "บันทึกการแก้ไข"
 * บน toolbar อีกทีถึงจะเขียนลงไฟล์จริงรวมทุกย่อหน้าที่สะสมไว้ทีเดียว — เพราะเป็นแค่การเก็บ draft ใน
 * เครื่อง การกดปุ่มนี้จึงเสร็จทันที ไม่มีสถานะ "กำลังบันทึก…" ให้รอเหมือนเดิมอีกต่อไป
 *
 * อัปเดตล่าสุด (ผู้ใช้แจ้งขอเพิ่ม): เดิม Font เป็น dropdown แบบ flat เห็นเป็นหลาย option แยกกัน (เช่น
 * "Sarabun"/"Sarabun Bold"/"Sarabun Italic" คนละแถว) เปลี่ยนเป็นเลือก **family** ก่อน (dropdown) แล้ว
 * กดปุ่มสไตล์ต่อ (ตัวหนา/ตัวเอียง/ตัวหนาเอียง) เหมือนไอคอน Bold/Italic/Bold Italic บน toolbar ทั่วไป —
 * ปุ่มไหนไม่มีไฟล์ฟอนต์ของสไตล์นั้นใน family ที่เลือกอยู่จะกดไม่ได้ (ไม่มีการสร้างตัวหนา/เอียงปลอม — ดู
 * เหตุผลเต็มใน backend fonts.py) ค่าที่ parent (App.jsx) เก็บยังเป็น flat fontname key เดิมเป๊ะๆ
 * (เช่น "sarabun-bold") — component นี้แค่แปลง family+style ↔ flat key เองภายใน ไม่ต้องเปลี่ยน
 * โครงสร้าง draftEdit ใน App.jsx เลย
 *
 * เพิ่มปุ่ม "ขีดเส้นใต้" แยกต่างหาก (ไม่ใช่ font variant — วาดเส้นเพิ่มเฉยๆ ใช้ได้กับทุกฟอนต์/ทุกสไตล์
 * จึงกดได้เสมอไม่ว่าจะเลือกฟอนต์ family ไหนอยู่)
 */
const STYLE_OPTIONS = [
  { key: "regular", label: "R", title: "ตัวปกติ (Regular)" },
  { key: "bold", label: "B", title: "ตัวหนา (Bold)" },
  { key: "italic", label: "I", title: "ตัวเอียง (Italic)" },
  { key: "bold_italic", label: "BI", title: "ตัวหนาเอียง (Bold Italic)" },
];

// ไอคอนจัดตัวหนังสือ ชิดซ้าย/กึ่งกลาง/ชิดขวา (ผู้ใช้แจ้งเพิ่ม) — เส้นจำลองบรรทัดข้อความสั้น/ยาวสลับกัน
// จัดตำแหน่งต่างกันตามแนวที่เลือก ให้ดูออกง่ายว่าปุ่มไหนคือปุ่มไหนแม้ไม่มี label ข้อความกำกับ
const ALIGN_ICONS = {
  left: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path d="M2 3.5h12M2 7h8M2 10.5h12M2 14h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  center: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path d="M2 3.5h12M4 7h8M2 10.5h12M4 14h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  right: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path d="M2 3.5h12M6 7h8M2 10.5h12M6 14h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
};
const ALIGN_OPTIONS = [
  { key: "left", label: "ชิดซ้าย" },
  { key: "center", label: "กึ่งกลาง" },
  { key: "right", label: "ชิดขวา" },
];

const VALIGN_ICONS = {
  top: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path d="M2 3h12 M4 7h8 M4 11h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  middle: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path d="M4 4h8 M2 8h12 M4 12h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  bottom: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path d="M4 5h8 M4 9h8 M2 13h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
};
const VALIGN_OPTIONS = [
  { key: "top", label: "ชิดบน" },
  { key: "middle", label: "กึ่งกลาง" },
  { key: "bottom", label: "ชิดล่าง" },
];

const PRESET_COLORS = [
  { key: "black", label: "ดำ", value: "#000000" },
  { key: "blue", label: "น้ำเงิน", value: "#1a56db" },
  { key: "red", label: "แดง", value: "#d32f2f" },
];

export default function PropertiesPanel({
  fontFamilies,
  fontKey,
  onFontKeyChange,
  fontSize,
  onFontSizeChange,
  colorHex,
  onColorHexChange,
  align = "left",
  onAlignChange,
  valign = "top",
  onValignChange,
  underline = false,
  onUnderlineChange,
  onSave,
  onCancel,
  saving,
  errorMessage,
}) {
  const families = fontFamilies || [];
  const { familyKey, style: currentStyle } = resolveFamilyAndStyle(fontKey, families);
  const currentFamily = families.find((f) => f.key === familyKey) || families[0] || null;

  function handleFamilyChange(newFamilyKey) {
    const fam = families.find((f) => f.key === newFamilyKey);
    if (!fam) return;
    // เปลี่ยน family แล้วพยายามคงสไตล์เดิมไว้ถ้า family ใหม่มีไฟล์สไตล์นั้นด้วย ไม่งั้น fallback ไปตัวปกติ
    const nextStyle = fam.styles[currentStyle] ? currentStyle : "regular";
    onFontKeyChange(fam.styles[nextStyle] || fam.styles.regular);
  }

  function handleStyleChange(newStyle) {
    if (!currentFamily || !currentFamily.styles[newStyle]) return;
    onFontKeyChange(currentFamily.styles[newStyle]);
  }

  return (
    <div className="properties-panel">
      <div className="properties-header">
        <h3>ฟอนต์ของข้อความ</h3>
        <button className="icon-btn" onClick={onCancel} title="ปิด" aria-label="ปิด">
          ✕
        </button>
      </div>

      <div className="properties-body">
        <p className="properties-hint">
          พิมพ์แก้ข้อความได้ที่กล่องบนหน้าเอกสารโดยตรง กด "ตกลง" เพื่อยืนยันย่อหน้านี้ แล้วไปกดปุ่ม
          "บันทึกการแก้ไข" บน toolbar อีกครั้งหลังแก้ไขครบทุกจุดแล้ว เพื่อบันทึกลงไฟล์จริง
        </p>

        <label className="properties-label">Font</label>
        <select
          className="properties-select"
          value={familyKey || ""}
          onChange={(e) => handleFamilyChange(e.target.value)}
        >
          {families.map((f) => (
            <option key={f.key} value={f.key}>
              {f.label}
            </option>
          ))}
        </select>

        <div className="properties-style-group">
          {STYLE_OPTIONS.map((opt) => {
            const available = !!currentFamily?.styles[opt.key];
            return (
              <button
                key={opt.key}
                type="button"
                className={`properties-style-btn ${currentStyle === opt.key ? "active" : ""}`}
                title={available ? opt.title : `${opt.title} — ฟอนต์นี้ไม่มีไฟล์สไตล์นี้`}
                disabled={!available}
                onClick={() => handleStyleChange(opt.key)}
              >
                {opt.label}
              </button>
            );
          })}
          <button
            type="button"
            className={`properties-style-btn properties-underline-btn ${underline ? "active" : ""}`}
            title="ขีดเส้นใต้ (ใช้ได้กับทุกฟอนต์)"
            onClick={() => onUnderlineChange(!underline)}
          >
            U
          </button>
        </div>

        <div className="properties-row">
          <div className="properties-field">
            <label className="properties-label">ขนาดตัวอักษร</label>
            <input
              type="number"
              className="properties-number"
              min={6}
              max={96}
              value={fontSize}
              onChange={(e) => onFontSizeChange(parseFloat(e.target.value) || 14)}
            />
          </div>
          <div className="properties-field" style={{ flex: 1.2 }}>
            <label className="properties-label">สีตัวอักษร</label>
            <div className="flex items-center gap-2 mt-1">
              {PRESET_COLORS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  title={preset.label}
                  aria-label={preset.label}
                  className={`w-7 h-7 rounded-full border transition-all shadow-sm ${
                    colorHex.toLowerCase() === preset.value
                      ? "border-sky-500 scale-110 ring-2 ring-sky-200"
                      : "border-slate-300 hover:scale-105"
                  }`}
                  style={{ backgroundColor: preset.value }}
                  onClick={() => onColorHexChange(preset.value)}
                />
              ))}
              <div
                className="relative w-7 h-7 rounded-full overflow-hidden border border-slate-300 shadow-sm hover:border-slate-400"
                title="สีอื่นๆ"
              >
                <input
                  type="color"
                  value={colorHex}
                  onChange={(e) => onColorHexChange(e.target.value)}
                  className="absolute -top-2 -left-2 w-12 h-12 cursor-pointer border-0 p-0"
                />
              </div>
            </div>
          </div>
        </div>

        <label className="properties-label">การจัดตัวหนังสือ (แนวนอน)</label>
        <div className="properties-align-group">
          {ALIGN_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              className={`properties-align-btn ${align === opt.key ? "active" : ""}`}
              title={opt.label}
              aria-label={opt.label}
              onClick={() => onAlignChange(opt.key)}
            >
              {ALIGN_ICONS[opt.key]}
            </button>
          ))}
        </div>

        <label className="properties-label" style={{ marginTop: 16 }}>การจัดตัวหนังสือ (แนวตั้ง)</label>
        <div className="properties-align-group">
          {VALIGN_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              className={`properties-align-btn ${valign === opt.key ? "active" : ""}`}
              title={opt.label}
              aria-label={opt.label}
              onClick={() => onValignChange(opt.key)}
            >
              {VALIGN_ICONS[opt.key]}
            </button>
          ))}
        </div>

        {errorMessage && <p className="properties-error">{errorMessage}</p>}
      </div>

      <div className="properties-actions">
        <button className="secondary-btn" onClick={onCancel} disabled={saving}>
          ยกเลิก
        </button>
        <button className="primary-btn" onClick={onSave} disabled={saving}>
          ตกลง
        </button>
      </div>
    </div>
  );
}
