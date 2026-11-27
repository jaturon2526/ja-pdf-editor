// แถบค้นหาข้อความในเอกสาร (Ctrl+F, v1.42.0) — เดสก์ท็อปลอยมุมขวาบน, มือถือกว้างเต็มขอบ
import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";

export default function FindBar({ find }) {
  const { t } = useI18n();
  const inputRef = useRef(null);
  const {
    open,
    query,
    setQuery,
    matchCase,
    setMatchCase,
    matches,
    truncated,
    activeIndex,
    searching,
    error,
    focusTick,
    closeFind,
    next,
    prev,
  } = find;

  useEffect(() => {
    if (!open) return;
    const el = inputRef.current;
    if (el) {
      el.focus();
      el.select();
    }
  }, [open, focusTick]);

  if (!open) return null;

  let statusText = "";
  if (searching) {
    statusText = "กำลังค้นหา...";
  } else if (error) {
    statusText = error;
  } else if (matches.length > 0) {
    statusText = `${activeIndex + 1} / ${matches.length}${truncated ? "+" : ""}`;
  } else if (query.trim()) {
    statusText = "ไม่พบ";
  }

  function onKeyDown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (e.shiftKey) prev();
      else next();
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeFind();
    }
  }

  return (
    <div
      role="search"
      aria-label={t("modals.findPlaceholder")}
      data-testid="find-bar"
      className="fixed top-[92px] right-4 z-50 phone:inset-x-2 phone:right-auto bg-white border border-slate-300 rounded-xl shadow-xl px-2.5 py-2 flex items-center gap-1.5 max-w-full"
    >
      <input
        ref={inputRef}
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="ค้นหาในเอกสาร..."
        aria-label="คำที่ต้องการค้นหา"
        className="w-48 phone:flex-1 phone:min-w-0 px-2.5 py-1 text-base sm:text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-800"
      />
      <button
        type="button"
        onClick={() => setMatchCase((v) => !v)}
        aria-pressed={matchCase}
        title="ตรงตัวพิมพ์ใหญ่-เล็ก"
        aria-label="ตรงตัวพิมพ์ใหญ่-เล็ก"
        className={`px-2 py-1 text-xs font-semibold rounded-md border transition-colors cursor-pointer ${
          matchCase
            ? "bg-sky-100 text-sky-700 border-sky-300"
            : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
        }`}
      >
        Aa
      </button>
      {statusText && (
        <span
          role="status"
          data-testid="find-status"
          className={`text-xs px-1.5 whitespace-nowrap ${error ? "text-red-600" : "text-slate-500"}`}
        >
          {statusText}
        </span>
      )}
      <button
        type="button"
        onClick={prev}
        disabled={matches.length === 0}
        title="ผลลัพธ์ก่อนหน้า (Shift+Enter)"
        aria-label="ผลลัพธ์ก่อนหน้า"
        className="w-7 h-7 flex items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-40 cursor-pointer"
      >
        ↑
      </button>
      <button
        type="button"
        onClick={next}
        disabled={matches.length === 0}
        title="ผลลัพธ์ถัดไป (Enter)"
        aria-label="ผลลัพธ์ถัดไป"
        className="w-7 h-7 flex items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-40 cursor-pointer"
      >
        ↓
      </button>
      <button
        type="button"
        onClick={closeFind}
        title="ปิดแถบค้นหา (Esc)"
        aria-label="ปิดแถบค้นหา"
        className="w-7 h-7 flex items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 cursor-pointer"
      >
        ✕
      </button>
    </div>
  );
}
