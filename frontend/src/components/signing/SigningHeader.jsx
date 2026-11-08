// แถบบนของหน้าการลงนาม: กลับไป Dashboard / รายการลงนาม + กระดิ่งแจ้งเตือน
// มือถือ: เหลือปุ่มย้อนกลับ (backTo) + ชื่อเรื่อง เพื่อไม่ให้ล้นจอ
import { Link } from "react-router-dom";
import NotificationBell from "./NotificationBell.jsx";

export default function SigningHeader({ title, backTo = "/signing" }) {
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-3 sm:px-4 h-14 flex items-center gap-2 sm:gap-3">
        <Link to="/dashboard" className="hidden sm:inline text-sm text-gray-600 hover:text-blue-600 whitespace-nowrap">← เอกสารของฉัน</Link>
        <span className="hidden sm:inline text-gray-300">|</span>
        <Link to="/signing" className="hidden sm:inline text-sm text-gray-600 hover:text-blue-600 whitespace-nowrap">การลงนาม</Link>
        <Link
          to={backTo}
          className="sm:hidden -ml-1 w-9 h-9 shrink-0 flex items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100"
          aria-label={backTo === "/dashboard" ? "กลับไปเอกสารของฉัน" : "กลับไปหน้าการลงนาม"}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </Link>
        <h1 className="sm:ml-2 text-base font-semibold text-gray-900 truncate flex-1 min-w-0">{title}</h1>
        <NotificationBell />
      </div>
    </header>
  );
}
