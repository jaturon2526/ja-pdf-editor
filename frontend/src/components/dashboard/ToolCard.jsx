// การ์ดเครื่องมือบน Dashboard — มือถือแสดง 2 คอลัมน์แบบกะทัดรัด (ไอคอนบน ชื่อล่าง ซ่อนคำอธิบาย)
const COLORS = {
  blue: { hover: "hover:border-blue-500", icon: "bg-blue-50 text-blue-600 group-hover:bg-blue-100" },
  purple: { hover: "hover:border-purple-500", icon: "bg-purple-50 text-purple-600 group-hover:bg-purple-100" },
  green: { hover: "hover:border-green-500", icon: "bg-green-50 text-green-600 group-hover:bg-green-100" },
  orange: { hover: "hover:border-orange-500", icon: "bg-orange-50 text-orange-600 group-hover:bg-orange-100" },
  emerald: { hover: "hover:border-emerald-500", icon: "bg-emerald-50 text-emerald-600 group-hover:bg-emerald-100" },
  indigo: { hover: "hover:border-indigo-500", icon: "bg-indigo-50 text-indigo-600 group-hover:bg-indigo-100" },
  red: { hover: "hover:border-red-500", icon: "bg-red-50 text-red-600 group-hover:bg-red-100" },
  sky: { hover: "hover:border-sky-500", icon: "bg-sky-50 text-sky-600 group-hover:bg-sky-100" },
  teal: { hover: "hover:border-teal-500", icon: "bg-teal-50 text-teal-600 group-hover:bg-teal-100" },
};

export default function ToolCard({ title, description, color = "blue", icon, badge = null, onClick, testId }) {
  const c = COLORS[color] || COLORS.blue;
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={`relative flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-0 p-3 sm:p-4 bg-white border border-gray-200 rounded-xl ${c.hover} hover:shadow-md transition-all text-left group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500`}
    >
      <div className={`p-2.5 sm:p-3 rounded-lg sm:mr-4 transition-colors ${c.icon}`}>
        <svg className="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
          {icon}
        </svg>
      </div>
      <div className="min-w-0">
        <h4 className="font-semibold text-gray-900 text-sm sm:text-base leading-snug">{title}</h4>
        {description && <p className="hidden sm:block text-xs text-gray-500 mt-1">{description}</p>}
      </div>
      {badge != null && badge > 0 && (
        <span className="absolute top-2 right-2 min-w-[1.5rem] h-6 px-1.5 rounded-full bg-red-500 text-white text-xs font-bold flex items-center justify-center" aria-label={`${badge} รายการ`}>
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </button>
  );
}
