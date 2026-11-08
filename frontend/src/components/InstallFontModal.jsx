import React, { useMemo, useRef, useState } from "react";

import GoogleFontTab from "./fonts/GoogleFontTab.jsx";

const STYLE_DEFS = [
  { key: "regular", label: "ตัวปกติ (Regular)", required: true },
  { key: "bold", label: "ตัวหนา (Bold)", required: false },
  { key: "italic", label: "ตัวเอียง (Italic)", required: false },
  { key: "bold_italic", label: "ตัวหนาเอียง (Bold Italic)", required: false },
];
const STYLE_BADGE = { regular: "R", bold: "B", italic: "I", bold_italic: "BI" };

// ตรงกับ backend fonts.inspect_font_file / MAX_FONT_FILE_BYTES
export const FONT_ACCEPT = ".ttf,.otf,.woff,.woff2";
export const MAX_FONT_MB = 20;
export function fontFileProblem(file) {
  if (!file) return null;
  if (/\.ttc$/i.test(file.name)) return "ไฟล์ .ttc (หลายฟอนต์ในไฟล์เดียว) ยังไม่รองรับ — ใช้ไฟล์ .ttf หรือ .otf ของแต่ละสไตล์";
  if (!/\.(ttf|otf|woff2?)$/i.test(file.name)) return "รองรับเฉพาะไฟล์ .ttf, .otf, .woff หรือ .woff2";
  if (file.size > MAX_FONT_MB * 1024 * 1024) return `ไฟล์ฟอนต์ใหญ่เกิน ${MAX_FONT_MB} MB`;
  return null;
}

export default function InstallFontModal({
  fontFamilies,
  onInstallFamily,
  onAddStyle,
  onRemoveFamily,
  onInstallFromUrl,
  onClose,
  error,
  notice = [],
  submitting,
}) {
  const [label, setLabel] = useState("");
  const [filesByStyle, setFilesByStyle] = useState({});
  const [confirmDeleteKey, setConfirmDeleteKey] = useState(null);
  const [tab, setTab] = useState("google"); // google | file
  const fileInputRefs = useRef({});

  const [fileProblem, setFileProblem] = useState(null);

  function handleStyleFileChange(styleKey, e) {
    const file = e.target.files?.[0] ?? null;
    const problem = fontFileProblem(file);
    setFileProblem(problem);
    if (problem) {
      e.target.value = "";
      setFilesByStyle((prev) => ({ ...prev, [styleKey]: null }));
      return;
    }
    setFilesByStyle((prev) => ({ ...prev, [styleKey]: file }));
  }

  const canSubmitNew = !!filesByStyle.regular && !submitting;

  async function handleSubmitNew(e) {
    e.preventDefault();
    if (!canSubmitNew) return;
    const ok = await onInstallFamily(label.trim(), filesByStyle);
    if (ok) {
      setLabel("");
      setFilesByStyle({});
      Object.values(fileInputRefs.current).forEach((el) => {
        if (el) el.value = "";
      });
    }
  }

  const customFamilies = useMemo(() => fontFamilies.filter((f) => f.removable), [fontFamilies]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 sm:p-6" onClick={onClose}>
      <div 
        className="bg-white w-full max-w-2xl max-h-[90vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-fade-in-up" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center bg-gray-50">
          <div>
            <h2 className="text-xl font-bold text-gray-900">ติดตั้งฟอนต์ใหม่</h2>
            <p className="text-sm text-gray-500 mt-1">
              จากลิงก์ Google Fonts หรือไฟล์ .ttf/.otf/.woff/.woff2 — ฟอนต์ 1 ตระกูลมีได้สูงสุด 4 สไตล์
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors p-2 rounded-full hover:bg-gray-200">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="flex gap-1 p-1 mb-6 bg-gray-100 rounded-lg" role="tablist">
            {[{ key: "google", label: "จาก Google Fonts" }, { key: "file", label: "จากไฟล์" }].map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                className={`flex-1 px-3 py-2 rounded-md text-sm font-medium transition-colors ${tab === t.key ? "bg-white shadow text-blue-700" : "text-gray-600 hover:text-gray-900"}`}>
                {t.label}
              </button>
            ))}
          </div>
          {tab === "google" && <GoogleFontTab submitting={submitting} error={error} onInstall={onInstallFromUrl} />}
          {tab === "file" && (
          <form onSubmit={handleSubmitNew} className="space-y-6">
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ชื่อฟอนต์ที่จะแสดง <span className="text-gray-400 font-normal">(ไม่บังคับ — ไม่ใส่จะใช้ชื่อจากไฟล์)</span></label>
              <input
                type="text"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="เช่น TH Sarabun New"
                maxLength={80}
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-gray-900 border-b border-gray-200 pb-2">อัปโหลดไฟล์ตามสไตล์</h3>
              <div className="grid sm:grid-cols-2 gap-4">
                {STYLE_DEFS.map((s) => (
                  <div key={s.key} className="bg-gray-50 p-4 rounded-xl border border-gray-200">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      {s.label}
                      {s.required && <span className="text-red-500 ml-1">*</span>}
                    </label>
                    <input
                      ref={(el) => (fileInputRefs.current[s.key] = el)}
                      type="file"
                      accept={FONT_ACCEPT}
                      className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 transition-colors cursor-pointer"
                      onChange={(e) => handleStyleFileChange(s.key, e)}
                    />
                  </div>
                ))}
              </div>
            </div>

            {fileProblem && <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded text-red-700 text-sm" role="alert">{fileProblem}</div>}
            {error && <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded text-red-700 text-sm">{error}</div>}
            {notice.length > 0 && (
              <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded text-amber-900 text-sm space-y-1" role="status" data-testid="font-notice">
                <p className="font-medium">ติดตั้งแล้ว แต่ควรทราบ:</p>
                {notice.map((n) => <p key={n}>• {n}</p>)}
              </div>
            )}
            <p className="text-xs text-gray-500">ไฟล์ละไม่เกิน {MAX_FONT_MB} MB · ฟอนต์ที่ไม่มีตัวอักษรไทยใช้ได้กับข้อความภาษาอังกฤษเท่านั้น</p>

            <div className="flex justify-end pt-2">
              <button 
                type="submit" 
                className="inline-flex items-center px-6 py-2.5 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                disabled={!canSubmitNew}
              >
                {submitting ? (
                  <><svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>กำลังติดตั้ง...</>
                ) : (
                  "ติดตั้งฟอนต์"
                )}
              </button>
            </div>
          </form>
          )}

          <div className="mt-10">
            <h3 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
              <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path></svg>
              ฟอนต์ที่ติดตั้งเองไว้แล้ว
            </h3>
            
            {customFamilies.length === 0 ? (
              <div className="text-center py-8 bg-gray-50 rounded-xl border border-dashed border-gray-300 text-gray-500 text-sm">
                ยังไม่มีฟอนต์ที่ติดตั้งเอง
              </div>
            ) : (
              <div className="space-y-3">
                {customFamilies.map((f) => (
                  <div key={f.key} className="flex items-center justify-between p-4 bg-white rounded-xl border border-gray-200 shadow-sm hover:border-blue-300 transition-colors">
                    <span className="font-semibold text-gray-900">{f.label}</span>
                    <div className="flex items-center gap-3">
                      <div className="flex gap-1.5">
                        {STYLE_DEFS.map((s) =>
                          f.styles[s.key] ? (
                            <span
                              key={s.key}
                              className="flex items-center justify-center w-7 h-7 rounded text-xs font-bold bg-blue-100 text-blue-700"
                              title={`${s.label} — มีไฟล์แล้ว`}
                            >
                              {STYLE_BADGE[s.key]}
                            </span>
                          ) : (
                            // สไตล์ที่ยังไม่มีไฟล์: คลิกเพื่ออัปโหลดเพิ่มเข้า family เดิม (เดิมแสดงเฉยๆ เพิ่มไม่ได้)
                            <label
                              key={s.key}
                              className={`flex items-center justify-center w-7 h-7 rounded text-xs font-bold bg-gray-100 text-gray-400 border border-dashed border-gray-300 ${submitting ? "opacity-50" : "cursor-pointer hover:bg-blue-50 hover:text-blue-600"}`}
                              title={`${s.label} — ยังไม่มีไฟล์ (คลิกเพื่อเพิ่ม)`}
                            >
                              {STYLE_BADGE[s.key]}
                              <input
                                type="file"
                                accept={FONT_ACCEPT}
                                className="hidden"
                                disabled={submitting}
                                onChange={(e) => {
                                  const file = e.target.files?.[0];
                                  e.target.value = "";
                                  const problem = fontFileProblem(file);
                                  setFileProblem(problem);
                                  if (file && !problem) onAddStyle(f.key, s.key, file);
                                }}
                              />
                            </label>
                          )
                        )}
                      </div>
                      {confirmDeleteKey === f.key ? (
                        <div className="flex items-center gap-2 ml-2">
                          <span className="text-sm text-red-600 font-medium">ลบฟอนต์นี้?</span>
                          <button
                            type="button"
                            className="px-2 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 transition-colors"
                            onClick={() => {
                              onRemoveFamily(f.key);
                              setConfirmDeleteKey(null);
                            }}
                          >
                            ลบ
                          </button>
                          <button
                            type="button"
                            className="px-2 py-1 bg-gray-200 text-gray-700 text-xs rounded hover:bg-gray-300 transition-colors"
                            onClick={() => setConfirmDeleteKey(null)}
                          >
                            ยกเลิก
                          </button>
                        </div>
                      ) : (
                        <button 
                          type="button" 
                          className="text-gray-400 hover:text-red-600 transition-colors p-1.5 rounded-md hover:bg-red-50 ml-2" 
                          title="ลบฟอนต์นี้ (ทุกสไตล์)" 
                          onClick={() => setConfirmDeleteKey(f.key)}
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
