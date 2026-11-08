// กระดิ่งแจ้งเตือน (ถึงคิวลงนาม / มีคนลงนาม / ถูกปฏิเสธ / ลงนามครบ) — ดึงใหม่ทุก 60 วินาที
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getNotifications, markNotificationsRead } from "../../api/signing.js";

const POLL_MS = 60000;

export default function NotificationBell() {
  const navigate = useNavigate();
  const [data, setData] = useState({ unread: 0, items: [] });
  const [open, setOpen] = useState(false);

  const refresh = useCallback(() => {
    getNotifications().then(setData).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  async function openItem(item) {
    setOpen(false);
    if (!item.read) {
      await markNotificationsRead([item.id]).catch(() => {});
      refresh();
    }
    if (item.request_id) navigate(`/signing/${item.request_id}`);
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-label="การแจ้งเตือน"
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg text-slate-600 hover:text-blue-600 hover:bg-blue-50"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0a3 3 0 11-6 0" />
        </svg>
        {data.unread > 0 && (
          <span data-testid="notification-badge" className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[11px] font-bold flex items-center justify-center">
            {data.unread > 99 ? "99+" : data.unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-w-[calc(100vw-1rem)] max-h-96 overflow-y-auto bg-white rounded-xl shadow-lg border border-gray-100 z-20">
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
            <span className="text-sm font-semibold text-gray-800">การแจ้งเตือน</span>
            {data.unread > 0 && (
              <button
                type="button"
                className="text-xs text-blue-600 hover:underline"
                onClick={() => markNotificationsRead().then(refresh).catch(() => {})}
              >
                อ่านทั้งหมด
              </button>
            )}
          </div>
          {data.items.length === 0 ? (
            <p className="px-4 py-6 text-sm text-gray-400 text-center">ยังไม่มีการแจ้งเตือน</p>
          ) : (
            data.items.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => openItem(item)}
                className={`w-full text-left px-4 py-3 text-sm border-b border-gray-50 hover:bg-blue-50 ${item.read ? "text-gray-500" : "text-gray-900 font-medium bg-blue-50/40"}`}
              >
                {item.title}
                <span className="block text-xs text-gray-400 mt-0.5">
                  {item.created_at ? new Date(item.created_at).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" }) : ""}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
