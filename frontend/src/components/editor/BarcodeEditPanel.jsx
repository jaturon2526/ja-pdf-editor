// แผง "ย้าย/ลบบาร์โค้ด" (v1.41.0): ตำแหน่ง (มม.) · ตกลงย้าย · ลบ · แทรกใหม่ (เปลี่ยนข้อมูล = ลบแล้วแทรกใหม่)
// เดสก์ท็อปอยู่ขวา มือถือเป็นแผ่นล่าง (เหมือนแผงแก้ไขตาราง)
import { mmToPt, ptToMm } from "../../utils/tableGeometry.js";
import { barcodeLabel } from "./BarcodeEditLayer.jsx";

function MmInput({ id, label, valuePt, onChangePt }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs text-slate-700" htmlFor={id}>
      <span>{label}</span>
      <input id={id} type="number" step="0.5" value={ptToMm(valuePt)}
        onChange={(e) => { const mm = Number.parseFloat(e.target.value); if (Number.isFinite(mm)) onChangePt(mmToPt(mm)); }}
        className="w-20 border border-slate-300 rounded px-2 py-1 text-base sm:text-xs text-right" />
    </label>
  );
}

export default function BarcodeEditPanel({ hook, onClose, onInsertNew }) {
  const { barcodes, rotated, selected, draft, moveTo, reset, changed, apply, remove, applying, error, lastAction } = hook;
  return (
    <aside aria-labelledby="barcode-edit-title" data-testid="barcode-edit-panel"
      className="bg-white border-slate-200 flex flex-col shrink-0
        desk:w-72 desk:border-l
        phone:fixed phone:inset-x-0 phone:bottom-0 phone:z-40 phone:max-h-[50dvh] phone:border-t phone:rounded-t-2xl phone:shadow-2xl">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200">
        <h3 id="barcode-edit-title" className="text-sm font-semibold text-slate-900">ย้าย / ลบบาร์โค้ด</h3>
        <button type="button" onClick={onClose} aria-label="ปิดเครื่องมือย้ายลบบาร์โค้ด" className="icon-btn">✕</button>
      </div>
      <div className="p-3 overflow-y-auto text-sm space-y-3">
        {barcodes === null && <p className="text-slate-500">กำลังหาบาร์โค้ดในหน้านี้...</p>}
        {barcodes?.length === 0 && (
          <p className="text-slate-600">
            {rotated ? "ยังย้าย/ลบบาร์โค้ดในหน้าที่หมุนไม่ได้ — หมุนหน้ากลับเป็นแนวเดิมก่อน"
              : "ไม่พบบาร์โค้ดหรือ QR Code ที่อ่านได้ในหน้านี้"}
          </p>
        )}
        {barcodes?.length > 0 && !selected && (
          <p className="text-slate-600">คลิกหรือแตะกรอบสีม่วงเพื่อเลือกบาร์โค้ด ({barcodes.length} รายการในหน้านี้)</p>
        )}
        {lastAction === "deleted" && <p className="text-xs text-green-700" role="status">ลบบาร์โค้ดแล้ว</p>}
        {selected && draft && (
          <>
            <p className="text-xs text-slate-600 break-all" data-testid="barcode-selected">{barcodeLabel(selected)}</p>
            <p className="text-xs text-slate-500">ลากบาร์โค้ดเพื่อย้าย (หรือปุ่มลูกศร) แล้วกดตกลง</p>
            <section className="space-y-1.5" aria-label="ตำแหน่ง">
              <h4 className="text-xs font-semibold text-slate-700">ตำแหน่ง (มม. จากมุมซ้ายบน)</h4>
              <MmInput id="bc-left" label="ซ้าย" valuePt={draft.x0} onChangePt={(v) => moveTo(v, draft.y0)} />
              <MmInput id="bc-top" label="บน" valuePt={draft.y0} onChangePt={(v) => moveTo(draft.x0, v)} />
            </section>
            {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
            {lastAction === "moved" && !changed && <p className="text-xs text-green-700" role="status">ย้ายบาร์โค้ดแล้ว</p>}
            <div className="flex gap-2">
              <button type="button" onClick={reset} disabled={!changed || applying}
                className="flex-1 px-3 py-2 text-sm rounded border border-slate-300 text-slate-700 disabled:opacity-50">รีเซ็ต</button>
              <button type="button" onClick={() => void apply()} disabled={!changed || applying}
                className="flex-1 px-3 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
                {applying ? "กำลังย้าย..." : "ตกลง"}
              </button>
            </div>
            <button type="button" onClick={() => void remove()} disabled={applying}
              className="w-full px-3 py-2 text-sm rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50">
              ลบบาร์โค้ดนี้
            </button>
          </>
        )}
        {barcodes !== null && (
          <div className="pt-2 border-t border-slate-100 space-y-1.5">
            <p className="text-[11px] text-slate-500">ต้องการเปลี่ยนข้อมูลในบาร์โค้ด: ลบอันเดิมแล้วแทรกใหม่</p>
            <button type="button" onClick={onInsertNew}
              className="w-full px-3 py-1.5 text-xs rounded border border-slate-300 hover:bg-slate-50">แทรกบาร์โค้ด / QR ใหม่...</button>
          </div>
        )}
      </div>
    </aside>
  );
}
