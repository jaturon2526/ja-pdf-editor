// แผง "ตรวจฟอนต์": รายละเอียดข้อความที่เลือก หรือสรุปฟอนต์ในหน้านี้ · เดสก์ท็อปอยู่ขวา มือถือเป็นแผ่นล่าง
import SourceFontList from "../fonts/SourceFontList.jsx";

export default function FontInspectorPanel({ inspector, onClose, onShowDocumentFonts }) {
  const { spans, pageFonts, selected, setSelected, error } = inspector;
  const span = selected != null ? spans?.[selected] : null;
  return (
    <aside aria-labelledby="font-inspector-title" data-testid="font-inspector-panel"
      className="bg-white border-slate-200 flex flex-col shrink-0
        desk:w-72 desk:border-l
        phone:fixed phone:inset-x-0 phone:bottom-0 phone:z-40 phone:max-h-[45dvh] phone:border-t phone:rounded-t-2xl phone:shadow-2xl">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200">
        <h3 id="font-inspector-title" className="text-sm font-semibold text-slate-900">ตรวจฟอนต์</h3>
        <button type="button" onClick={onClose} aria-label="ปิดเครื่องมือตรวจฟอนต์" className="icon-btn">✕</button>
      </div>
      <div className="p-3 overflow-y-auto text-sm space-y-3">
        {error && <p className="text-red-600" role="alert">{error}</p>}
        {spans === null && !error && <p className="text-slate-500">กำลังอ่านข้อมูลฟอนต์...</p>}
        {spans?.length === 0 && !error && (
          <p className="text-slate-600">หน้านี้ไม่มีข้อความ (อาจเป็นภาพสแกน) — ใช้ “อ่านข้อความในรูปภาพ (OCR)” ก่อน</p>
        )}
        {span ? (
          <section aria-label="ข้อความที่เลือก" className="space-y-2">
            <p className="text-xs text-slate-500">ข้อความที่เลือก</p>
            <p className="text-slate-900 break-words bg-slate-50 rounded px-2 py-1">{span.text}</p>
            <SourceFontList fonts={[span]} />
            <button type="button" onClick={() => setSelected(null)} className="text-xs text-blue-700 hover:underline">
              ← ดูฟอนต์ทั้งหน้านี้
            </button>
          </section>
        ) : spans?.length > 0 && (
          <section aria-label="ฟอนต์ในหน้านี้" className="space-y-2">
            <p className="text-xs text-slate-500">ชี้หรือแตะข้อความบนหน้าเพื่อดูฟอนต์ · ในหน้านี้มี {pageFonts.length} แบบ</p>
            <SourceFontList fonts={pageFonts} />
          </section>
        )}
        <button type="button" onClick={onShowDocumentFonts}
          className="w-full px-3 py-2 text-sm rounded border border-slate-300 hover:bg-slate-50">
          ฟอนต์ทั้งเอกสาร...
        </button>
      </div>
    </aside>
  );
}
