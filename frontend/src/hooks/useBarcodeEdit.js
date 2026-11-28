// เครื่องมือ "ย้าย/ลบบาร์โค้ด" (v1.41.0): โหลดบาร์โค้ด/QR ในหน้า → เลือก → ลากย้าย (draft บนหน้าเว็บ) → ตกลง = backend ย้ายจริง
// หรือ ลบ · ไม่แก้ข้อมูลในบาร์โค้ด (ผู้ใช้เลือก: อยากเปลี่ยนให้ลบแล้วแทรกใหม่)
import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

const MATCH_PT = 3;
const near = (a, b) => ["x0", "y0", "x1", "y1"].every((k) => Math.abs(a[k] - b[k]) <= MATCH_PT);
const shift = (r, dx, dy) => ({ x0: r.x0 + dx, y0: r.y0 + dy, x1: r.x1 + dx, y1: r.y1 + dy });

export function useBarcodeEdit({ session, currentPage, pageImage, active, runDocumentChange }) {
  const { t } = useI18n();
  const [barcodes, setBarcodes] = useState(null);
  const [rotated, setRotated] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [draft, setDraft] = useState(null); // กรอบใหม่ {x0, y0, x1, y1}
  const [error, setError] = useState("");
  const [applying, setApplying] = useState(false);
  const [lastAction, setLastAction] = useState(""); // "moved" | "deleted"
  const reselect = useRef(null); // ย้ายแล้ว → เลือกบาร์โค้ดที่ตำแหน่งใหม่ต่อเมื่อโหลดรายการใหม่

  useEffect(() => {
    if (!active || !session) {
      setBarcodes(null);
      setSelectedId(null);
      setDraft(null);
      setLastAction("");
      return undefined;
    }
    let cancelled = false;
    setError("");
    api.getBarcodes(session.sessionId, currentPage)
      .then((res) => {
        if (cancelled) return;
        const list = res.barcodes || [];
        setBarcodes(list);
        setRotated(!!res.rotated);
        const want = reselect.current;
        reselect.current = null;
        setSelectedId((id) => {
          if (want) return list.find((b) => near(b.bbox, want))?.id ?? null;
          return list.some((b) => b.id === id) ? id : null;
        });
      })
      .catch((e) => { if (!cancelled) { setBarcodes([]); setError(e.message || t("editor.hooks.barcode.loadFailed")); } });
    return () => { cancelled = true; };
  }, [active, session?.sessionId, currentPage, pageImage, t]); // eslint-disable-line react-hooks/exhaustive-deps

  const selected = barcodes?.find((b) => b.id === selectedId) || null;

  useEffect(() => {
    setDraft(selected ? { ...selected.bbox } : null);
  }, [selected?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = useCallback((id) => {
    setSelectedId(id);
    setError("");
    setLastAction("");
  }, []);

  const moveBy = useCallback((dx, dy) => setDraft((d) => (d ? shift(d, dx, dy) : d)), []);
  const moveTo = useCallback((x0, y0) => setDraft((d) => (d ? shift(d, x0 - d.x0, y0 - d.y0) : d)), []);
  const reset = useCallback(() => { if (selected) setDraft({ ...selected.bbox }); }, [selected]);

  const changed = !!(selected && draft && !["x0", "y0"].every((k) => Math.abs(draft[k] - selected.bbox[k]) <= 0.05));

  async function run(target) {
    if (!selected || applying) return;
    setApplying(true);
    setError("");
    reselect.current = target; // ตั้งก่อน — รายการโหลดใหม่ทันทีที่ภาพหน้าเปลี่ยน (ระหว่าง runDocumentChange)
    try {
      await runDocumentChange((sid) => api.editBarcodeObject(sid, currentPage, { bbox: selected.bbox, target }), {
        nextPage: currentPage,
        success: target ? t("editor.hooks.barcode.moved") : t("editor.hooks.barcode.deleted"),
        failure: target ? t("editor.hooks.barcode.moveFailed") : t("editor.hooks.barcode.deleteFailed"),
        rethrow: true,
        keepTool: true,
      });
      if (!target) setSelectedId(null);
      setLastAction(target ? "moved" : "deleted");
    } catch (e) {
      reselect.current = null;
      setError(e.message || t("editor.hooks.barcode.actionFailed"));
    } finally {
      setApplying(false);
    }
  }

  return {
    barcodes, rotated, selected, select, draft, moveBy, moveTo, reset, changed, applying, error, lastAction,
    apply: () => (changed ? run(draft) : undefined),
    remove: () => run(null),
  };
}
