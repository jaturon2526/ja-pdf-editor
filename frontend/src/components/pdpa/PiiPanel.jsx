// แผง "ตรวจหาข้อมูลส่วนบุคคล (PDPA)" ใน Editor — ไม่บังหน้าเอกสาร เพื่อให้เห็นกรอบไฮไลต์ก่อนปิดจริง
// สแกน → ตรวจทาน/ติ๊ก (คลิกรายการเพื่อกระโดดไปหน้านั้น) → ปิดทับถาวร (undo ได้) → ดาวน์โหลดรายงาน
import { useCallback, useEffect, useState } from "react";
import * as api from "../../api.js";
import PiiReviewList, { defaultPiiSelection, downloadPiiReport } from "./PiiReviewList.jsx";

export default function PiiPanel({ sessionId, fileName, onGoToPage, onHighlights, onApplied, onClose }) {
  const [phase, setPhase] = useState("scanning"); // scanning | review | applying | done | error
  const [scan, setScan] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [cleanMetadata, setCleanMetadata] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const runScan = useCallback(async () => {
    setPhase("scanning");
    setError("");
    setActiveId(null);
    try {
      const res = await api.scanPii(sessionId);
      setScan(res);
      setSelected(defaultPiiSelection(res.findings));
      setPhase("review");
    } catch (e) {
      setError(e.message || "ตรวจเอกสารไม่สำเร็จ");
      setPhase("error");
    }
  }, [sessionId]);

  useEffect(() => {
    runScan();
  }, [runScan]);

  // ส่งกรอบไฮไลต์ให้ PDFCanvas (เฉพาะตอนตรวจทาน)
  useEffect(() => {
    if (phase !== "review" || !scan) {
      onHighlights([]);
      return;
    }
    onHighlights(scan.findings.map((f) => ({ id: f.id, page: f.page, rects: f.rects, selected: selected.has(f.id), active: f.id === activeId })));
  }, [phase, scan, selected, activeId, onHighlights]);

  useEffect(() => () => onHighlights([]), [onHighlights]);

  async function apply() {
    setPhase("applying");
    setError("");
    try {
      const res = await api.redactPii(sessionId, [...selected], cleanMetadata);
      setResult(res);
      setPhase("done");
      await onApplied(res);
    } catch (e) {
      setError(e.status === 409 ? "เอกสารเปลี่ยนไปหลังสแกน — สแกนใหม่อีกครั้งก่อนปกปิด" : e.message || "ปกปิดไม่สำเร็จ");
      setPhase("review");
    }
  }

  function activate(f) {
    setActiveId(f.id);
    onGoToPage(f.page);
  }

  const nothing = selected.size === 0 && !cleanMetadata;

  return (
    <aside
      role="dialog"
      aria-label="ตรวจหาข้อมูลส่วนบุคคล (PDPA)"
      data-testid="pii-panel"
      className="fixed z-[45] inset-x-0 bottom-0 max-h-[70dvh] sm:inset-x-auto sm:right-4 sm:top-24 sm:bottom-4 sm:max-h-none sm:w-[380px] flex flex-col bg-white border border-gray-200 rounded-t-2xl sm:rounded-xl shadow-2xl"
    >
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
        <svg className="w-5 h-5 text-indigo-600 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
          <path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z" />
        </svg>
        <h3 className="flex-1 font-bold text-gray-900">ข้อมูลส่วนบุคคล (PDPA)</h3>
        <button type="button" onClick={onClose} aria-label="ปิด" className="p-1 rounded hover:bg-gray-100 text-gray-500">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 text-sm text-gray-600 space-y-3">
        {phase === "scanning" && <p>กำลังตรวจหาข้อมูลส่วนบุคคลทั้งเอกสาร...</p>}
        {phase === "error" && <p className="text-red-700">{error}</p>}
        {(phase === "review" || phase === "applying") && scan && (
          <>
            {scan.findings.length > 0 && (
              <p>
                พบ <strong className="text-gray-900">{scan.findings.length}</strong> รายการ — กรอบ<span className="text-orange-600 font-semibold">สีส้ม</span>บนหน้าเอกสารคือรายการที่เลือก
                คลิกข้อความเพื่อไปยังตำแหน่ง
              </p>
            )}
            {error && <p className="p-2.5 rounded-lg bg-red-50 text-red-700 border border-red-200" role="alert">{error}</p>}
            <PiiReviewList
              scan={scan}
              selected={selected}
              onChange={setSelected}
              cleanMetadata={cleanMetadata}
              onCleanMetadata={setCleanMetadata}
              activeId={activeId}
              onActivate={activate}
              maxHeightClass="max-h-none"
            />
            <p className="text-xs text-gray-500">ตรวจบนเซิร์ฟเวอร์ของระบบเท่านั้น ไม่ส่งข้อความไปยัง AI หรือบริการภายนอก</p>
          </>
        )}
        {phase === "done" && result && (
          <>
            <p className="p-3 rounded-lg bg-green-50 text-green-800 border border-green-200">
              ปกปิดแล้ว {result.redacted} รายการ{result.metadata_cleaned ? " และล้างข้อมูลเมตาแล้ว" : ""}
              — กด "บันทึก" เพื่อเก็บลงไฟล์ (ย้อนกลับได้ด้วย Undo)
            </p>
            {result.report.length > 0 && (
              <button type="button" className="text-blue-700 hover:underline" onClick={() => downloadPiiReport(result.report, fileName || "document.pdf")}>
                ดาวน์โหลดรายงานการปกปิด (CSV)
              </button>
            )}
          </>
        )}
      </div>

      <div className="flex flex-wrap justify-end gap-2 px-4 py-3 border-t border-gray-100">
        {phase === "review" || phase === "applying" ? (
          <>
            <button type="button" onClick={runScan} disabled={phase === "applying"} className="px-3 py-2 text-sm font-medium rounded-lg text-gray-700 border border-gray-300 hover:bg-gray-50 disabled:opacity-50">
              สแกนใหม่
            </button>
            <button
              type="button"
              onClick={apply}
              disabled={nothing || phase === "applying"}
              className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            >
              {phase === "applying" ? "กำลังปกปิด..." : selected.size ? `ปกปิด ${selected.size} รายการ` : "ล้างข้อมูลเมตา"}
            </button>
          </>
        ) : phase === "done" || phase === "error" ? (
          <>
            <button type="button" onClick={runScan} className="px-3 py-2 text-sm font-medium rounded-lg text-gray-700 border border-gray-300 hover:bg-gray-50">สแกนอีกครั้ง</button>
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-blue-600 hover:bg-blue-700">เสร็จสิ้น</button>
          </>
        ) : null}
      </div>
    </aside>
  );
}
