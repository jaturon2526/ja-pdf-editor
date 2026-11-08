// แปลง PDF เป็น Word — เลือกรูปแบบ แล้วแสดงความคืบหน้า/ผลลัพธ์ (แยกมาจาก Dashboard.jsx)
//
// โหมด:
// - editable : ข้อความไหลเป็นย่อหน้า/ตาราง แก้ไขต่อได้สะดวก (AI ช่วยแก้คำไทย ใช้โควต้า AI)
// - layout   : หน้าตาเหมือนต้นฉบับ (ภาพพื้นหลัง + กล่องข้อความวางตำแหน่งเดิม) เหมาะกับไฟล์ที่ออกแบบสวยๆ
//              หรือฟอร์มที่แค่จะกรอก/แก้คำ — ไม่ใช้โควต้า AI
// - scan     : ไฟล์สแกน (ตรวจอัตโนมัติ) — อ่านข้อความด้วย OCR บนเซิร์ฟเวอร์ ลายเซ็น/โลโก้/บาร์โค้ดเป็นรูป
//              AI แก้คำไทยเป็นตัวเลือก (ปิดเป็นค่าเริ่มต้น)
import { useState } from "react";

export const CONVERSION_MODES = [
  {
    key: "editable",
    title: "แก้ไขข้อความได้อิสระ",
    detail: "แปลงเป็นย่อหน้าและตาราง ข้อความไหลต่อกันเหมือนเอกสาร Word ทั่วไป AI ช่วยแก้คำไทย (ใช้โควต้า AI)",
    hint: "เหมาะกับ: รายงาน บทความ เอกสารที่ต้องแก้ไขเนื้อหามาก",
  },
  {
    key: "layout",
    title: "รักษาหน้าตาเหมือนต้นฉบับ",
    detail: "พื้นหลัง รูป และกราฟิกเหมือนต้นฉบับ ข้อความแต่ละบรรทัดเป็นกล่องที่แก้ไขได้ (ไม่ใช้โควต้า AI)",
    hint: "เหมาะกับ: ไฟล์ที่ออกแบบด้วย Canva/PowerPoint ฟอร์ม ใบงาน ที่แค่แก้คำหรือกรอกช่องว่าง",
  },
];

function ModalShell({ title, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm transition-opacity">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 transform transition-all text-center">
        <h3 className="text-lg font-bold text-gray-900 mb-2">{title}</h3>
        {children}
      </div>
    </div>
  );
}

// ข้อความของโหมด "แก้ไขข้อความได้อิสระ" เมื่อระบบไม่ได้ตั้ง AI (ไม่พูดถึง AI/โควต้า AI)
const EDITABLE_DETAIL_NO_AI = "แปลงเป็นย่อหน้าและตาราง ข้อความไหลต่อกันเหมือนเอกสาร Word ทั่วไป";
const LAYOUT_DETAIL_NO_AI = "พื้นหลัง รูป และกราฟิกเหมือนต้นฉบับ ข้อความแต่ละบรรทัดเป็นกล่องที่แก้ไขได้";

function ScanChooser({ filename, scan, onChoose, onCancel, aiAvailable = true }) {
  const [useAi, setUseAi] = useState(false);
  const tooMany = scan.max_pages && scan.pages > scan.max_pages;
  return (
    <ModalShell title="แปลงไฟล์สแกนเป็น Word">
      <p className="text-sm text-gray-500 mb-4 truncate" title={filename}>{filename}</p>
      <div className="text-left space-y-3" data-testid="scan-convert">
        <div className="p-3 rounded-lg bg-teal-50 border border-teal-100 text-sm text-teal-900">
          ไฟล์นี้เป็นไฟล์สแกน ระบบจะอ่านข้อความด้วย OCR ให้เป็นข้อความที่แก้ไขและคัดลอกได้ ฟอนต์ Sarabun
          ส่วนลายเซ็น โลโก้ ตราประทับ และบาร์โค้ด จะใส่เป็นรูปภาพ
        </div>
        {aiAvailable && (
        <label className="flex items-start gap-2 p-3 rounded-lg border border-gray-200 cursor-pointer">
          <input type="checkbox" className="mt-1" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} data-testid="scan-convert-ai" />
          <span className="text-sm text-gray-700">
            ให้ AI ช่วยแก้คำไทยที่ OCR อ่านผิด
            <span className="block text-xs text-gray-400">ใช้โควต้า AI · ข้อความในเอกสารจะถูกส่งไปประมวลผลที่ผู้ให้บริการ AI ที่ตั้งไว้ (ดูที่เมนู API Key สำหรับ AI)</span>
          </span>
        </label>
        )}
        <p className="text-xs text-gray-400">
          ใช้เวลาประมาณ 5–15 วินาทีต่อหน้า ({scan.pages} หน้า) · ผลลัพธ์ควรตรวจทานก่อนนำไปใช้ — OCR อาจอ่านผิดบางคำ และลายมือเขียนจะเป็นรูป
        </p>
        {tooMany && (
          <p className="text-sm text-red-600">แปลงไฟล์สแกนได้ครั้งละไม่เกิน {scan.max_pages} หน้า — แยกไฟล์ก่อน (เมนู แยกหน้า)</p>
        )}
      </div>
      <div className="mt-5 flex justify-center gap-2">
        <button type="button" onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
          ยกเลิก
        </button>
        <button type="button" disabled={tooMany} onClick={() => onChoose("scan", { useAi: aiAvailable && useAi })}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
          แปลงเป็น Word
        </button>
      </div>
    </ModalShell>
  );
}

export function ConversionModeChooser({ filename, onChoose, onCancel, inspecting = false, scan = null, aiAvailable = true }) {
  if (inspecting) {
    return (
      <ModalShell title="แปลงไฟล์ PDF เป็น Word">
        <p className="text-sm text-gray-500 py-6">กำลังตรวจไฟล์...</p>
      </ModalShell>
    );
  }
  if (scan) return <ScanChooser filename={filename} scan={scan} onChoose={onChoose} onCancel={onCancel} aiAvailable={aiAvailable} />;
  return (
    <ModalShell title="แปลงไฟล์ PDF เป็น Word">
      <p className="text-sm text-gray-500 mb-4 truncate" title={filename}>{filename}</p>
      <div className="space-y-3 text-left">
        {CONVERSION_MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => onChoose(m.key)}
            className="w-full p-4 rounded-xl border border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition-colors text-left"
          >
            <div className="font-semibold text-gray-900">{m.title}</div>
            <div className="text-sm text-gray-600 mt-1">
              {aiAvailable ? m.detail : m.key === "editable" ? EDITABLE_DETAIL_NO_AI : LAYOUT_DETAIL_NO_AI}
            </div>
            <div className="text-xs text-gray-400 mt-1">{m.hint}</div>
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={onCancel}
        className="mt-4 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
      >
        ยกเลิก
      </button>
    </ModalShell>
  );
}

export default function ConversionModal({ task, mode, onClose, aiAvailable = true }) {
  const title = mode === "layout" ? "แปลงไฟล์ PDF เป็น Word (รักษาหน้าตา)"
    : mode === "scan" ? "แปลงไฟล์สแกนเป็น Word (OCR)" : aiAvailable ? "แปลงไฟล์ PDF เป็น Word (AI)" : "แปลงไฟล์ PDF เป็น Word";
  if (task.status === "failed") {
    return (
      <ModalShell title={title}>
        <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-100">
          เกิดข้อผิดพลาด: {task.error_message || "ไม่ทราบสาเหตุ"}
        </div>
        <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-lg hover:bg-red-700">
          ปิด
        </button>
      </ModalShell>
    );
  }
  if (task.status === "completed") {
    return (
      <ModalShell title={title}>
        <div className="mb-4 p-3 bg-green-50 text-green-700 text-sm rounded-lg border border-green-100">
          แปลงไฟล์สำเร็จ! เริ่มต้นการดาวน์โหลด...
        </div>
        <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-lg hover:bg-blue-700">
          ปิด
        </button>
      </ModalShell>
    );
  }
  return (
    <ModalShell title={title}>
      <p className="text-sm text-gray-500 mb-4">
        {mode === "scan" ? "กำลังอ่านข้อความทีละหน้า..." : "กำลังประมวลผล..."} โปรดอย่าปิดหน้าจอนี้ ({task.progress}%)
      </p>
      <div className="w-full bg-gray-100 rounded-full h-3 mb-4">
        <div className="bg-blue-600 h-3 rounded-full transition-all duration-500" style={{ width: `${task.progress}%` }}></div>
      </div>
    </ModalShell>
  );
}
