// กระดิ่งแจ้งเตือน (ถึงคิวลงนาม / มีคนลงนาม / ถูกปฏิเสธ / ลงนามครบ) — ดึงใหม่ทุก 60 วินาที
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getNotifications, markNotificationsRead } from "../../api/signing.js";
import { useI18n } from "../../i18n/I18nContext.jsx";

const POLL_MS = 60000;

/**
 * แปลข้อความแจ้งเตือนที่ถูกบันทึกไว้ใน DB (กรณีผู้ใช้สลับภาษาเป็น EN ภายหลัง)
 * ครอบคลุมทั้งการลงนาม (signing_service) และรับบริจาค/แพ็กเกจ (donation_service)
 */
const EN_PATTERNS = [
  [/^ถึงคิวคุณลงนาม "(.+)" \(ส่งโดย (.+)\)$/, (_, title, owner) => `Your turn to sign "${title}" (sent by ${owner})`],
  [/^"(.+)" ลงนามครบทุกคนแล้ว$/, (_, title) => `"${title}" has been signed by everyone`],
  [/^(.+) ลงนาม "(.+)" แล้ว \((.+)\)$/, (_, who, title, progress) => `${who} signed "${title}" (${progress})`],
  [/^(.+) ลงนาม "(.+)" แล้ว$/, (_, who, title) => `${who} signed "${title}"`],
  [/^(.+) ปฏิเสธการลงนาม "(.+)"$/, (_, who, title) => `${who} declined to sign "${title}"`],
  [/^(.+) ลบบัญชีแล้ว — คำขอ "(.+)" ถูกปฏิเสธอัตโนมัติ$/, (_, who, title) => `${who} deleted their account — signing request "${title}" was automatically declined`],
  [/^(.+) ยกเลิกคำขอลงนาม "(.+)"$/, (_, who, title) => `${who} cancelled the signing request "${title}"`],
  [/^(.+) เตือนให้ลงนาม "(.+)"$/, (_, who, title) => `${who} sent a reminder to sign "${title}"`],
  [/^"(.+)" เลยกำหนดลงนามแล้ว \(รอ (.+)\)$/, (_, title, names) => `"${title}" is overdue for signing (waiting for ${names})`],
  [/^"(.+)" เลยกำหนดลงนามแล้ว — รอคุณลงนาม$/, (_, title) => `"${title}" is overdue — waiting for your signature`],
  [/^"(.+)" เกินกำหนดลงนามแล้ว$/, (_, title) => `"${title}" is overdue for signing`],
  [/^"(.+)" ใกล้ครบกำหนดลงนาม$/, (_, title) => `"${title}" is due soon for signing`],
  [/^แจ้งเตือนลงนาม "(.+)"$/, (_, title) => `Reminder to sign "${title}"`],
  [/^มีผู้แจ้งโอนสนับสนุน ([\d,.]+) บาท — รอตรวจสอบ$/, (_, amt) => `New support transfer reported (${amt} THB) — pending review`],
  [/^มีแจ้งโอนสนับสนุน ฿([\d,.]+) จาก (.+)$/, (_, amt, who) => `New donation report of ฿${amt} from ${who}`],
  [/^ขอบคุณที่สนับสนุน ([\d,.]+) บาท(?: — ได้รับสิทธิ์ (\S+) (\d+) วัน)?$/, (_, amt, plan, days) => (plan ? `Thank you for supporting ${amt} THB — ${plan} plan granted for ${days} days` : `Thank you for supporting ${amt} THB`)],
  [/^ได้รับเงินสนับสนุนแล้ว — ขอบคุณมากครับ(?: \(ได้รับสิทธิ์ (\S+) (\d+) วัน\))?$/, (_, plan, days) => (plan ? `Donation verified — thank you! (${plan} for ${days} days)` : "Donation verified — thank you!")],
  [/^ไม่พบยอดโอนที่แจ้งไว้(.*?) — ติดต่อผู้ดูแลระบบได้$/, (_, reason) => `Transfer could not be verified${reason || ""} — please contact support`],
  [/^ไม่พบยอดโอนสนับสนุน(?:: (.+))?$/, (_, note) => (note ? `Donation transfer not found: ${note}` : "Donation transfer not found")],
  [/^สิทธิ์ผู้สนับสนุน \((.+)\) ครบกำหนดแล้ว — ขอบคุณที่ร่วมสนับสนุน$/, (_, plan) => `Your supporter plan (${plan}) has expired — thank you for your support`],
  [/^สิทธิ์ผู้สนับสนุนหมดอายุแล้ว — กลับเป็นแพ็กเกจฟรี$/, () => "Supporter perks expired — reverted to Free plan"],
];

function localizeNotificationTitle(title, lang) {
  if (!title || lang !== "en") return title;
  for (const [re, format] of EN_PATTERNS) {
    const m = title.match(re);
    if (m) return format(...m);
  }
  return title;
}

export default function NotificationBell() {
  const { lang, t } = useI18n();
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
    if (item.request_id) void navigate(`/signing/${item.request_id}`);
    else if (item.kind === "donation_new") void navigate("/admin");
    else if (item.kind?.startsWith("donation_") || item.kind === "plan_expired") void navigate("/support");
  }

  return (
    <div className="relative">
      <button
        type="button"
        aria-label={t("notifications.title")}
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
            <span className="text-sm font-semibold text-gray-800">{t("notifications.title")}</span>
            {data.unread > 0 && (
              <button
                type="button"
                className="text-xs text-blue-600 hover:underline"
                onClick={() => void markNotificationsRead().then(refresh).catch(() => { /* ไม่สำเร็จ — รอรอบถัดไป */ })}
              >
                {t("notifications.markAllRead")}
              </button>
            )}
          </div>
          {data.items.length === 0 ? (
            <p className="px-4 py-6 text-sm text-gray-400 text-center">{t("notifications.empty")}</p>
          ) : (
            data.items.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() => void openItem(item)}
                className={`w-full text-left px-4 py-3 text-sm border-b border-gray-50 hover:bg-blue-50 ${item.read ? "text-gray-500" : "text-gray-900 font-medium bg-blue-50/40"}`}
              >
                {localizeNotificationTitle(item.title, lang)}
                <span className="block text-xs text-gray-400 mt-0.5">
                  {item.created_at ? new Date(item.created_at).toLocaleString(lang === "en" ? "en-US" : "th-TH", { dateStyle: "medium", timeStyle: "short" }) : ""}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
