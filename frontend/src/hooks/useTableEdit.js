// เครื่องมือ "แก้ไขตาราง" (v1.40.0): โหลดตารางในหน้า → เลือก → ปรับเส้นแบ่ง (draft บนหน้าเว็บ) → ตกลง = backend วาดใหม่
// ทับข้อความอื่น → backend ตอบ 409 → ถามยืนยันในแผง (overlapWarning) แล้วส่ง allowOverlap
import { useCallback, useEffect, useState } from "react";
import * as api from "../api.js";
import { translate } from "../utils/tableGeometry.js";

export function useTableEdit({ session, currentPage, pageImage, active, runDocumentChange }) {
  const [tables, setTables] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null); // { xs, ys }
  const [error, setError] = useState("");
  const [overlapWarning, setOverlapWarning] = useState("");
  const [applying, setApplying] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [expandMode, setExpandMode] = useState(false); // มือถือไม่มีปุ่ม Shift — เปิดสวิตช์นี้เพื่อให้ลากเส้นแบ่งแล้วช่องถัดไปเลื่อนตาม

  useEffect(() => {
    if (!active || !session) {
      setTables(null);
      setSelectedId(null);
      setDraft(null);
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

  // เลือกตาราง/ตารางเปลี่ยนหลังวาดใหม่ → draft เริ่มจากตำแหน่งปัจจุบัน
  useEffect(() => {
    setDraft(selected ? { xs: [...selected.xs], ys: [...selected.ys] } : null);
    setOverlapWarning("");
  }, [selected?.id, selected?.xs?.join(","), selected?.ys?.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = useCallback((id) => {
    setSelectedId(id);
    setError("");
    setLastResult(null);
  }, []);

  const update = useCallback((fn) => {
    setDraft((d) => (d ? fn(d) : d));
    setOverlapWarning("");
  }, []);

  const moveBy = useCallback((dx, dy) => update((d) => ({ xs: translate(d.xs, dx), ys: translate(d.ys, dy) })), [update]);

  const reset = useCallback(() => {
    if (selected) setDraft({ xs: [...selected.xs], ys: [...selected.ys] });
    setOverlapWarning("");
  }, [selected]);

  const changed = !!(selected && draft && (draft.xs.some((v, i) => Math.abs(v - selected.xs[i]) > 0.05)
    || draft.ys.some((v, i) => Math.abs(v - selected.ys[i]) > 0.05)));

  async function apply({ allowOverlap = false } = {}) {
    if (!selected || !draft || !changed || applying) return;
    setApplying(true);
    setError("");
    try {
      let result = null;
      await runDocumentChange(async (sid) => {
        result = await api.editTable(sid, currentPage, { bbox: selected.bbox, xs: draft.xs, ys: draft.ys, allowOverlap });
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
        keepTool: true, // แก้ต่อได้เลย (เลือกตารางเดิมค้างไว้)
      });
      setLastResult(result);
      setOverlapWarning("");
      if (result?.id) setSelectedId(result.id);
    } catch (e) {
      if (e.status === 409) setOverlapWarning(e.message);
      else setError(e.message || "แก้ตารางไม่สำเร็จ");
    } finally {
      setApplying(false);
    }
  }

  return {
    tables, selected, selectedId, select, draft, update, moveBy, reset, changed,
    apply, applying, error, overlapWarning, lastResult, expandMode, setExpandMode,
  };
}
