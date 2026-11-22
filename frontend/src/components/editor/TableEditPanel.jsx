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
  const {
    tables, selected, draft, update, reset, changed, apply, applying, error,
    overlapWarning, lastResult, expandMode, setExpandMode,
    cellSelection, multiSelectMode, setMultiSelectMode, runStructure, confirmOverlap,
  } = hook;
  const [collapsed, setCollapsed] = useState(false); // มือถือ: ย่อแผ่นล่างให้เห็นตารางเต็มจอตอนใช้นิ้วลากจุดจับ

  const activeCell = selected && cellSelection
    ? selected.cells.find((c) => (
      cellSelection.r0 >= c.r && cellSelection.r0 < c.r + c.rowspan
      && cellSelection.c0 >= c.c && cellSelection.c0 < c.c + c.colspan
    ))
    : null;
  const selRows = cellSelection ? cellSelection.r1 - cellSelection.r0 + 1 : 0;
  const selCols = cellSelection ? cellSelection.c1 - cellSelection.c0 + 1 : 0;
  const isMergedActive = !!(activeCell && (activeCell.rowspan > 1 || activeCell.colspan > 1));
  const coveredCellsCount = selected && cellSelection
    ? selected.cells.filter((c) => {
      const cr1 = c.r + c.rowspan - 1;
      const cc1 = c.c + c.colspan - 1;
      return cr1 >= cellSelection.r0 && c.r <= cellSelection.r1
        && cc1 >= cellSelection.c0 && c.c <= cellSelection.c1;
    }).length
    : 0;
  const canMerge = coveredCellsCount >= 2;
  const structDisabled = applying || changed || !cellSelection;
  const rowCount = draft ? draft.ys.length - 1 : 0;
  const colCount = draft ? draft.xs.length - 1 : 0;
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

            {/* โครงสร้างตาราง (v1.46.0): เพิ่ม/ลบแถว · เพิ่ม/ลบคอลัมน์ · รวม/แยกเซลล์ */}
            <section className="space-y-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200" aria-label="โครงสร้างตาราง">
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-xs font-semibold text-slate-800">แถว · คอลัมน์ · เซลล์</h4>
                {cellSelection && (
                  <span className="text-[11px] font-medium text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                    {selRows > 1 || selCols > 1
                      ? `เลือก ${selRows}×${selCols} ช่อง`
                      : `แถว ${cellSelection.r0 + 1} · คอลัมน์ ${cellSelection.c0 + 1}`}
                  </span>
                )}
              </div>
              <label className="flex items-center gap-2 text-[11px] text-slate-600 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={!!multiSelectMode}
                  onChange={(e) => setMultiSelectMode?.(e.target.checked)}
                  className="rounded border-slate-300"
                />
                <span>เลือกหลายเซลล์เพื่อรวม (หรือ Shift+คลิก)</span>
              </label>
              {changed && (
                <p className="text-[11px] text-amber-700">กด &quot;ตกลง&quot; หรือ &quot;รีเซ็ต&quot; ขนาดก่อนปรับแถว/คอลัมน์</p>
              )}
              <div className="grid grid-cols-3 gap-1">
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_row", { position: "above" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  + แถวบน
                </button>
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_row", { position: "below" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  + แถวล่าง
                </button>
                <button type="button" disabled={structDisabled || rowCount <= 1}
                  onClick={() => void runStructure("delete_row")}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-red-200 bg-white text-red-700 hover:bg-red-50 disabled:opacity-45">
                  ลบแถว
                </button>
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_col", { position: "left" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  + ซ้าย
                </button>
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_col", { position: "right" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  + ขวา
                </button>
                <button type="button" disabled={structDisabled || colCount <= 1}
                  onClick={() => void runStructure("delete_col")}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-red-200 bg-white text-red-700 hover:bg-red-50 disabled:opacity-45">
                  ลบคอลัมน์
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                <button type="button" disabled={structDisabled || !canMerge}
                  onClick={() => void runStructure("merge_cells")}
                  className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-45">
                  รวมเซลล์
                </button>
                {isMergedActive ? (
                  <button type="button" disabled={structDisabled}
                    onClick={() => void runStructure("split_cell")}
                    className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                    แยกเซลล์
                  </button>
                ) : (
                  <>
                    <button type="button" disabled={structDisabled || canMerge}
                      onClick={() => void runStructure("split_cell", { direction: "cols" })}
                      className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                      แยก 2 คอลัมน์
                    </button>
                    <button type="button" disabled={structDisabled || canMerge}
                      onClick={() => void runStructure("split_cell", { direction: "rows" })}
                      className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                      แยก 2 แถว
                    </button>
                  </>
                )}
              </div>
            </section>
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
                <button type="button" onClick={() => void confirmOverlap()} disabled={applying}
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
