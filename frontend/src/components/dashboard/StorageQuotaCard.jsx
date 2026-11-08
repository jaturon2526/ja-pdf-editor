import { formatBytes } from "../../utils/format.js";

// การ์ดพื้นที่จัดเก็บ + โควต้าแปลงไฟล์ด้วย AI ฟรีรายวัน (แยกมาจาก Dashboard.jsx)
export default function StorageQuotaCard({ quota, aiQuota }) {
  return (
    <div className="mb-8 bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-6">
      <div className="w-full flex-1">
         <div className="flex justify-between text-sm mb-2 text-gray-700 font-medium">
            <span>พื้นที่ใช้งานของคุณ</span>
            <span>{formatBytes(quota.used)} / {formatBytes(quota.limit)}</span>
         </div>
         <div className="w-full bg-gray-100 rounded-full h-2.5">
            <div className={`h-2.5 rounded-full ${quota.used / quota.limit > 0.9 ? 'bg-red-500' : 'bg-blue-600'}`} style={{width: `${Math.min(100, (quota.used/quota.limit)*100)}%`}}></div>
         </div>
         <div className="text-xs text-gray-400 mt-1 sm:hidden">
           เหลือที่ว่าง {formatBytes(Math.max(0, quota.limit - quota.used))}
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
              <span>โควต้าแปลงไฟล์ฟรี (AI)</span>
              <span>{used} / {limit} ครั้ง</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2.5 mb-1">
              <div className={`h-2.5 rounded-full ${exhausted ? 'bg-orange-500' : 'bg-green-500'}`} style={{width: `${limit > 0 ? Math.min(100, (used / limit) * 100) : 100}%`}}></div>
          </div>
          {exhausted && (
              <div className="text-[11px] leading-tight text-orange-600 mt-1">
                ⚠️ โควต้าฟรีรายวันหมดแล้ว<br/>(ระบบจะเปลี่ยนไปใช้ API Key ส่วนตัว หรือจัดเรียงคำพื้นฐานแทน)
              </div>
          )}
        </div>
        );
      })()}
      
      <div className="text-sm font-medium text-gray-500 bg-gray-50 px-4 py-2 rounded-lg border border-gray-100 hidden sm:block whitespace-nowrap">
         เหลือพื้นที่ {formatBytes(Math.max(0, quota.limit - quota.used))}
      </div>
    </div>
  );
}
