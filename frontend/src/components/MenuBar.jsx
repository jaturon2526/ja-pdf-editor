import AppBrand from "./AppBrand.jsx";
import React, { useEffect, useRef, useState } from "react";

const isMac = typeof navigator !== "undefined" && /Mac|iPod|iPhone|iPad/.test(navigator.platform);

function formatShortcut(sc) {
  if (!sc) return sc;
  
  // Clean up any explicit Mac overrides we previously added (e.g., "(Mac: ⌥Q)")
  let cleanSc = sc.replace(/\s*\(Mac:.*\)/i, "");
  
  if (!isMac) return cleanSc;
  
  // Convert Windows shortcuts to Mac format
  return cleanSc
    .replace(/Ctrl\+/g, "⌘")
    .replace(/Alt\+/g, "⌥")
    .replace(/Shift\+/g, "⇧");
}

export default function MenuBar({ menus, fileName }) {
  const [openIndex, setOpenIndex] = useState(null);
  const rootRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpenIndex(null);
      }
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setOpenIndex(null);
    }
    document.addEventListener("pointerdown", onDocClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onDocClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return (
    <div className="flex flex-wrap items-center min-h-[40px] py-1 bg-slate-800 text-slate-200 px-3 text-sm select-none relative z-50 shadow-sm" ref={rootRef}>
      {/* Mobile Hamburger Menu Button */}
      <div className="desk:hidden relative mr-2 shrink-0">
        <button 
          className={`p-1.5 rounded transition-colors focus:outline-none cursor-pointer ${openIndex === 'mobile' ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-700 hover:text-white"}`}
          onClick={() => setOpenIndex(openIndex === 'mobile' ? null : 'mobile')}
          title="เมนูหลัก"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        {/* Mobile Dropdown Menu (All Menus Combined) */}
        {openIndex === 'mobile' && (
          <div className="absolute top-full left-0 mt-2 w-[260px] max-h-[80vh] overflow-y-auto overscroll-contain bg-white text-slate-800 border border-slate-200 rounded shadow-2xl py-2 z-50 flex flex-col">
            {menus.map((menu, mIdx) => (
              <div key={menu.label} className="flex flex-col">
                <div className="px-4 py-1.5 text-xs font-bold text-sky-600 bg-slate-50 border-y border-slate-100 first:border-t-0 uppercase tracking-wide">
                  {menu.label}
                </div>
                {menu.items.map((item, i) =>
                  item.divider ? (
                    <div className="h-px bg-slate-100 my-1 mx-2" key={`div-${mIdx}-${i}`} />
                  ) : (
                    <button
                      key={`${menu.label}-${item.label}`}
                      className="w-full text-left px-4 py-2.5 text-[14px] hover:bg-sky-50 focus:bg-sky-50 focus:outline-none flex justify-between items-center group cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                      disabled={item.disabled}
                      onClick={() => { 
                        
                        setOpenIndex(null);
                        item.onClick && item.onClick();
                      }}
                    >
                      <span className="text-slate-700 group-hover:text-slate-900 group-disabled:text-slate-400">{item.label}{item.hint && <span className="block text-[11px] leading-tight text-slate-400">{item.hint}</span>}</span>
                    </button>
                  )
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="hidden desk:flex items-center justify-center w-6 h-6 mr-3 shrink-0">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
          <rect x="2" y="1" width="12" height="14" rx="1.5" fill="#0ea5e9" />
          <rect x="4.5" y="4" width="7" height="1.4" rx="0.7" fill="white" opacity="0.9" />
          <rect x="4.5" y="7" width="7" height="1.4" rx="0.7" fill="white" opacity="0.7" />
          <rect x="4.5" y="10" width="4.5" height="1.4" rx="0.7" fill="white" opacity="0.55" />
        </svg>
      </div>

      {/* Desktop Menus (Hidden on Mobile) */}
      {/* มือถือ: โลโก้ + ชื่อแอปข้าง ☰ (จอแคบมากเหลือแค่โลโก้ — ชื่อไฟล์ไม่ถูกบีบ) · ไม่เป็นลิงก์ กันกดพลาดออกจากเอกสาร */}
      <div className="desk:hidden min-w-0 shrink">
        <AppBrand variant="dark" size="sm" nameClassName="max-[359px]:hidden" />
      </div>

      <div className="hidden desk:flex flex-1 min-w-0 items-center lg:gap-1 flex-wrap">
        {menus.map((menu, idx) => (
          <div className="relative shrink-0" key={menu.label}>
            <button
              className={`px-2 lg:px-3 py-1.5 rounded whitespace-nowrap transition-colors focus:outline-none cursor-pointer ${openIndex === idx ? "bg-slate-700 text-white" : "hover:bg-slate-700 hover:text-white"}`}
              onClick={() => setOpenIndex(openIndex === idx ? null : idx)}
              onMouseEnter={() => openIndex !== null && setOpenIndex(idx)}
            >
              {menu.label}
            </button>
            {openIndex === idx && (
              <div className="absolute top-full left-0 mt-1 min-w-[220px] bg-white text-slate-800 border border-slate-200 rounded shadow-xl py-1 z-50">
                {menu.items.map((item, i) =>
                  item.divider ? (
                    <div className="h-px bg-slate-200 my-1 mx-2" key={`div-${i}`} />
                  ) : (
                    <button
                      key={item.label}
                      className="w-full text-left px-4 py-1.5 text-[13px] hover:bg-sky-50 focus:bg-sky-50 focus:outline-none flex justify-between items-center group cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                      disabled={item.disabled}
                      onClick={() => { 
                        
                        setOpenIndex(null);
                        item.onClick && item.onClick();
                      }}
                    >
                      <span className="text-slate-700 group-hover:text-slate-900 group-disabled:text-slate-400">{item.label}{item.hint && <span className="block text-[11px] leading-tight text-slate-400">{item.hint}</span>}</span>
                      {item.shortcut && <span className="text-slate-400 text-xs tracking-wider">{formatShortcut(item.shortcut)}</span>}
                    </button>
                  )
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="ml-auto px-3 py-1 bg-slate-900/50 rounded text-slate-400 text-xs truncate max-w-[120px] lg:max-w-[200px]" title={fileName || ""}>
        {fileName || "ยังไม่ได้เปิดไฟล์"}
      </div>
    </div>
  );
}
