// เครื่องมือ "ตรวจฟอนต์" (v1.38.0): โหลดข้อความระดับ span ของหน้าปัจจุบันพร้อมชื่อฟอนต์/ขนาด/สี/การฝัง
// ไม่แก้ไฟล์ — โหลดใหม่เมื่อเปลี่ยนหน้า หรือภาพหน้าเปลี่ยน (แก้ไข/undo แล้ว)
import { useEffect, useMemo, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

export function useFontInspector({ session, currentPage, pageImage, active }) {
  const { t } = useI18n();
  const [spans, setSpans] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!active || !session) {
      setSpans(null);
      setSelected(null);
      return undefined;
    }
    let cancelled = false;
    setError("");
    setSelected(null);
    api.getFontSpans(session.sessionId, currentPage)
      .then((list) => { if (!cancelled) setSpans(list); })
      .catch((e) => { if (!cancelled) { setSpans([]); setError(e.message || t("editor.hooks.fontInspector.loadFailed")); } });
    return () => { cancelled = true; };
  }, [active, session?.sessionId, currentPage, pageImage, t]); // eslint-disable-line react-hooks/exhaustive-deps

  // ฟอนต์ในหน้านี้ (ไม่ซ้ำตามชื่อ+ขนาด) — สรุปในแผงเมื่อยังไม่ได้เลือกข้อความ
  const pageFonts = useMemo(() => {
    const map = new Map();
    for (const s of spans || []) {
      const key = `${s.name}|${s.size}|${s.color}|${s.bold}|${s.italic}`;
      const entry = map.get(key);
      if (entry) entry.chars += s.text.length;
      else map.set(key, { ...s, chars: s.text.length });
    }
    return [...map.values()].sort((a, b) => b.chars - a.chars);
  }, [spans]);

  return { spans, pageFonts, selected, setSelected, error };
}
