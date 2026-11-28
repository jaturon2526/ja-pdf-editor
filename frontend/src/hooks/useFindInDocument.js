// ค้นหาข้อความในเอกสาร (Ctrl+F, v1.42.0): ค้นทุกหน้าผ่าน GET /pdf/{sid}/search → ไฮไลต์บนหน้า + กระโดดข้ามหน้า
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

export function useFindInDocument({ session, currentPage, goToPage }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [matches, setMatches] = useState([]);
  const [truncated, setTruncated] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [focusTick, setFocusTick] = useState(0);
  const currentPageRef = useRef(currentPage);
  currentPageRef.current = currentPage;
  const goToPageRef = useRef(goToPage);
  goToPageRef.current = goToPage;

  // รีเซ็ตเมื่อเปลี่ยนหรือปิดเอกสาร
  useEffect(() => {
    setOpen(false);
    setQuery("");
    setMatches([]);
    setTruncated(false);
    setActiveIndex(-1);
    setError("");
  }, [session?.sessionId]);

  const openFind = useCallback(() => {
    if (!session) return;
    setOpen(true);
    setFocusTick((n) => n + 1);
  }, [session]);

  const closeFind = useCallback(() => {
    setOpen(false);
    setMatches([]);
    setTruncated(false);
    setActiveIndex(-1);
    setError("");
  }, []);

  // ค้นหาอัตโนมัติเมื่อพิมพ์คำค้นหรือสลับตัวพิมพ์ใหญ่-เล็ก (debounce 220ms)
  useEffect(() => {
    if (!open || !session) return undefined;
    const trimmed = query.trim();
    if (!trimmed) {
      setMatches([]);
      setTruncated(false);
      setActiveIndex(-1);
      setError("");
      setSearching(false);
      return undefined;
    }
    let cancelled = false;
    setSearching(true);
    setError("");
    const timer = setTimeout(() => {
      api
        .searchPdfText(session.sessionId, trimmed, { matchCase })
        .then((res) => {
          if (cancelled) return;
          const list = res.matches || [];
          setMatches(list);
          setTruncated(!!res.truncated);
          if (list.length === 0) {
            setActiveIndex(-1);
            return;
          }
          // เลือกจุดแรกที่อยู่บนหน้าปัจจุบันหรือถัดไป (ถ้าไม่มีเลยให้เริ่มที่จุดแรกของเอกสาร)
          const idx = list.findIndex((m) => m.page >= currentPageRef.current);
          const pick = idx >= 0 ? idx : 0;
          setActiveIndex(pick);
          if (list[pick].page !== currentPageRef.current) {
            goToPageRef.current(list[pick].page);
          }
        })
        .catch((err) => {
          if (cancelled) return;
          setMatches([]);
          setTruncated(false);
          setActiveIndex(-1);
          setError(err.message || t("editor.hooks.find.searchFailed"));
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 220);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, session, query, matchCase, t]);

  const jumpTo = useCallback((nextIdx) => {
    if (matches.length === 0) return;
    const wrapped = ((nextIdx % matches.length) + matches.length) % matches.length;
    setActiveIndex(wrapped);
    const targetPage = matches[wrapped].page;
    if (targetPage !== currentPageRef.current) {
      goToPageRef.current(targetPage);
    }
  }, [matches]);

  const next = useCallback(() => {
    jumpTo(activeIndex + 1);
  }, [activeIndex, jumpTo]);

  const prev = useCallback(() => {
    jumpTo(activeIndex - 1);
  }, [activeIndex, jumpTo]);

  const pageMatches = useMemo(
    () =>
      open
        ? matches
            .filter((m) => m.page === currentPage)
            .map((m) => ({ ...m, active: m.index === activeIndex }))
        : [],
    [open, matches, currentPage, activeIndex],
  );

  return {
    open,
    query,
    setQuery,
    matchCase,
    setMatchCase,
    matches,
    truncated,
    activeIndex,
    searching,
    error,
    focusTick,
    pageMatches,
    openFind,
    closeFind,
    next,
    prev,
  };
}
