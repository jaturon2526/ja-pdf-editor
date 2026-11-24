// เครื่องมือ "แก้ไขตาราง" (v1.40.0 + โครงสร้างตาราง v1.46.0):
// โหลดตารางในหน้า → เลือก → ปรับเส้นแบ่ง (draft บนหน้าเว็บ) หรือ เพิ่ม/ลบแถว-คอลัมน์ / รวม-แยกเซลล์ → backend วาดใหม่
// ทับข้อความอื่น → backend ตอบ 409 → ถามยืนยันในแผง (overlapWarning) แล้วส่ง allowOverlap
import { useCallback, useEffect, useState } from "react";
import * as api from "../api.js";
import { translate } from "../utils/tableGeometry.js";

const OP_LABELS = {
  insert_row: "เพิ่มแถวแล้ว",
  delete_row: "ลบแถวแล้ว",
  insert_col: "เพิ่มคอลัมน์แล้ว",
  delete_col: "ลบคอลัมน์แล้ว",
  merge_cells: "รวมเซลล์แล้ว",
  split_cell: "แยกเซลล์แล้ว",
};

export function useTableEdit({ session, currentPage, pageImage, active, runDocumentChange }) {
  const [tables, setTables] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null); // { xs, ys }
  const [cellSelection, setCellSelection] = useState(null); // { r0, c0, r1, c1 }
  const [multiSelectMode, setMultiSelectMode] = useState(false); // มือถือไม่มี Shift — เปิดเพื่อแตะขยายช่วงเซลล์
  const [error, setError] = useState("");
  const [overlapWarning, setOverlapWarning] = useState("");
  const [pendingOverlapOp, setPendingOverlapOp] = useState(null); // null = apply size · { op, opts } = structure op
  const [applying, setApplying] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [expandMode, setExpandMode] = useState(false); // มือถือไม่มีปุ่ม Shift — เปิดสวิตช์นี้เพื่อให้ลากเส้นแบ่งแล้วช่องถัดไปเลื่อนตาม
  const [cellText, setCellText] = useState("");
  const [cellFontKey, setCellFontKey] = useState("sarabun");
  const [cellFontSize, setCellFontSize] = useState(11);
  const [cellColorHex, setCellColorHex] = useState("#000000");
  const [cellTextAlign, setCellTextAlign] = useState(""); // "" = อัตโนมัติตามคอลัมน์ · "left" | "center" | "right"
  const [cellTextValign, setCellTextValign] = useState("middle"); // "top" | "middle" | "bottom"
  const [cellUnderline, setCellUnderline] = useState(false);
  const [origCellStyle, setOrigCellStyle] = useState({
    fontKey: "sarabun",
    fontSize: 11,
    colorHex: "#000000",
    align: "",
    valign: "middle",
    underline: false,
  });
  const [editingCellOnCanvas, setEditingCellOnCanvas] = useState(false);

  useEffect(() => {
    if (!active || !session) {
      setTables(null);
      setSelectedId(null);
      setDraft(null);
      setCellSelection(null);
      return undefined;
    }
    let cancelled = false;
    setError("");
    api.getTables(session.sessionId, currentPage)
      .then((list) => {
        if (cancelled) return;
        setTables(list);
        // ตารางที่เลือกอยู่ (เพิ่งวาดใหม่) ยังอยู่ → เลือกค้างไว้ให้แก้ต่อ ไม่งั้นล้าง
        setSelectedId((id) => (list.some((t) => t.id === id) ? id : null));
        setDraft((d) => d);
      })
      .catch((e) => { if (!cancelled) { setTables([]); setError(e.message || "อ่านตารางไม่สำเร็จ"); } });
    return () => { cancelled = true; };
  }, [active, session?.sessionId, currentPage, pageImage]); // eslint-disable-line react-hooks/exhaustive-deps

  const selected = tables?.find((t) => t.id === selectedId) || null;
  const activeCell = selected && cellSelection
    ? selected.cells.find((c) => (
      cellSelection.r0 >= c.r && cellSelection.r0 < c.r + c.rowspan
      && cellSelection.c0 >= c.c && cellSelection.c0 < c.c + c.colspan
    )) || null
    : null;
  const activeCellKey = activeCell ? `${activeCell.r},${activeCell.c}` : null;
  const activeCellOrigText = (selected && activeCellKey && selected.cell_texts?.[activeCellKey]) || "";
  const activeCellOrigStyle = (selected && activeCellKey && selected.cell_styles?.[activeCellKey]) || null;

  useEffect(() => {
    setCellText(activeCellOrigText);
    if (activeCellOrigStyle) {
      const nextStyle = {
        fontKey: activeCellOrigStyle.fontname || "sarabun",
        fontSize: Number(activeCellOrigStyle.fontsize) || 11,
        colorHex: (activeCellOrigStyle.color || "#000000").toLowerCase(),
        align: activeCellOrigStyle.align || "",
        valign: activeCellOrigStyle.valign || "middle",
        underline: false,
      };
      setCellFontKey(nextStyle.fontKey);
      setCellFontSize(nextStyle.fontSize);
      setCellColorHex(nextStyle.colorHex);
      setCellTextAlign(nextStyle.align);
      setCellTextValign(nextStyle.valign);
      setCellUnderline(false);
      setOrigCellStyle(nextStyle);
    } else {
      // เซลล์ว่าง: คงฟอนต์และสไตล์ที่ผู้ใช้เลือกค้างไว้ เพื่อให้พิมพ์หลายช่องต่อเนื่องได้สะดวก
      setOrigCellStyle({
        fontKey: cellFontKey,
        fontSize: cellFontSize,
        colorHex: (cellColorHex || "#000000").toLowerCase(),
        align: cellTextAlign,
        valign: cellTextValign,
        underline: cellUnderline,
      });
    }
  }, [ // eslint-disable-line react-hooks/exhaustive-deps
    selected?.id,
    activeCell?.r,
    activeCell?.c,
    activeCellOrigText,
    activeCellOrigStyle?.fontname,
    activeCellOrigStyle?.fontsize,
    activeCellOrigStyle?.color,
    activeCellOrigStyle?.align,
    activeCellOrigStyle?.valign,
  ]);

  // เลือกตาราง/ตารางเปลี่ยนหลังวาดใหม่ → draft เริ่มจากตำแหน่งปัจจุบัน + clamp cellSelection ให้อยู่ในตาราง
  useEffect(() => {
    setDraft(selected ? { xs: [...selected.xs], ys: [...selected.ys] } : null);
    setOverlapWarning("");
    setPendingOverlapOp(null);
    if (!selected) {
      setCellSelection(null);
      return;
    }
    const maxR = Math.max(0, selected.ys.length - 2);
    const maxC = Math.max(0, selected.xs.length - 2);
    setCellSelection((prev) => {
      if (!prev) return { r0: 0, c0: 0, r1: 0, c1: 0 };
      const r0 = Math.min(prev.r0, maxR);
      const c0 = Math.min(prev.c0, maxC);
      const r1 = Math.min(prev.r1, maxR);
      const c1 = Math.min(prev.c1, maxC);
      return { r0, c0, r1, c1 };
    });
  }, [selected?.id, selected?.xs?.join(","), selected?.ys?.join(","), selected?.cells?.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = useCallback((id) => {
    setSelectedId(id);
    setCellSelection({ r0: 0, c0: 0, r1: 0, c1: 0 });
    setError("");
    setLastResult(null);
  }, []);

  const selectCell = useCallback((cell, extend = false, startInlineEdit = false) => {
    if (!cell) return;
    const cr0 = cell.r;
    const cc0 = cell.c;
    const cr1 = cell.r + cell.rowspan - 1;
    const cc1 = cell.c + cell.colspan - 1;
    setCellSelection((prev) => {
      if ((extend || multiSelectMode) && prev) {
        setEditingCellOnCanvas(false);
        return {
          r0: Math.min(prev.r0, cr0),
          c0: Math.min(prev.c0, cc0),
          r1: Math.max(prev.r1, cr1),
          c1: Math.max(prev.c1, cc1),
        };
      }
      const sameSingleCell = prev && prev.r0 === cr0 && prev.c0 === cc0 && prev.r1 === cr1 && prev.c1 === cc1;
      setEditingCellOnCanvas(Boolean(startInlineEdit || sameSingleCell));
      return { r0: cr0, c0: cc0, r1: cr1, c1: cc1 };
    });
    setError("");
  }, [multiSelectMode]);

  const update = useCallback((fn) => {
    setDraft((d) => (d ? fn(d) : d));
    setOverlapWarning("");
    setPendingOverlapOp(null);
  }, []);

  const moveBy = useCallback((dx, dy) => update((d) => ({ xs: translate(d.xs, dx), ys: translate(d.ys, dy) })), [update]);

  const reset = useCallback(() => {
    if (selected) setDraft({ xs: [...selected.xs], ys: [...selected.ys] });
    setCellText(activeCellOrigText);
    setCellFontKey(origCellStyle.fontKey);
    setCellFontSize(origCellStyle.fontSize);
    setCellColorHex(origCellStyle.colorHex);
    setCellTextAlign(origCellStyle.align);
    setCellTextValign(origCellStyle.valign);
    setCellUnderline(origCellStyle.underline);
    setEditingCellOnCanvas(false);
    setOverlapWarning("");
    setPendingOverlapOp(null);
    setError("");
  }, [selected, activeCellOrigText, origCellStyle]);

  // ขยายตารางให้เต็มพื้นที่หน้ากระดาษ: "width" (ซ้าย-ขวา) · "height" (บน-ล่าง) · "full" (เต็มหน้า)
  const fitTableToPage = useCallback((mode) => {
    if (!session) return;
    const [pw, ph] = session.pageSizes?.[currentPage] || [595, 842];
    const margin = 20;
    const fitLines = (lines, minPos, maxPos) => {
      if (!lines || lines.length < 2) return lines;
      const oldSpan = lines.at(-1) - lines[0];
      const newSpan = Math.max((lines.length - 1) * 6, maxPos - minPos);
      if (oldSpan <= 0) return lines;
      return lines.map((v) => Math.round((minPos + ((v - lines[0]) / oldSpan) * newSpan) * 100) / 100);
    };
    update((d) => ({
      xs: mode === "width" || mode === "full" ? fitLines(d.xs, margin, pw - margin) : d.xs,
      ys: mode === "height" || mode === "full" ? fitLines(d.ys, margin, ph - margin) : d.ys,
    }));
  }, [session, currentPage, update]);

  const changed = !!(selected && draft && (draft.xs.some((v, i) => Math.abs(v - selected.xs[i]) > 0.05)
    || draft.ys.some((v, i) => Math.abs(v - selected.ys[i]) > 0.05)));
  const cellStyleDirty = !!(
    cellFontKey !== origCellStyle.fontKey
    || Math.abs((Number(cellFontSize) || 11) - (Number(origCellStyle.fontSize) || 11)) > 0.05
    || (cellColorHex || "#000000").toLowerCase() !== (origCellStyle.colorHex || "#000000").toLowerCase()
    || (cellTextAlign || "") !== (origCellStyle.align || "")
    || (cellTextValign || "middle") !== (origCellStyle.valign || "middle")
    || Boolean(cellUnderline) !== Boolean(origCellStyle.underline)
  );
  const cellTextDirty = !!(
    selected
    && activeCell
    && (cellText.trim() !== activeCellOrigText.trim() || (cellText.trim() !== "" && cellStyleDirty))
  );

  async function saveCellText(textOverride = null, { moveCol = 0, moveRow = 0 } = {}) {
    if (!selected || !cellSelection || applying) return null;
    const nextText = textOverride !== null ? textOverride : cellText;
    const totalRows = selected.ys.length - 1;
    const totalCols = selected.xs.length - 1;
    const curR = cellSelection.r0;
    const curC = cellSelection.c0;

    const advanceSelection = () => {
      if (moveCol === 0 && moveRow === 0) return;
      let nr = curR + moveRow;
      let nc = curC + moveCol;
      if (nc >= totalCols) {
        nc = 0;
        nr += 1;
      } else if (nc < 0) {
        nc = Math.max(0, totalCols - 1);
        nr -= 1;
      }
      nr = Math.max(0, Math.min(totalRows - 1, nr));
      nc = Math.max(0, Math.min(totalCols - 1, nc));
      setCellSelection({ r0: nr, c0: nc, r1: nr, c1: nc });
    };

    if (nextText.trim() === activeCellOrigText.trim() && !(nextText.trim() !== "" && cellStyleDirty)) {
      advanceSelection();
      return null;
    }

    setApplying(true);
    setError("");
    try {
      let result = null;
      await runDocumentChange(async (sid) => {
        result = await api.editTableCellText(sid, currentPage, {
          bbox: selected.bbox,
          r0: curR,
          c0: curC,
          text: nextText,
          fontname: cellFontKey || null,
          fontsize: Number.isFinite(Number(cellFontSize)) && Number(cellFontSize) >= 4 ? Number(cellFontSize) : null,
          align: cellTextAlign || null,
          valign: cellTextValign || "middle",
          color: cellColorHex || null,
          underline: Boolean(cellUnderline),
        });
        return result;
      }, {
        nextPage: currentPage,
        success: "บันทึกข้อความในเซลล์แล้ว",
        failure: "บันทึกข้อความในเซลล์ไม่สำเร็จ",
        rethrow: true,
        keepTool: true,
      });
      setLastResult(result);
      if (result?.id) setSelectedId(result.id);
      advanceSelection();
      return result;
    } catch (e) {
      setError(e.message || "บันทึกข้อความในเซลล์ไม่สำเร็จ");
      return null;
    } finally {
      setApplying(false);
    }
  }

  async function createNewTable({ rows = 3, cols = 4 } = {}) {
    if (!session || applying) return null;
    const cleanRows = Math.max(1, Math.min(50, Number.parseInt(rows, 10) || 3));
    const cleanCols = Math.max(1, Math.min(30, Number.parseInt(cols, 10) || 4));
    setApplying(true);
    setError("");
    try {
      let result = null;
      await runDocumentChange(async (sid) => {
        result = await api.createTable(sid, currentPage, { rows: cleanRows, cols: cleanCols });
        return result;
      }, {
        nextPage: currentPage,
        success: `สร้างตาราง ${cleanRows} แถว × ${cleanCols} คอลัมน์แล้ว`,
        failure: "สร้างตารางไม่สำเร็จ",
        rethrow: true,
        keepTool: true,
      });
      setLastResult(result);
      setOverlapWarning("");
      setPendingOverlapOp(null);
      if (result?.id) {
        setSelectedId(result.id);
        setCellSelection({ r0: 0, c0: 0, r1: 0, c1: 0 });
      }
      return result;
    } catch (e) {
      setError(e.message || "สร้างตารางไม่สำเร็จ");
      return null;
    } finally {
      setApplying(false);
    }
  }

  async function apply({ allowOverlap = false, onDone = null } = {}) {
    if (!selected || !draft || applying) return;
    if (!changed && !cellTextDirty) {
      setEditingCellOnCanvas(false);
      onDone?.();
      return;
    }
    if (!changed && cellTextDirty) {
      await saveCellText();
      return;
    }
    setApplying(true);
    setError("");
    try {
      let result = null;
      await runDocumentChange(async (sid) => {
        result = await api.editTable(sid, currentPage, { bbox: selected.bbox, xs: draft.xs, ys: draft.ys, allowOverlap });
        if (cellTextDirty && cellSelection) {
          const nextBbox = {
            x0: result.xs[0],
            y0: result.ys[0],
            x1: result.xs.at(-1),
            y1: result.ys.at(-1),
          };
          const cellRes = await api.editTableCellText(sid, currentPage, {
            bbox: nextBbox,
            r0: cellSelection.r0,
            c0: cellSelection.c0,
            text: cellText,
            fontname: cellFontKey || null,
            fontsize: Number.isFinite(Number(cellFontSize)) && Number(cellFontSize) >= 4 ? Number(cellFontSize) : null,
            align: cellTextAlign || null,
            valign: cellTextValign || "middle",
            color: cellColorHex || null,
            underline: Boolean(cellUnderline),
          });
          result = { ...result, ...cellRes };
        }
        return result;
      }, {
        nextPage: currentPage,
        success: (res) => {
          const notes = [];
          if (res.wrapped_cells?.length) notes.push(`ตัดบรรทัดใหม่ ${res.wrapped_cells.length} ช่อง`);
          if (res.adjusted_rows?.length) notes.push(`แถว ${res.adjusted_rows.map((r) => r + 1).join(", ")} สูงขึ้นให้ข้อความพอ`);
          return `แก้ตารางแล้ว${notes.length ? ` — ${notes.join(" · ")}` : ""}`;
        },
        failure: "แก้ตารางไม่สำเร็จ",
        rethrow: true,
        keepTool: true,
      });
      setLastResult(result);
      setOverlapWarning("");
      setPendingOverlapOp(null);
      if (result?.id) setSelectedId(result.id);
    } catch (e) {
      if (e.status === 409) {
        setOverlapWarning(e.message);
        setPendingOverlapOp(null);
      } else {
        setError(e.message || "แก้ตารางไม่สำเร็จ");
      }
    } finally {
      setApplying(false);
    }
  }

  async function runStructure(op, opts = {}) {
    if (!selected || !cellSelection || applying) return;
    setApplying(true);
    setError("");
    try {
      let result = null;
      await runDocumentChange(async (sid) => {
        let baseBbox = selected.bbox;
        if (changed && draft) {
          const resized = await api.editTable(sid, currentPage, {
            bbox: selected.bbox,
            xs: draft.xs,
            ys: draft.ys,
            allowOverlap: !!opts.allowOverlap,
          });
          baseBbox = {
            x0: resized.xs[0],
            y0: resized.ys[0],
            x1: resized.xs.at(-1),
            y1: resized.ys.at(-1),
          };
        }
        result = await api.editTableStructure(sid, currentPage, {
          bbox: baseBbox,
          op,
          r0: cellSelection.r0,
          c0: cellSelection.c0,
          r1: cellSelection.r1,
          c1: cellSelection.c1,
          position: opts.position || "below",
          direction: opts.direction || "cols",
          allowOverlap: !!opts.allowOverlap,
        });
        return result;
      }, {
        nextPage: currentPage,
        success: OP_LABELS[op] || "แก้โครงสร้างตารางแล้ว",
        failure: "แก้โครงสร้างตารางไม่สำเร็จ",
        rethrow: true,
        keepTool: true,
      });
      setLastResult(result);
      setOverlapWarning("");
      setPendingOverlapOp(null);
      if (result?.id) setSelectedId(result.id);
      if (op === "insert_row") {
        const targetR = (opts.position || "below") === "above" ? cellSelection.r0 : cellSelection.r0 + 1;
        setCellSelection({ r0: targetR, c0: cellSelection.c0, r1: targetR, c1: cellSelection.c0 });
        setEditingCellOnCanvas(true);
      } else if (op === "insert_col") {
        const targetC = opts.position === "left" ? cellSelection.c0 : cellSelection.c0 + 1;
        setCellSelection({ r0: cellSelection.r0, c0: targetC, r1: cellSelection.r0, c1: targetC });
        setEditingCellOnCanvas(true);
      } else if (op === "merge_cells" || op === "split_cell") {
        setCellSelection({ r0: cellSelection.r0, c0: cellSelection.c0, r1: cellSelection.r0, c1: cellSelection.c0 });
      }
    } catch (e) {
      if (e.status === 409) {
        setOverlapWarning(e.message);
        setPendingOverlapOp({ op, opts });
      } else {
        setError(e.message || "แก้โครงสร้างตารางไม่สำเร็จ");
      }
    } finally {
      setApplying(false);
    }
  }

  async function confirmOverlap() {
    if (pendingOverlapOp) {
      await runStructure(pendingOverlapOp.op, { ...pendingOverlapOp.opts, allowOverlap: true });
    } else {
      await apply({ allowOverlap: true });
    }
  }

  return {
    tables, selected, selectedId, select, draft, update, moveBy, reset, changed,
    fitTableToPage, createNewTable,
    activeCell, cellText, setCellText,
    cellFontKey, setCellFontKey,
    cellFontSize, setCellFontSize,
    cellColorHex, setCellColorHex,
    cellTextAlign, setCellTextAlign,
    cellTextValign, setCellTextValign,
    cellUnderline, setCellUnderline,
    cellTextDirty, saveCellText,
    editingCellOnCanvas, setEditingCellOnCanvas,
    cellSelection, selectCell, multiSelectMode, setMultiSelectMode, runStructure, confirmOverlap,
    apply, applying, error, overlapWarning, lastResult, expandMode, setExpandMode,
  };
}
