// เลือกไฟล์จาก "เอกสารของฉัน" 1 ไฟล์ (ใช้กับ "ส่งเอกสารให้ลงนาม" และ "แปลงเป็น Word" บน Dashboard)
import { useEffect, useState } from "react";

export default function ChooseFileModal({ title, subtitle = "", emptyText = "ยังไม่มีเอกสาร — อัปโหลด PDF ก่อน แล้วค่อยส่งให้ลงนาม", files, onChoose, onCancel }) {
  const [query, setQuery] = useState("");
  const shown = files.filter((f) => f?.filename?.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="choose-file-title"
        className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[80vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-gray-100">
          <h3 id="choose-file-title" className="text-lg font-bold text-gray-900">{title}</h3>
          {subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
          {files.length > 5 && (
            <input
              type="search"
              autoFocus
              placeholder="ค้นหาเอกสาร..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mt-3 block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
          )}
        </div>
        <ul className="overflow-y-auto divide-y divide-gray-100">
          {shown.length === 0 && (
            <li className="p-6 text-center text-sm text-gray-500">
              {files.length === 0 ? emptyText : "ไม่พบเอกสารที่ค้นหา"}
            </li>
          )}
          {shown.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                onClick={() => onChoose(f)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-blue-50 focus:bg-blue-50 focus:outline-none"
              >
                <svg className="w-5 h-5 shrink-0 text-gray-400" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" /></svg>
                <span className="text-sm text-gray-900 truncate">{f.filename}</span>
              </button>
            </li>
          ))}
        </ul>
        <div className="p-3 border-t border-gray-100 flex justify-end">
          <button type="button" onClick={onCancel} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
            ยกเลิก
          </button>
        </div>
      </div>
    </div>
  );
}
