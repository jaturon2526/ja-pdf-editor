// แผง "แก้ไขตาราง" (v1.40.0, ย่อ/ขยายแผงบนมือถือ + สวิตช์ขยายตารางตาม v1.41.4)
// เดสก์ท็อปอยู่ขวา มือถือเป็นแผ่นล่าง (เหมือนแผงตรวจฟอนต์)
import { useState } from "react";
import { equalize, mmToPt, ptToMm, setSize, sizes, translate } from "../../utils/tableGeometry.js";
import { resolveFamilyAndStyle } from "../../utils/textEditUtils.js";

const CELL_STYLE_OPTIONS = [
  { key: "regular", label: "R", title: "ตัวปกติ (Regular)" },
  { key: "bold", label: "B", title: "ตัวหนา (Bold)" },
  { key: "italic", label: "I", title: "ตัวเอียง (Italic)" },
  { key: "bold_italic", label: "BI", title: "ตัวหนาเอียง (Bold Italic)" },
];

const CELL_PRESET_COLORS = [
  { key: "black", label: "ดำ", value: "#000000" },
  { key: "blue", label: "น้ำเงิน", value: "#1a56db" },
  { key: "red", label: "แดง", value: "#d32f2f" },
];

const CELL_ALIGN_OPTIONS = [
  { k: "", label: "อัตโนมัติ" },
  { k: "left", label: "ซ้าย" },
  { k: "center", label: "กลาง" },
  { k: "right", label: "ขวา" },
];

const CELL_VALIGN_OPTIONS = [
  { k: "top", label: "บน" },
  { k: "middle", label: "กลาง" },
  { k: "bottom", label: "ล่าง" },
];

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

export default function TableEditPanel({
  hook,
  fontFamilies = [],
  onClose,
  canUndo = false,
  canRedo = false,
  onUndo,
  onRedo,
}) {
  const {
    tables, selected, draft, update, reset, changed, apply, applying, error,
    overlapWarning, lastResult, expandMode, setExpandMode,
    fitTableToPage, createNewTable,
    cellText, setCellText,
    cellFontKey, setCellFontKey,
    cellFontSize, setCellFontSize,
    cellColorHex, setCellColorHex,
    cellTextAlign, setCellTextAlign,
    cellTextValign, setCellTextValign,
    cellUnderline, setCellUnderline,
    cellTextDirty, saveCellText,
    cellSelection, multiSelectMode, setMultiSelectMode, runStructure, confirmOverlap,
  } = hook;
  const families = fontFamilies || [];
  const { familyKey: cellFamilyKey, style: cellCurrentStyle } = resolveFamilyAndStyle(cellFontKey, families);
  const currentCellFamily = families.find((f) => f.key === cellFamilyKey) || families[0] || null;

  function handleCellFamilyChange(newFamilyKey) {
    const fam = families.find((f) => f.key === newFamilyKey);
    if (!fam) return;
    const nextStyle = fam.styles[cellCurrentStyle] ? cellCurrentStyle : "regular";
    setCellFontKey?.(fam.styles[nextStyle] || fam.styles.regular);
  }

  function handleCellStyleChange(newStyle) {
    if (!currentCellFamily || !currentCellFamily.styles[newStyle]) return;
    setCellFontKey?.(currentCellFamily.styles[newStyle]);
  }
  const [collapsed, setCollapsed] = useState(false); // มือถือ: ย่อแผ่นล่างให้เห็นตารางเต็มจอตอนใช้นิ้วลากจุดจับ
  const [newRows, setNewRows] = useState(3);
  const [newCols, setNewCols] = useState(4);

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
  const structDisabled = applying || !cellSelection;
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
          {onUndo && (
            <button
              type="button"
              onClick={() => void onUndo()}
              disabled={!canUndo || applying}
              title="เลิกทำ (Ctrl+Z)"
              className="px-2 py-1 text-xs rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              ↶ เลิกทำ
            </button>
          )}
          {onRedo && canRedo && (
            <button
              type="button"
              onClick={() => void onRedo()}
              disabled={applying}
              title="ทำซ้ำ (Ctrl+Y)"
              className="px-2 py-1 text-xs rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              ↷
            </button>
          )}
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
          <button
            type="button"
            onClick={() => {
              if (changed || cellTextDirty) reset();
              else void onUndo?.();
            }}
            disabled={(!changed && !cellTextDirty && !canUndo) || applying}
            className="px-2.5 py-1.5 text-xs rounded border border-slate-300 text-slate-700 disabled:opacity-50"
          >
            รีเซ็ต
          </button>
          <button type="button" onClick={() => void apply({ onDone: onClose })} disabled={applying}
            className="px-3 py-1.5 text-xs font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
            {applying ? "กำลังวาด..." : "ตกลง"}
          </button>
        </div>
      )}
      <div className={`p-3 overflow-y-auto text-sm space-y-3 ${collapsed ? "phone:hidden" : ""}`}>
        {tables === null && <p className="text-slate-500">กำลังหาตารางในหน้านี้...</p>}
        {tables?.length === 0 && (
          <p className="text-slate-600">ไม่พบตารางที่มีเส้นในหน้านี้ — สร้างตารางใหม่ด้านล่างได้เลย</p>
        )}
        {tables?.length > 0 && !selected && (
          <p className="text-slate-600">คลิกหรือแตะกรอบประสีฟ้าเพื่อเลือกตาราง ({tables.length} ตารางในหน้านี้)</p>
        )}

        {/* แทรกตารางใหม่ (v1.49.0): กำหนดจำนวนแถวและคอลัมน์เริ่มต้นได้ */}
        <details className="group rounded-lg border border-slate-200 bg-slate-50/80 p-2.5" open={!selected}>
          <summary className="text-xs font-semibold text-slate-800 cursor-pointer select-none">
            + แทรกตารางใหม่
          </summary>
          <div className="mt-2 space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <label htmlFor="new-table-rows" className="block text-[11px] font-medium text-slate-700">
                <span>จำนวนแถว</span>
                <input
                  id="new-table-rows"
                  type="number"
                  min="1"
                  max="50"
                  value={newRows}
                  onChange={(e) => setNewRows(Number.parseInt(e.target.value, 10) || 1)}
                  className="mt-0.5 w-full border border-slate-300 rounded bg-white px-2 py-1 text-xs"
                />
              </label>
              <label htmlFor="new-table-cols" className="block text-[11px] font-medium text-slate-700">
                <span>จำนวนคอลัมน์</span>
                <input
                  id="new-table-cols"
                  type="number"
                  min="1"
                  max="30"
                  value={newCols}
                  onChange={(e) => setNewCols(Number.parseInt(e.target.value, 10) || 1)}
                  className="mt-0.5 w-full border border-slate-300 rounded bg-white px-2 py-1 text-xs"
                />
              </label>
            </div>
            <button
              type="button"
              disabled={applying}
              onClick={() => void createNewTable?.({ rows: newRows, cols: newCols })}
              className="w-full px-3 py-1.5 text-xs font-medium rounded bg-sky-600 hover:bg-sky-700 text-white disabled:opacity-50"
            >
              {applying ? "กำลังสร้าง..." : "สร้างตาราง"}
            </button>
          </div>
        </details>

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

              {/* พิมพ์ข้อความในเซลล์ที่เลือก (v1.49.0) */}
              {cellSelection && (
                <div className="space-y-1.5 pt-1 pb-1.5 border-y border-slate-200/80">
                  <label htmlFor="tbl-cell-text" className="block text-[11px] font-medium text-slate-700">
                    ข้อความในเซลล์ที่เลือก (กด Enter เพื่อบันทึก · Tab ไปช่องถัดไป)
                  </label>
                  <div className="flex gap-1">
                    <input
                      id="tbl-cell-text"
                      type="text"
                      value={cellText || ""}
                      disabled={applying}
                      placeholder="พิมพ์ข้อความในเซลล์..."
                      onChange={(e) => setCellText?.(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void saveCellText?.(cellText, { moveRow: 1 });
                        } else if (e.key === "Tab") {
                          e.preventDefault();
                          void saveCellText?.(cellText, { moveCol: e.shiftKey ? -1 : 1 });
                        }
                      }}
                      className="flex-1 min-w-0 border border-slate-300 rounded bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <button
                      type="button"
                      disabled={!cellTextDirty || applying}
                      onClick={() => void saveCellText?.()}
                      className="px-2.5 py-1 text-[11px] font-medium rounded bg-sky-600 hover:bg-sky-700 text-white disabled:opacity-45 shrink-0"
                    >
                      ใส่ข้อความ
                    </button>
                  </div>
                  {/* ฟอนต์และรูปแบบฟอนต์ของเซลล์ (เหมือนโหมดแก้ไขข้อความ — v1.50.0) */}
                  {families.length > 0 && (
                    <div className="space-y-1.5 pt-1">
                      <div>
                        <label htmlFor="tbl-cell-font" className="block text-[10px] font-medium text-slate-600 mb-0.5">
                          ฟอนต์
                        </label>
                        <select
                          id="tbl-cell-font"
                          value={cellFamilyKey || ""}
                          disabled={applying}
                          onChange={(e) => handleCellFamilyChange(e.target.value)}
                          className="w-full border border-slate-300 rounded bg-white px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          {families.map((f) => (
                            <option key={f.key} value={f.key}>
                              {f.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="flex items-center gap-1" role="group" aria-label="รูปแบบฟอนต์ในเซลล์">
                        {CELL_STYLE_OPTIONS.map((opt) => {
                          const available = !!currentCellFamily?.styles[opt.key];
                          const active = cellCurrentStyle === opt.key;
                          let fontCls = "";
                          if (opt.key === "bold") fontCls = "font-bold";
                          else if (opt.key === "italic") fontCls = "italic";
                          else if (opt.key === "bold_italic") fontCls = "font-bold italic";
                          return (
                            <button
                              key={opt.key}
                              type="button"
                              title={available ? opt.title : `${opt.title} — ฟอนต์นี้ไม่มีไฟล์สไตล์นี้`}
                              aria-label={opt.title}
                              aria-pressed={active}
                              disabled={!available || applying}
                              onClick={() => handleCellStyleChange(opt.key)}
                              className={`flex-1 py-1 text-[11px] rounded border transition-colors disabled:opacity-35 ${fontCls} ${
                                active
                                  ? "border-sky-600 bg-sky-600 text-white"
                                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                              }`}
                            >
                              {opt.label}
                            </button>
                          );
                        })}
                        <button
                          type="button"
                          title="ขีดเส้นใต้ (ใช้ได้กับทุกฟอนต์)"
                          aria-label="ขีดเส้นใต้"
                          aria-pressed={!!cellUnderline}
                          disabled={applying}
                          onClick={() => setCellUnderline?.(!cellUnderline)}
                          className={`flex-1 py-1 text-[11px] underline rounded border transition-colors disabled:opacity-35 ${
                            cellUnderline
                              ? "border-sky-600 bg-sky-600 text-white"
                              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                          }`}
                        >
                          U
                        </button>
                      </div>
                    </div>
                  )}

                  <div className="flex items-end gap-2 pt-0.5">
                    <div className="w-20">
                      <label htmlFor="tbl-cell-fontsize" className="block text-[10px] font-medium text-slate-600 mb-0.5">
                        ขนาด (pt)
                      </label>
                      <input
                        id="tbl-cell-fontsize"
                        type="number"
                        min={6}
                        max={96}
                        step={0.5}
                        disabled={applying}
                        value={cellFontSize ?? 11}
                        onChange={(e) => {
                          const v = Number.parseFloat(e.target.value);
                          if (Number.isFinite(v)) setCellFontSize?.(v);
                        }}
                        className="w-full border border-slate-300 rounded bg-white px-2 py-1 text-xs"
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <span id="tbl-cell-color-label" className="block text-[10px] font-medium text-slate-600 mb-0.5">
                        สีตัวอักษร
                      </span>
                      <div className="flex items-center gap-1.5" role="group" aria-labelledby="tbl-cell-color-label">
                        {CELL_PRESET_COLORS.map((preset) => (
                          <button
                            key={preset.key}
                            type="button"
                            title={preset.label}
                            aria-label={`สี${preset.label}`}
                            disabled={applying}
                            onClick={() => setCellColorHex?.(preset.value)}
                            className={`w-6 h-6 rounded-full border transition-all ${
                              (cellColorHex || "#000000").toLowerCase() === preset.value
                                ? "border-sky-500 scale-110 ring-2 ring-sky-200"
                                : "border-slate-300 hover:scale-105"
                            }`}
                            style={{ backgroundColor: preset.value }}
                          />
                        ))}
                        <div
                          className="relative w-6 h-6 rounded-full overflow-hidden border border-slate-300 hover:border-slate-400"
                          title="สีอื่นๆ"
                        >
                          <input
                            type="color"
                            aria-label="เลือกสีตัวอักษรในเซลล์"
                            disabled={applying}
                            value={cellColorHex || "#000000"}
                            onChange={(e) => setCellColorHex?.(e.target.value)}
                            className="absolute -top-2 -left-2 w-10 h-10 cursor-pointer border-0 p-0"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-slate-500 mr-1">แนวนอน:</span>
                    {CELL_ALIGN_OPTIONS.map((opt) => (
                      <button
                        key={opt.k || "auto"}
                        type="button"
                        disabled={applying}
                        onClick={() => setCellTextAlign?.(opt.k)}
                        className={`px-1.5 py-0.5 text-[10px] rounded border ${
                          (cellTextAlign || "") === opt.k
                            ? "border-sky-500 bg-sky-50 text-sky-700 font-medium"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-slate-500 mr-1">แนวตั้ง:</span>
                    {CELL_VALIGN_OPTIONS.map((opt) => (
                      <button
                        key={opt.k}
                        type="button"
                        disabled={applying}
                        onClick={() => setCellTextValign?.(opt.k)}
                        className={`px-1.5 py-0.5 text-[10px] rounded border ${
                          (cellTextValign || "middle") === opt.k
                            ? "border-sky-500 bg-sky-50 text-sky-700 font-medium"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
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

            {overlapWarning && (
              <div className="p-2 rounded bg-amber-50 border border-amber-300 text-amber-900 text-xs space-y-2" role="alert">
                <p>{overlapWarning}</p>
                <button type="button" onClick={() => void confirmOverlap()} disabled={applying}
                  className="px-3 py-1.5 rounded bg-amber-600 text-white disabled:opacity-50">วางทับต่อ</button>
              </div>
            )}

            <section className="space-y-1.5" aria-label="ตำแหน่ง">
              <h4 className="text-xs font-semibold text-slate-700">ตำแหน่ง (มม. จากมุมซ้ายบน)</h4>
              <MmInput id="tbl-left" label="ซ้าย" valuePt={draft.xs[0]} onChangePt={(v) => update((d) => ({ ...d, xs: translate(d.xs, v - d.xs[0]) }))} />
              <MmInput id="tbl-top" label="บน" valuePt={draft.ys[0]} onChangePt={(v) => update((d) => ({ ...d, ys: translate(d.ys, v - d.ys[0]) }))} />
              <div className="pt-1 space-y-1">
                <span className="block text-[11px] font-medium text-slate-600">ขยายเต็มพื้นที่หน้ากระดาษ</span>
                <div className="grid grid-cols-3 gap-1">
                  <button
                    type="button"
                    disabled={applying}
                    onClick={() => fitTableToPage?.("width")}
                    className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
                    title="ขยายความกว้างตารางให้เต็มพื้นที่ซ้าย–ขวาของหน้า"
                  >
                    ↔ เต็มซ้าย–ขวา
                  </button>
                  <button
                    type="button"
                    disabled={applying}
                    onClick={() => fitTableToPage?.("height")}
                    className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
                    title="ขยายความสูงตารางให้เต็มพื้นที่บน–ล่างของหน้า"
                  >
                    ↕ เต็มบน–ล่าง
                  </button>
                  <button
                    type="button"
                    disabled={applying}
                    onClick={() => fitTableToPage?.("full")}
                    className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
                    title="ขยายตารางให้เต็มทั้งซ้าย–ขวาและบน–ล่างของหน้า"
                  >
                    ⛶ เต็มหน้า
                  </button>
                </div>
              </div>
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
            {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
            {lastResult && !changed && (
              <p className="text-xs text-green-700" role="status">
                แก้ตารางแล้ว{lastResult.wrapped_cells?.length ? ` · ตัดบรรทัดใหม่ ${lastResult.wrapped_cells.length} ช่อง` : ""}
                {lastResult.adjusted_rows?.length ? ` · แถว ${lastResult.adjusted_rows.map((r) => r + 1).join(", ")} สูงขึ้น` : ""}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  if (changed || cellTextDirty) reset();
                  else void onUndo?.();
                }}
                disabled={(!changed && !cellTextDirty && !canUndo) || applying}
                className="flex-1 px-3 py-2 text-sm rounded border border-slate-300 text-slate-700 disabled:opacity-50"
              >
                รีเซ็ต
              </button>
              <button type="button" onClick={() => void apply({ onDone: onClose })} disabled={applying}
                className="flex-1 px-3 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
                {applying ? "กำลังวาดตาราง..." : "ตกลง"}
              </button>
            </div>
          </>
        )}
        {!selected && error && <p className="text-xs text-red-600" role="alert">{error}</p>}
      </div>
    </aside>
  );
}
