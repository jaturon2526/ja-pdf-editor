// กรอบหน้าต่างลงนาม: มือถือ = เต็มจอ (ปุ่มยืนยันติดด้านล่างเสมอ) · จอใหญ่ = การ์ดกลางจอ
import { useEffect } from "react";

export default function SignModalShell({ title, subtitle, icon, onCancel, footer, children, labelledBy = "sign-modal-title" }) {
  // ล็อกการเลื่อนหน้าหลังระหว่างเปิด (กันหน้าเลื่อนตอนเซ็นบน iOS)
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  return (
    <div className="fixed inset-0 z-[100] flex items-stretch sm:items-center justify-center bg-black/50 backdrop-blur-sm sm:p-6 short:p-0" onClick={onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className="bg-white text-slate-900 w-full sm:max-w-xl h-[100dvh] sm:h-auto sm:max-h-[92dvh] sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden short:h-[100dvh] short:max-h-none short:max-w-none short:rounded-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 sm:px-6 py-3 sm:py-4 short:py-1.5 border-b border-slate-200 bg-slate-50 flex items-start short:items-center gap-3 pt-[max(0.75rem,env(safe-area-inset-top))] short:pt-1.5">
          <div className="min-w-0 flex-1">
            <h2 id={labelledBy} className="text-lg sm:text-xl short:text-base font-bold text-slate-900 flex items-center gap-2">
              {icon}
              {title}
            </h2>
            {subtitle && <p className="text-sm text-slate-500 mt-0.5 short:hidden">{subtitle}</p>}
          </div>
          <button type="button" onClick={onCancel} aria-label="ปิด" className="p-2 -mr-2 rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-200">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 sm:px-6 py-4 short:py-2 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))]">{children}</div>
        <div className="px-4 sm:px-6 py-3 short:py-1.5 border-t border-slate-200 bg-white flex justify-end gap-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] short:pb-1.5">
          {footer}
        </div>
      </div>
    </div>
  );
}
