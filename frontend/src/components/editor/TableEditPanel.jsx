// แผง "แก้ไขตาราง" (v1.40.0, ย่อ/ขยายแผงบนมือถือ + สวิตช์ขยายตารางตาม v1.41.4)
// เดสก์ท็อปอยู่ขวา มือถือเป็นแผ่นล่าง (เหมือนแผงตรวจฟอนต์)
import { useState } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";
import { equalize, mmToPt, ptToMm, setSize, sizes, translate } from "../../utils/tableGeometry.js";
import { resolveFamilyAndStyle } from "../../utils/textEditUtils.js";

const CELL_STYLE_OPTIONS = [
  { key: "regular", label: "R", titleKey: "editor.panels.table.styleRegular" },
  { key: "bold", label: "B", titleKey: "editor.panels.table.styleBold" },
  { key: "italic", label: "I", titleKey: "editor.panels.table.styleItalic" },
  { key: "bold_italic", label: "BI", titleKey: "editor.panels.table.styleBoldItalic" },
];

const CELL_PRESET_COLORS = [
  { key: "black", labelKey: "editor.panels.table.colorBlack", value: "#000000" },
  { key: "blue", labelKey: "editor.panels.table.colorBlue", value: "#1a56db" },
  { key: "red", labelKey: "editor.panels.table.colorRed", value: "#d32f2f" },
];

const CELL_ALIGN_OPTIONS = [
  { k: "", labelKey: "editor.panels.table.alignAuto" },
  { k: "left", labelKey: "editor.panels.table.alignLeft" },
  { k: "center", labelKey: "editor.panels.table.alignCenter" },
  { k: "right", labelKey: "editor.panels.table.alignRight" },
];

const CELL_VALIGN_OPTIONS = [
  { k: "top", labelKey: "editor.panels.table.valignTop" },
  { k: "middle", labelKey: "editor.panels.table.valignMiddle" },
  { k: "bottom", labelKey: "editor.panels.table.valignBottom" },
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
  const { t } = useI18n();
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
        <h3 id="table-edit-title" className="text-sm font-semibold text-slate-900">{t("editor.panels.table.title")}</h3>
        <div className="flex items-center gap-1">
          {onUndo && (
            <button
              type="button"
              onClick={() => void onUndo()}
              disabled={!canUndo || applying}
              title={t("editor.panels.table.undoTitle")}
              className="px-2 py-1 text-xs rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              {t("editor.panels.table.undoBtn")}
            </button>
          )}
          {onRedo && canRedo && (
            <button
              type="button"
              onClick={() => void onRedo()}
              disabled={applying}
              title={t("editor.panels.table.redoTitle")}
              className="px-2 py-1 text-xs rounded border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              ↷
            </button>
          )}
          {selected && (
            <button type="button" onClick={() => setCollapsed((v) => !v)}
              className="desk:hidden px-2 py-1 text-xs rounded border border-slate-300 text-slate-700 hover:bg-slate-50">
              {collapsed ? t("editor.panels.table.expandPanel") : t("editor.panels.table.collapsePanel")}
            </button>
          )}
          <button type="button" onClick={onClose} aria-label={t("editor.panels.table.closeAria")} className="icon-btn">✕</button>
        </div>
      </div>
      {collapsed && selected && (
        <div className="desk:hidden px-3 py-2 flex items-center gap-2">
          <span className="text-xs text-slate-500 flex-1 truncate">{t("editor.panels.table.collapsedHint")}</span>
          <button
            type="button"
            onClick={() => {
              if (changed || cellTextDirty) reset();
              else void onUndo?.();
            }}
            disabled={(!changed && !cellTextDirty && !canUndo) || applying}
            className="px-2.5 py-1.5 text-xs rounded border border-slate-300 text-slate-700 disabled:opacity-50"
          >
            {t("editor.panels.table.resetBtn")}
          </button>
          <button type="button" onClick={() => void apply({ onDone: onClose })} disabled={applying}
            className="px-3 py-1.5 text-xs font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
            {applying ? t("editor.panels.table.drawingShort") : t("editor.panels.table.applyBtn")}
          </button>
        </div>
      )}
      <div className={`p-3 overflow-y-auto text-sm space-y-3 ${collapsed ? "phone:hidden" : ""}`}>
        {tables === null && <p className="text-slate-500">{t("editor.panels.table.searchingTables")}</p>}
        {tables?.length === 0 && (
          <p className="text-slate-600">{t("editor.panels.table.noTablesFound")}</p>
        )}
        {tables?.length > 0 && !selected && (
          <p className="text-slate-600">{t("editor.panels.table.selectTableHint", { count: tables.length })}</p>
        )}

        {/* แทรกตารางใหม่ (v1.49.0): กำหนดจำนวนแถวและคอลัมน์เริ่มต้นได้ */}
        <details className="group rounded-lg border border-slate-200 bg-slate-50/80 p-2.5" open={!selected}>
          <summary className="text-xs font-semibold text-slate-800 cursor-pointer select-none">
            {t("editor.panels.table.insertNewTableSummary")}
          </summary>
          <div className="mt-2 space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <label htmlFor="new-table-rows" className="block text-[11px] font-medium text-slate-700">
                <span>{t("editor.panels.table.rowCountLabel")}</span>
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
                <span>{t("editor.panels.table.colCountLabel")}</span>
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
              {applying ? t("editor.panels.table.creatingTable") : t("editor.panels.table.createTableBtn")}
            </button>
          </div>
        </details>

        {selected && draft && (
          <>
            <p className="text-xs text-slate-500">
              {t("editor.panels.table.tableInstructions", { rows: draft.ys.length - 1, cols: draft.xs.length - 1 })}
            </p>
            <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
              <input type="checkbox" checked={!!expandMode} onChange={(e) => setExpandMode?.(e.target.checked)} className="rounded border-slate-300" />
              <span>{t("editor.panels.table.expandModeLabel")}</span>
            </label>

            {/* โครงสร้างตาราง (v1.46.0): เพิ่ม/ลบแถว · เพิ่ม/ลบคอลัมน์ · รวม/แยกเซลล์ */}
            <section className="space-y-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200" aria-label={t("editor.panels.table.structureAria")}>
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-xs font-semibold text-slate-800">{t("editor.panels.table.structureHeading")}</h4>
                {cellSelection && (
                  <span className="text-[11px] font-medium text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                    {selRows > 1 || selCols > 1
                      ? t("editor.panels.table.selectionMulti", { rows: selRows, cols: selCols })
                      : t("editor.panels.table.selectionSingle", { row: cellSelection.r0 + 1, col: cellSelection.c0 + 1 })}
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
                <span>{t("editor.panels.table.multiSelectLabel")}</span>
              </label>

              {/* พิมพ์ข้อความในเซลล์ที่เลือก (v1.49.0) */}
              {cellSelection && (
                <div className="space-y-1.5 pt-1 pb-1.5 border-y border-slate-200/80">
                  <label htmlFor="tbl-cell-text" className="block text-[11px] font-medium text-slate-700">
                    {t("editor.panels.table.cellTextLabel")}
                  </label>
                  <div className="flex gap-1">
                    <input
                      id="tbl-cell-text"
                      type="text"
                      value={cellText || ""}
                      disabled={applying}
                      placeholder={t("editor.panels.table.cellTextPlaceholder")}
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
                      {t("editor.panels.table.insertTextBtn")}
                    </button>
                  </div>
                  {/* ฟอนต์และรูปแบบฟอนต์ของเซลล์ (เหมือนโหมดแก้ไขข้อความ — v1.50.0) */}
                  {families.length > 0 && (
                    <div className="space-y-1.5 pt-1">
                      <div>
                        <label htmlFor="tbl-cell-font" className="block text-[10px] font-medium text-slate-600 mb-0.5">
                          {t("editor.panels.table.fontLabel")}
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

                      <div className="flex items-center gap-1" role="group" aria-label={t("editor.panels.table.cellFontStyleAria")}>
                        {CELL_STYLE_OPTIONS.map((opt) => {
                          const available = !!currentCellFamily?.styles[opt.key];
                          const active = cellCurrentStyle === opt.key;
                          const styleTitle = t(opt.titleKey);
                          let fontCls = "";
                          if (opt.key === "bold") fontCls = "font-bold";
                          else if (opt.key === "italic") fontCls = "italic";
                          else if (opt.key === "bold_italic") fontCls = "font-bold italic";
                          return (
                            <button
                              key={opt.key}
                              type="button"
                              title={available ? styleTitle : t("editor.panels.table.styleUnavailableTitle", { style: styleTitle })}
                              aria-label={styleTitle}
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
                          title={t("editor.panels.table.underlineTitle")}
                          aria-label={t("editor.panels.table.underlineAria")}
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
                        {t("editor.panels.table.fontSizeLabel")}
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
                        {t("editor.panels.table.textColorLabel")}
                      </span>
                      <div className="flex items-center gap-1.5" role="group" aria-labelledby="tbl-cell-color-label">
                        {CELL_PRESET_COLORS.map((preset) => {
                          const presetLabel = t(preset.labelKey);
                          return (
                            <button
                              key={preset.key}
                              type="button"
                              title={presetLabel}
                              aria-label={t("editor.panels.table.colorAriaLabel", { color: presetLabel })}
                              disabled={applying}
                              onClick={() => setCellColorHex?.(preset.value)}
                              className={`w-6 h-6 rounded-full border transition-all ${
                                (cellColorHex || "#000000").toLowerCase() === preset.value
                                  ? "border-sky-500 scale-110 ring-2 ring-sky-200"
                                  : "border-slate-300 hover:scale-105"
                              }`}
                              style={{ backgroundColor: preset.value }}
                            />
                          );
                        })}
                        <div
                          className="relative w-6 h-6 rounded-full overflow-hidden border border-slate-300 hover:border-slate-400"
                          title={t("editor.panels.table.otherColorsTitle")}
                        >
                          <input
                            type="color"
                            aria-label={t("editor.panels.table.pickCellColorAria")}
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
                    <span className="text-[10px] text-slate-500 mr-1">{t("editor.panels.table.horizontalAlignLabel")}</span>
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
                        {t(opt.labelKey)}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-slate-500 mr-1">{t("editor.panels.table.verticalAlignLabel")}</span>
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
                        {t(opt.labelKey)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-3 gap-1">
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_row", { position: "above" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  {t("editor.panels.table.insertRowAbove")}
                </button>
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_row", { position: "below" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  {t("editor.panels.table.insertRowBelow")}
                </button>
                <button type="button" disabled={structDisabled || rowCount <= 1}
                  onClick={() => void runStructure("delete_row")}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-red-200 bg-white text-red-700 hover:bg-red-50 disabled:opacity-45">
                  {t("editor.panels.table.deleteRow")}
                </button>
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_col", { position: "left" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  {t("editor.panels.table.insertColLeft")}
                </button>
                <button type="button" disabled={structDisabled}
                  onClick={() => void runStructure("insert_col", { position: "right" })}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                  {t("editor.panels.table.insertColRight")}
                </button>
                <button type="button" disabled={structDisabled || colCount <= 1}
                  onClick={() => void runStructure("delete_col")}
                  className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-red-200 bg-white text-red-700 hover:bg-red-50 disabled:opacity-45">
                  {t("editor.panels.table.deleteCol")}
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                <button type="button" disabled={structDisabled || !canMerge}
                  onClick={() => void runStructure("merge_cells")}
                  className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-45">
                  {t("editor.panels.table.mergeCells")}
                </button>
                {isMergedActive ? (
                  <button type="button" disabled={structDisabled}
                    onClick={() => void runStructure("split_cell")}
                    className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                    {t("editor.panels.table.splitCell")}
                  </button>
                ) : (
                  <>
                    <button type="button" disabled={structDisabled || canMerge}
                      onClick={() => void runStructure("split_cell", { direction: "cols" })}
                      className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                      {t("editor.panels.table.splitTwoCols")}
                    </button>
                    <button type="button" disabled={structDisabled || canMerge}
                      onClick={() => void runStructure("split_cell", { direction: "rows" })}
                      className="flex-1 px-2 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45">
                      {t("editor.panels.table.splitTwoRows")}
                    </button>
                  </>
                )}
              </div>
            </section>

            {overlapWarning && (
              <div className="p-2 rounded bg-amber-50 border border-amber-300 text-amber-900 text-xs space-y-2" role="alert">
                <p>{overlapWarning}</p>
                <button type="button" onClick={() => void confirmOverlap()} disabled={applying}
                  className="px-3 py-1.5 rounded bg-amber-600 text-white disabled:opacity-50">{t("editor.panels.table.confirmOverlapBtn")}</button>
              </div>
            )}

            <section className="space-y-1.5" aria-label={t("editor.panels.table.positionAria")}>
              <h4 className="text-xs font-semibold text-slate-700">{t("editor.panels.table.positionHeading")}</h4>
              <MmInput id="tbl-left" label={t("editor.panels.table.posLeft")} valuePt={draft.xs[0]} onChangePt={(v) => update((d) => ({ ...d, xs: translate(d.xs, v - d.xs[0]) }))} />
              <MmInput id="tbl-top" label={t("editor.panels.table.posTop")} valuePt={draft.ys[0]} onChangePt={(v) => update((d) => ({ ...d, ys: translate(d.ys, v - d.ys[0]) }))} />
              <div className="pt-1 space-y-1">
                <span className="block text-[11px] font-medium text-slate-600">{t("editor.panels.table.fitToPageHeading")}</span>
                <div className="grid grid-cols-3 gap-1">
                  <button
                    type="button"
                    disabled={applying}
                    onClick={() => fitTableToPage?.("width")}
                    className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
                    title={t("editor.panels.table.fitWidthTitle")}
                  >
                    {t("editor.panels.table.fitWidthBtn")}
                  </button>
                  <button
                    type="button"
                    disabled={applying}
                    onClick={() => fitTableToPage?.("height")}
                    className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
                    title={t("editor.panels.table.fitHeightTitle")}
                  >
                    {t("editor.panels.table.fitHeightBtn")}
                  </button>
                  <button
                    type="button"
                    disabled={applying}
                    onClick={() => fitTableToPage?.("full")}
                    className="px-1.5 py-1.5 text-[11px] font-medium rounded border border-slate-300 bg-white hover:bg-slate-100 disabled:opacity-45"
                    title={t("editor.panels.table.fitFullTitle")}
                  >
                    {t("editor.panels.table.fitFullBtn")}
                  </button>
                </div>
              </div>
            </section>
            <details className="group" open={draft.xs.length <= 8}>
              <summary className="text-xs font-semibold text-slate-700 cursor-pointer">{t("editor.panels.table.colWidthsSummary")}</summary>
              <div className="mt-1.5 space-y-1.5">
                {sizes(draft.xs).map((w, i) => (
                  <MmInput key={i} id={`tbl-col-${i}`} label={t("editor.panels.table.colIndexLabel", { index: i + 1 })} valuePt={w}
                    onChangePt={(v) => update((d) => ({ ...d, xs: setSize(d.xs, i, v) }))} />
                ))}
                <button type="button" onClick={() => update((d) => ({ ...d, xs: equalize(d.xs) }))}
                  className="w-full px-2 py-1.5 text-xs rounded border border-slate-300 hover:bg-slate-50">{t("editor.panels.table.equalizeColsBtn")}</button>
              </div>
            </details>
            <details className="group" open={draft.ys.length <= 8}>
              <summary className="text-xs font-semibold text-slate-700 cursor-pointer">{t("editor.panels.table.rowHeightsSummary")}</summary>
              <div className="mt-1.5 space-y-1.5">
                {sizes(draft.ys).map((hgt, i) => (
                  <MmInput key={i} id={`tbl-row-${i}`} label={t("editor.panels.table.rowIndexLabel", { index: i + 1 })} valuePt={hgt}
                    onChangePt={(v) => update((d) => ({ ...d, ys: setSize(d.ys, i, v) }))} />
                ))}
                <button type="button" onClick={() => update((d) => ({ ...d, ys: equalize(d.ys) }))}
                  className="w-full px-2 py-1.5 text-xs rounded border border-slate-300 hover:bg-slate-50">{t("editor.panels.table.equalizeRowsBtn")}</button>
              </div>
            </details>
            <p className="text-[11px] text-slate-500">{t("editor.panels.table.autoWrapNote")}</p>
            {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
            {lastResult && !changed && (
              <p className="text-xs text-green-700" role="status">
                {t("editor.panels.table.tableUpdated")}
                {lastResult.wrapped_cells?.length ? t("editor.panels.table.wrappedCellsSuffix", { count: lastResult.wrapped_cells.length }) : ""}
                {lastResult.adjusted_rows?.length ? t("editor.panels.table.adjustedRowsSuffix", { rows: lastResult.adjusted_rows.map((r) => r + 1).join(", ") }) : ""}
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
                {t("editor.panels.table.resetBtn")}
              </button>
              <button type="button" onClick={() => void apply({ onDone: onClose })} disabled={applying}
                className="flex-1 px-3 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
                {applying ? t("editor.panels.table.drawingTable") : t("editor.panels.table.applyBtn")}
              </button>
            </div>
          </>
        )}
        {!selected && error && <p className="text-xs text-red-600" role="alert">{error}</p>}
      </div>
    </aside>
  );
}
