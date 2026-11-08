import React, { useState } from "react";
import * as api from "../api.js";

// ข้อความตอนค้นไม่เจอ — ใช้ร่วมกับเซ็นเซอร์จากหน้าเอกสารของฉัน (QuickFileAction)
export function notFoundText(keyword, imagePages, { ocr = false } = {}) {
  const base = `ไม่พบ "${keyword}" ในเอกสาร`;
  if (!imagePages?.length) return base;
  const how = ocr
    ? "กด \"อ่านข้อความในรูป (OCR)\" ด้านล่างแล้วค้นหาอีกครั้ง หรือใช้เครื่องมือกล่องทึบลากปิดทับ"
    : "ใช้เครื่องมือกล่องทึบลากปิดทับแทน";
  return `${base} — หน้า ${imagePages.join(", ")} มีรูปภาพ: ข้อความที่อยู่ในรูป (เช่น ลายเซ็นและชื่อผู้ลงนาม ตราประทับ เอกสารสแกน) ค้นหาด้วยคำตรงๆ ไม่ได้ ${how}`;
}

export default function SearchRedactModal({ open, onClose, session, onComplete }) {
  const [keyword, setKeyword] = useState("");
  const [isRegex, setIsRegex] = useState(false);
  const [isRedacting, setIsRedacting] = useState(false);
  const [message, setMessage] = useState({ type: "", text: "" });
  const [imagePages, setImagePages] = useState([]); // หน้าที่มีรูปภาพ (จากผลค้นไม่เจอ) — เสนอให้ OCR
  const [isOcring, setIsOcring] = useState(false);

  if (!open) return null;

  const handleClose = () => {
    setMessage({ type: "", text: "" });
    setKeyword("");
    setImagePages([]);
    onClose();
  };

  const handleOcr = async () => {
    setIsOcring(true);
    setMessage({ type: "success", text: "กำลังอ่านข้อความในรูปภาพ (OCR)... อาจใช้เวลาหลายวินาทีต่อหน้า" });
    try {
      const r = await api.addOcrTextLayer(session, imagePages.map((p) => p - 1));
      setImagePages([]);
      onComplete(); // หน้าเอกสารมีชั้นข้อความใหม่ (มองไม่เห็น) — เลิกทำได้
      if (!r.words) {
        setMessage({ type: "error", text: "อ่านข้อความในรูปไม่ได้ (รูปอาจไม่มีตัวอักษร หรือไม่ชัดพอ) — ใช้เครื่องมือกล่องทึบลากปิดทับแทน" });
        return;
      }
      await handleRedact();
    } catch (err) {
      setMessage({ type: "error", text: `อ่านข้อความในรูปไม่สำเร็จ: ${err.message}` });
    } finally {
      setIsOcring(false);
    }
  };

  const handleRedact = async () => {
    if (!keyword) return;
    setIsRedacting(true);
    try {
      const response = await api.fetchWithAuth(`/api/pdf/${session}/redact-search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword: keyword, match_case: false, is_regex: isRegex }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.redacted_count === 0) {
          // ไม่เจอ — ไม่ปิดหน้าต่าง ให้แก้คำค้นได้ · บอกหน้าที่มีรูปภาพ (ข้อความในรูปค้นด้วยคำไม่ได้)
          setMessage({ type: "error", text: notFoundText(keyword, data.image_pages, { ocr: true }) });
          setImagePages(data.image_pages || []);
          return;
        }
        setMessage({ type: "success", text: `ลบข้อความสำเร็จ! พบและเซ็นเซอร์ทั้งหมด ${data.redacted_count} จุด` });
        setTimeout(() => { setMessage({type:"", text:""}); onComplete(); onClose(); }, 2000);
        setKeyword("");
        
      } else {
        const errData = await response.json().catch(() => ({}));
        setMessage({ type: "error", text: `เกิดข้อผิดพลาด: ${errData.detail || response.statusText}` });
      }
    } catch (error) {
      console.error(error);
      setMessage({ type: "error", text: "ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้" });
    } finally {
      setIsRedacting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={handleClose}></div>
      <div className="relative mx-auto max-w-sm w-full rounded-xl bg-white p-6 shadow-2xl">
        <h3 className="text-lg font-medium text-slate-900 mb-4 flex items-center gap-2">
          <svg className="w-5 h-5 text-sky-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
          เซ็นเซอร์ด้วยคำค้นหา
        </h3>
        
          {message.text && (
            <div className={`p-3 rounded-lg text-sm mb-4 ${message.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'}`}>
              {message.text}
              {imagePages.length > 0 && (
                <button
                  type="button"
                  onClick={handleOcr}
                  disabled={isOcring || isRedacting}
                  data-testid="ocr-retry"
                  className="mt-2 block w-full px-3 py-2 rounded-lg bg-white border border-red-300 text-red-800 font-medium hover:bg-red-100 disabled:opacity-50"
                >
                  {isOcring ? "กำลังอ่านข้อความในรูป..." : "อ่านข้อความในรูป (OCR) แล้วค้นหาอีกครั้ง"}
                </button>
              )}
            </div>
          )}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">คำที่ต้องการเซ็นเซอร์ (ค้นหาทั้งเอกสาร)</label>
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="เช่น เลขบัตรประชาชน, ชื่อ"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            />

          <div>
            <label className="flex items-center gap-2 cursor-pointer mt-2">
              <input 
                type="checkbox" 
                checked={isRegex} 
                onChange={(e) => setIsRegex(e.target.checked)}
                className="w-4 h-4 text-sky-600 border-gray-300 rounded focus:ring-sky-500"
              />
              <span className="text-sm text-slate-700">ใช้ Regular Expression (Regex)</span>
            </label>
          </div>

          </div>
          <p className="text-xs text-orange-600 bg-orange-50 p-2 rounded border border-orange-100">
            * การเซ็นเซอร์จะเป็นการลบข้อความออกอย่างถาวรและไม่สามารถกู้คืนได้ (หลังกดบันทึก) โปรดตรวจสอบให้แน่ใจก่อนทำการเซ็นเซอร์
          </p>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
          >
            ยกเลิก
          </button>
          <button
            onClick={handleRedact}
            disabled={isRedacting || !keyword}
            className="px-4 py-2 text-sm font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {isRedacting ? "กำลังลบ..." : "เริ่มเซ็นเซอร์"}
          </button>
        </div>
      </div>
    </div>
  );
}
