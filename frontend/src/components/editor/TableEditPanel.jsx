// แผง "แก้ไขตาราง" (v1.40.0, ย่อ/ขยายแผงบนมือถือ + สวิตช์ขยายตารางตาม v1.41.4)
// เดสก์ท็อปอยู่ขวา มือถือเป็นแผ่นล่าง (เหมือนแผงตรวจฟอนต์)
import { useState } from "react";
import { equalize, mmToPt, ptToMm, setSize, sizes, translate } from "../../utils/tableGeometry.js";

function MmInput({ id, label, valuePt, onChangePt }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs text-slate-700" htmlFor={id}>
      <span className="truncate">{label}</span>
      <input id={id} type="number" step="0.5" min="2" value={ptToMm(valuePt)}
        onChange={(e) => { const mm = Number.parseFloat(e.target.value); if (Number.isFinite(mm)) onChangePt(mmToPt(mm)); }}
        className="w-20 border border-slate-300 rounded px-2 py-1 text-base sm:text-xs text-right" />
    </label>
  );
}

export default function TableEditPanel({ hook, onClose }) {
  const { tables, selected, draft, update, reset, changed, apply, applying, error, overlapWarning, lastResult, expandMode, setExpandMode } = hook;
  const [collapsed, setCollapsed] = useState(false); // มือถือ: ย่อแผ่นล่างให้เห็นตารางเต็มจอตอนใช้นิ้วลากจุดจับ
  return (
    <aside aria-labelledby="table-edit-title" data-testid="table-edit-panel"
      className="bg-white border-slate-200 flex flex-col shrink-0
        desk:w-72 desk:border-l
        phone:fixed phone:inset-x-0 phone:bottom-0 phone:z-40 phone:max-h-[50dvh] phone:border-t phone:rounded-t-2xl phone:shadow-2xl">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-slate-200">
        <h3 id="table-edit-title" className="text-sm font-semibold text-slate-900">แก้ไขตาราง</h3>
        <div className="flex items-center gap-1">
          {selected && (
            <button type="button" onClick={() => setCollapsed((v) => !v)}
              className="desk:hidden px-2 py-1 text-xs rounded border border-slate-300 text-slate-700 hover:bg-slate-50">
              {collapsed ? "ขยายแผง" : "ย่อแผง"}
            </button>
          )}
          <button type="button" onClick={onClose} aria-label="ปิดเครื่องมือแก้ไขตาราง" className="icon-btn">✕</button>
        </div>
      </div>
      {collapsed && selected && (
        <div className="desk:hidden px-3 py-2 flex items-center gap-2">
          <span className="text-xs text-slate-500 flex-1 truncate">ลากปุ่มสีฟ้าขอบบน/ซ้ายของตาราง</span>
          <button type="button" onClick={reset} disabled={!changed || applying}
            className="px-2.5 py-1.5 text-xs rounded border border-slate-300 text-slate-700 disabled:opacity-50">รีเซ็ต</button>
          <button type="button" onClick={() => void apply()} disabled={!changed || applying}
            className="px-3 py-1.5 text-xs font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
            {applying ? "กำลังวาด..." : "ตกลง"}
          </button>
        </div>
      )}
      <div className={`p-3 overflow-y-auto text-sm space-y-3 ${collapsed ? "phone:hidden" : ""}`}>
        {tables === null && <p className="text-slate-500">กำลังหาตารางในหน้านี้...</p>}
        {tables?.length === 0 && (
          <p className="text-slate-600">ไม่พบตารางที่มีเส้นในหน้านี้ — รองรับตารางที่มีเส้นตาราง (ไม่ใช่ภาพสแกน)</p>
        )}
        {tables?.length > 0 && !selected && (
          <p className="text-slate-600">คลิกหรือแตะกรอบประสีฟ้าเพื่อเลือกตาราง ({tables.length} ตารางในหน้านี้)</p>
        )}
        {selected && draft && (
          <>
            <p className="text-xs text-slate-500">
              {draft.ys.length - 1} แถว × {draft.xs.length - 1} คอลัมน์ · ลากตารางเพื่อย้าย (หรือปุ่มลูกศร) · ลากเส้นแบ่งหรือปุ่มสีฟ้าขอบบน/ซ้ายเพื่อปรับขนาดคอลัมน์และแถว · ลากขอบขวา/ล่างเพื่อย่อขยายทั้งตาราง
            </p>
            <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
              <input type="checkbox" checked={!!expandMode} onChange={(e) => setExpandMode?.(e.target.checked)} className="rounded border-slate-300" />
              <span>ลากเส้นแบ่งแล้วเลื่อนช่องถัดไปตาม (ขยายตาราง)</span>
            </label>
            <section className="space-y-1.5" aria-label="ตำแหน่ง">
              <h4 className="text-xs font-semibold text-slate-700">ตำแหน่ง (มม. จากมุมซ้ายบน)</h4>
              <MmInput id="tbl-left" label="ซ้าย" valuePt={draft.xs[0]} onChangePt={(v) => update((d) => ({ ...d, xs: translate(d.xs, v - d.xs[0]) }))} />
              <MmInput id="tbl-top" label="บน" valuePt={draft.ys[0]} onChangePt={(v) => update((d) => ({ ...d, ys: translate(d.ys, v - d.ys[0]) }))} />
            </section>
            <details className="group" open={draft.xs.length <= 8}>
              <summary className="text-xs font-semibold text-slate-700 cursor-pointer">ความกว้างคอลัมน์ (มม.)</summary>
              <div className="mt-1.5 space-y-1.5">
                {sizes(draft.xs).map((w, i) => (
                  <MmInput key={i} id={`tbl-col-${i}`} label={`คอลัมน์ ${i + 1}`} valuePt={w}
                    onChangePt={(v) => update((d) => ({ ...d, xs: setSize(d.xs, i, v) }))} />
                ))}
                <button type="button" onClick={() => update((d) => ({ ...d, xs: equalize(d.xs) }))}
                  className="w-full px-2 py-1.5 text-xs rounded border border-slate-300 hover:bg-slate-50">คอลัมน์กว้างเท่ากัน</button>
              </div>
            </details>
            <details className="group" open={draft.ys.length <= 8}>
              <summary className="text-xs font-semibold text-slate-700 cursor-pointer">ความสูงแถว (มม.)</summary>
              <div className="mt-1.5 space-y-1.5">
                {sizes(draft.ys).map((hgt, i) => (
                  <MmInput key={i} id={`tbl-row-${i}`} label={`แถว ${i + 1}`} valuePt={hgt}
                    onChangePt={(v) => update((d) => ({ ...d, ys: setSize(d.ys, i, v) }))} />
                ))}
                <button type="button" onClick={() => update((d) => ({ ...d, ys: equalize(d.ys) }))}
                  className="w-full px-2 py-1.5 text-xs rounded border border-slate-300 hover:bg-slate-50">แถวสูงเท่ากัน</button>
              </div>
            </details>
            <p className="text-[11px] text-slate-500">ช่องที่แคบลงจนข้อความไม่พอ จะตัดบรรทัดใหม่และแถวสูงขึ้นอัตโนมัติ (ข้อความในช่องนั้นอาจเปลี่ยนเป็นฟอนต์ระบบที่ใกล้เคียง)</p>
            {overlapWarning && (
              <div className="p-2 rounded bg-amber-50 border border-amber-300 text-amber-900 text-xs space-y-2" role="alert">
                <p>{overlapWarning}</p>
                <button type="button" onClick={() => void apply({ allowOverlap: true })} disabled={applying}
                  className="px-3 py-1.5 rounded bg-amber-600 text-white disabled:opacity-50">วางทับต่อ</button>
              </div>
            )}
            {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
            {lastResult && !changed && (
              <p className="text-xs text-green-700" role="status">
                แก้ตารางแล้ว{lastResult.wrapped_cells?.length ? ` · ตัดบรรทัดใหม่ ${lastResult.wrapped_cells.length} ช่อง` : ""}
                {lastResult.adjusted_rows?.length ? ` · แถว ${lastResult.adjusted_rows.map((r) => r + 1).join(", ")} สูงขึ้น` : ""}
              </p>
            )}
            <div className="flex gap-2">
              <button type="button" onClick={reset} disabled={!changed || applying}
                className="flex-1 px-3 py-2 text-sm rounded border border-slate-300 text-slate-700 disabled:opacity-50">รีเซ็ต</button>
              <button type="button" onClick={() => void apply()} disabled={!changed || applying}
                className="flex-1 px-3 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
                {applying ? "กำลังวาดตาราง..." : "ตกลง"}
              </button>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
