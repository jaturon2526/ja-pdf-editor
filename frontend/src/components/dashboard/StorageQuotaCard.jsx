import { formatBytes } from "../../utils/format.js";
import { useI18n } from "../../i18n/I18nContext.jsx";

// การ์ดพื้นที่จัดเก็บ + โควต้าแปลงไฟล์ด้วย AI ฟรีรายวัน (แยกมาจาก Dashboard.jsx)
export default function StorageQuotaCard({ quota, aiQuota }) {
  const { t } = useI18n();
  const freeSize = formatBytes(Math.max(0, quota.limit - quota.used));
  return (
    <div className="mb-8 bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-6">
      <div className="w-full flex-1">
         <div className="flex justify-between text-sm mb-2 text-gray-700 font-medium">
            <span>{t("dash.quota.usedTitle")}</span>
            <span>{formatBytes(quota.used)} / {formatBytes(quota.limit)}</span>
         </div>
         <div className="w-full bg-gray-100 rounded-full h-2.5">
            <div className={`h-2.5 rounded-full ${quota.used / quota.limit > 0.9 ? 'bg-red-500' : 'bg-blue-600'}`} style={{width: `${Math.min(100, (quota.used/quota.limit)*100)}%`}}></div>
         </div>
         <div className="text-xs text-gray-400 mt-1 sm:hidden">
           {t("dash.quota.freeSpaceShort", { size: freeSize })}
         </div>
      </div>
      
      {/* กล่องนี้คือโควต้า AI ของระบบ — ผู้ดูแลยังไม่ได้ตั้ง AI (AI_PROVIDER/AI_API_KEY) = ไม่แสดง */}
      {aiQuota?.system_ai && (() => {
        // จำนวนครั้งต่อวันมาจาก backend (AI_SYSTEM_DAILY_LIMIT) ไม่ฮาร์ดโค้ดไว้ที่หน้าเว็บ
        const used = aiQuota.system_requests_today || 0;
        const limit = aiQuota.system_daily_limit ?? 2;
        const exhausted = used >= limit;
        return (
        <div className="w-full sm:w-64 border-t sm:border-t-0 sm:border-l border-gray-200 pt-4 sm:pt-0 sm:pl-6 flex flex-col justify-center">
          <div className="flex justify-between text-sm mb-2 text-gray-700 font-medium">
              <span>{t("dash.quota.aiTitle")}</span>
              <span>{t("dash.quota.aiCount", { used, limit })}</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2.5 mb-1">
              <div className={`h-2.5 rounded-full ${exhausted ? 'bg-orange-500' : 'bg-green-500'}`} style={{width: `${limit > 0 ? Math.min(100, (used / limit) * 100) : 100}%`}}></div>
          </div>
          {exhausted && (
              <div className="text-[11px] leading-tight text-orange-600 mt-1">
                {t("dash.quota.aiExhaustedTitle")}<br/>{t("dash.quota.aiExhaustedHint")}
              </div>
          )}
        </div>
        );
      })()}
      
      <div className="text-sm font-medium text-gray-500 bg-gray-50 px-4 py-2 rounded-lg border border-gray-100 hidden sm:block whitespace-nowrap">
         {t("dash.quota.freeSpace", { size: freeSize })}
      </div>
    </div>
  );
}
