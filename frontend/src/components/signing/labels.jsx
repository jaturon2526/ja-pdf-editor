// สถานะ/ประเภทลายเซ็น และคอมโพเนนต์แสดงผล (รองรับ TH/EN)
import { useI18n } from "../../i18n/I18nContext.jsx";

export const REQUEST_STATUS_CLASS = {
  in_progress: "bg-amber-100 text-amber-800",
  completed: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-gray-200 text-gray-700",
};

export const SIGN_TYPE_KEYS = ["either", "electronic", "digital"];

export function formatDateTime(iso, lang = "th") {
  if (!iso) return "";
  return new Date(iso).toLocaleString(lang === "en" ? "en-US" : "th-TH", { dateStyle: "medium", timeStyle: "short" });
}

export function StatusBadge({ status }) {
  const { t } = useI18n();
  const className = REQUEST_STATUS_CLASS[status] || "bg-gray-100 text-gray-700";
  const label = REQUEST_STATUS_CLASS[status] ? t(`signingFlow.status.${status}`) : status;
  return <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${className}`}>{label}</span>;
}

// วันครบกำหนด: แดงเมื่อเลยกำหนด (เฉพาะคำขอที่ยังรอลงนาม)
export function DueDate({ request }) {
  const { lang, t } = useI18n();
  if (!request.due_at) return <span className="text-gray-400">-</span>;
  return (
    <span className={request.overdue ? "text-red-600 font-medium" : "text-gray-700"}>
      {formatDateTime(request.due_at, lang)}
      {request.overdue && <span className="ml-1.5 text-xs text-white bg-red-600 rounded px-1.5 py-0.5">{t("signingFlow.overdue")}</span>}
    </span>
  );
}
