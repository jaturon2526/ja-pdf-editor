import React, { useEffect, useState } from "react";

export default function StatusBar({
  currentPage,
  pageCount,
  onGoToPage,
  onPrev,
  onNext,
  hasDocument,
}) {
  const [pageInput, setPageInput] = useState(String(currentPage + 1));

  useEffect(() => {
    setPageInput(String(currentPage + 1));
  }, [currentPage]);

  function commitPageInput() {
    const n = parseInt(pageInput, 10);
    if (!Number.isNaN(n) && n >= 1 && n <= pageCount) {
      onGoToPage(n - 1);
    } else {
      setPageInput(String(currentPage + 1));
    }
  }

  return (
    <div className="flex items-center justify-between h-8 bg-slate-100 border-t border-slate-200 px-4 text-xs text-slate-600 shrink-0 z-10 shadow-[0_-1px_2px_rgba(0,0,0,0.02)]">
      <div className="flex items-center gap-1">
        <button 
          className="flex items-center justify-center w-6 h-6 rounded hover:bg-slate-200 disabled:opacity-40 disabled:hover:bg-transparent transition-colors font-bold" 
          onClick={onPrev} 
          disabled={!hasDocument || currentPage <= 0} 
          title="หน้าก่อนหน้า"
        >
          ‹
        </button>
        <span className="flex items-center mx-1">
          <input
            className="w-10 h-5 text-center text-xs bg-white border border-slate-300 rounded mx-1 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 disabled:bg-slate-50"
            aria-label="หน้าปัจจุบัน"
            value={pageInput}
            disabled={!hasDocument}
            onChange={(e) => setPageInput(e.target.value)}
            onBlur={commitPageInput}
            onKeyDown={(e) => e.key === "Enter" && commitPageInput()}
          />
          <span className="text-slate-500 ml-1">/ {pageCount || 0}</span>
        </span>
        <button
          className="flex items-center justify-center w-6 h-6 rounded hover:bg-slate-200 disabled:opacity-40 disabled:hover:bg-transparent transition-colors font-bold"
          onClick={onNext}
          disabled={!hasDocument || currentPage >= pageCount - 1}
          title="หน้าถัดไป"
        >
          ›
        </button>
      </div>
      <div className="text-[10px] text-slate-400">พร้อมใช้งาน</div>
    </div>
  );
}
