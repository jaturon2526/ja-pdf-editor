// ข้อความภาษาไทยของสถานะ/ประเภทลายเซ็น
export const REQUEST_STATUS = {
  in_progress: { label: "กำลังลงนาม", className: "bg-amber-100 text-amber-800" },
  completed: { label: "ลงนามครบแล้ว", className: "bg-green-100 text-green-800" },
  rejected: { label: "ถูกปฏิเสธ", className: "bg-red-100 text-red-700" },
  cancelled: { label: "ยกเลิกแล้ว", className: "bg-gray-200 text-gray-700" },
};

export const STEP_STATUS = {
  waiting: "รอคิว",
  pending: "ถึงคิวลงนาม",
  signed: "ลงนามแล้ว",
  rejected: "ปฏิเสธ",
  skipped: "ไม่ต้องลงนามแล้ว", // คำขอถูกยกเลิก/ปฏิเสธก่อนถึงคนนี้
};

export const SIGN_TYPES = {
  either: "เลือกได้ (อิเล็กทรอนิกส์/ดิจิทัล)",
  electronic: "ลายเซ็นอิเล็กทรอนิกส์",
  digital: "ลายเซ็นดิจิทัล (ใบรับรอง)",
};

export const EVENT_LABELS = {
  created: "ส่งให้ลงนาม",
  viewed: "เปิดดูเอกสาร",
  signed: "ลงนาม",
  rejected: "ปฏิเสธ",
  cancelled: "ยกเลิก",
  completed: "ลงนามครบทุกคน",
  reminded: "ส่งเตือนผู้ลงนาม",
  invite_accepted: "รับคำเชิญ (ผูกบัญชี)",
};

export function formatDateTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

export function StatusBadge({ status }) {
  const s = REQUEST_STATUS[status] || { label: status, className: "bg-gray-100 text-gray-700" };
  return <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${s.className}`}>{s.label}</span>;
}

// วันครบกำหนด: แดงเมื่อเลยกำหนด (เฉพาะคำขอที่ยังรอลงนาม)
export function DueDate({ request }) {
  if (!request.due_at) return <span className="text-gray-400">-</span>;
  return (
    <span className={request.overdue ? "text-red-600 font-medium" : "text-gray-700"}>
      {formatDateTime(request.due_at)}
      {request.overdue && <span className="ml-1.5 text-xs text-white bg-red-600 rounded px-1.5 py-0.5">เลยกำหนด</span>}
    </span>
  );
}
