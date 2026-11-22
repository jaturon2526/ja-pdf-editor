import React, { useState } from "react";
import * as api from "../api.js";

const PAPER_SIZES = [
  { id: "a4_portrait", label: "A4 แนวตั้ง (210 × 297 มม.)", width: 595, height: 842 },
  { id: "a4_landscape", label: "A4 แนวนอน (297 × 210 มม.)", width: 842, height: 595 },
  { id: "letter", label: "Letter แนวตั้ง (216 × 279 มม.)", width: 612, height: 792 },
  { id: "a5", label: "A5 แนวตั้ง (148 × 210 มม.)", width: 420, height: 595 },
];

/**
 * หน้าต่างสร้างเอกสาร PDF หน้าเปล่า (v1.47.0)
 * ใช้สร้างเอกสารเปล่าเพื่อออกแบบแบบฟอร์ม PDF หรือวางข้อความ/รูปภาพใหม่ได้ทันที
 */
export default function CreateBlankPdfModal({ onClose, onCreated, defaultOpenFormBuilder = true }) {
  const [filename, setFilename] = useState("แบบฟอร์มใหม่.pdf");
  const [sizeId, setSizeId] = useState("a4_portrait");
  const [pageCount, setPageCount] = useState(1);
  const [openFormBuilder, setOpenFormBuilder] = useState(defaultOpenFormBuilder);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    const cleanName = filename.trim() || "แบบฟอร์มใหม่.pdf";
    const size = PAPER_SIZES.find((s) => s.id === sizeId) || PAPER_SIZES[0];
    const pages = Math.max(1, Math.min(50, Number(pageCount) || 1));

    setSubmitting(true);
    setError("");
    try {
      const res = await api.createBlankPdf({
        filename: cleanName,
        width: size.width,
        height: size.height,
        pageCount: pages,
      });
      onCreated(res, { openFormBuilder });
    } catch (err) {
      setError(err?.message || "สร้างเอกสารเปล่าไม่สำเร็จ");
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 flex items-end sm:items-center justify-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="สร้างเอกสารเปล่า"
    >
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl shadow-2xl border border-slate-200 overflow-hidden"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
          <h2 className="text-base font-semibold text-slate-800">สร้างเอกสารเปล่า / แบบฟอร์มใหม่</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิดหน้าต่างสร้างเอกสารเปล่า"
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            ✕
          </button>
        </div>

        <div className="p-4 space-y-3.5 text-sm">
          <div>
            <label htmlFor="blank-pdf-filename" className="block text-xs font-medium text-slate-600 mb-1">
              ชื่อไฟล์
            </label>
            <input
              id="blank-pdf-filename"
              type="text"
              value={filename}
              maxLength={200}
              onChange={(e) => setFilename(e.target.value)}
              placeholder="เช่น ใบสมัครงาน.pdf"
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label htmlFor="blank-pdf-size" className="block text-xs font-medium text-slate-600 mb-1">
                ขนาดกระดาษ
              </label>
              <select
                id="blank-pdf-size"
                value={sizeId}
                onChange={(e) => setSizeId(e.target.value)}
                className="w-full px-2.5 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PAPER_SIZES.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="blank-pdf-pages" className="block text-xs font-medium text-slate-600 mb-1">
                จำนวนหน้า
              </label>
              <input
                id="blank-pdf-pages"
                type="number"
                min={1}
                max={50}
                value={pageCount}
                onChange={(e) => setPageCount(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none pt-1">
            <input
              type="checkbox"
              checked={openFormBuilder}
              onChange={(e) => setOpenFormBuilder(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <span>เปิดโหมดออกแบบแบบฟอร์ม (เพิ่มช่องกรอก) ทันที</span>
          </label>

          {error && (
            <div role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-slate-200 bg-slate-50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200/70 rounded-lg"
          >
            ยกเลิก
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
          >
            {submitting ? "กำลังสร้าง..." : "สร้างเอกสาร"}
          </button>
        </div>
      </form>
    </div>
  );
}
