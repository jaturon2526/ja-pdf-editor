// useContinuousPages.js — Virtual Continuous Scroll ที่ไม่เพิ่มภาระให้เซิร์ฟเวอร์:
// - โหลดภาพเฉพาะหน้าที่อยู่ในจอ ± 1 หน้า (debounce 120ms กันเลื่อนเร็ว ๆ ยิง API รัว)
// - ยกเลิก request ของหน้าที่เลื่อนผ่านออกนอกจอแล้วด้วย AbortController
// - จำกัดคำขอพร้อมกันไม่เกิน 2 หน้า และแคชภาพในหน่วยความจำเบราว์เซอร์แบบ LRU (สูงสุด 15 หน้า)
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "../api.js";
import {
  computePageLayouts,
  createPageCache,
  findVisiblePageRange,
} from "../utils/continuousScroll.js";

const FETCH_DEBOUNCE_MS = 60;
const MAX_CONCURRENT_FETCHES = 2;
const MAX_CACHED_PAGES = 15;

export function useContinuousPages({
  enabled,
  session,
  currentPage,
  pageImage,
  pageImagePage,
  zoom,
  canvasAreaRef,
  canAutoSwitchPage = true,
  onSelectPageFromScroll,
}) {
  const pageSizes = session?.pageSizes;
  const active = Boolean(enabled && session && (pageSizes?.length || 0) > 1);

  const { layouts } = useMemo(
    () => computePageLayouts(pageSizes || [], zoom),
    [pageSizes, zoom],
  );

  const cacheRef = useRef(null);
  if (!cacheRef.current) cacheRef.current = createPageCache(MAX_CACHED_PAGES);

  const [cachedPages, setCachedPages] = useState({});
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 1 });

  const inflightRef = useRef(new Map()); // pageIndex -> AbortController
  const scrollDrivenPageRef = useRef(null); // ป้องกัน jump กลับเมื่อ currentPage เปลี่ยนจากการเลื่อนเอง
  const prevPageRef = useRef(currentPage); // ใช้เช็กว่า currentPage เปลี่ยนจริง (ไม่เลื่อนกลับหัวหน้าตอนซูม/pinch-zoom)
  const ignoreScrollUntilRef = useRef(0);
  const currentPageRef = useRef(currentPage);
  currentPageRef.current = currentPage;
  const layoutsRef = useRef(layouts);
  layoutsRef.current = layouts;
  const canAutoSwitchRef = useRef(canAutoSwitchPage);
  canAutoSwitchRef.current = canAutoSwitchPage;
  const onSelectPageRef = useRef(onSelectPageFromScroll);
  onSelectPageRef.current = onSelectPageFromScroll;

  const abortAll = useCallback(() => {
    for (const ctrl of inflightRef.current.values()) {
      ctrl.abort();
    }
    inflightRef.current.clear();
  }, []);

  const invalidate = useCallback(() => {
    abortAll();
    cacheRef.current.clear();
    setCachedPages({});
  }, [abortAll]);

  // เปลี่ยนเอกสาร / จำนวนหน้า / ซูม / ปิดโหมดต่อเนื่อง → ล้างแคชและยกเลิกคำขอค้าง
  useEffect(() => {
    invalidate();
  }, [active, session?.sessionId, session?.pageCount, zoom, invalidate]);

  // ซิงค์ภาพของ currentPage ที่ useSession โหลดมาแล้วเข้าแคชทันที (เฉพาะเมื่อ pageImagePage ตรงกับ currentPage
  // ป้องกันเอาภาพหน้าก่อนหน้าไปทับช่องหน้าใหม่ตอนกำลังเลื่อนผ่านรอยต่อหน้า)
  useEffect(() => {
    if (!active || !pageImage || pageImagePage !== currentPage) return;
    if (cacheRef.current.get(currentPage) === pageImage) return;
    cacheRef.current.set(currentPage, pageImage);
    setCachedPages(cacheRef.current.toObject());
  }, [active, currentPage, pageImage, pageImagePage]);

  // เลื่อน scroll ไปที่หน้าเป้าหมายเมื่อ currentPage เปลี่ยนจากปุ่ม/Sidebar/Find (ไม่ใช่จากการเลื่อนเองหรือการซูม)
  useEffect(() => {
    if (!active) {
      prevPageRef.current = currentPage;
      return;
    }
    const pageChanged = prevPageRef.current !== currentPage;
    prevPageRef.current = currentPage;
    if (!pageChanged) return;
    if (scrollDrivenPageRef.current === currentPage) {
      scrollDrivenPageRef.current = null;
      return;
    }
    const el = canvasAreaRef?.current;
    const curLayouts = layoutsRef.current;
    const target = curLayouts[currentPage];
    if (!el || !target) return;
    ignoreScrollUntilRef.current = Date.now() + 250;
    el.scrollTop = Math.max(0, target.top);
    const range = findVisiblePageRange(curLayouts, el.scrollTop, el.clientHeight || 800, 1);
    setVisibleRange({ start: range.start, end: range.end });
  }, [active, currentPage, canvasAreaRef]);

  // ติดตามตำแหน่ง scroll เพื่อหาช่วงหน้าที่มองเห็นและอัปเดต currentPage อัตโนมัติ
  useEffect(() => {
    if (!active) return undefined;
    const el = canvasAreaRef?.current;
    if (!el) return undefined;

    let rafId = null;
    const syncScroll = () => {
      rafId = null;
      const range = findVisiblePageRange(layouts, el.scrollTop, el.clientHeight || 800, 1);
      setVisibleRange((prev) => (
        prev.start === range.start && prev.end === range.end ? prev : { start: range.start, end: range.end }
      ));
      if (
        Date.now() >= ignoreScrollUntilRef.current
        && canAutoSwitchRef.current
        && range.dominantPage !== currentPageRef.current
      ) {
        scrollDrivenPageRef.current = range.dominantPage;
        onSelectPageRef.current?.(range.dominantPage);
      }
    };

    const onScroll = () => {
      if (rafId === null) rafId = window.requestAnimationFrame(syncScroll);
    };

    syncScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      if (rafId !== null) window.cancelAnimationFrame(rafId);
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [active, layouts, canvasAreaRef]);

  // โหลดภาพเฉพาะหน้าที่อยู่ใน visibleRange (debounce 120ms + max 2 concurrent + abort หน้าที่พ้นจอ)
  useEffect(() => {
    if (!active || !session) return undefined;
    const { start, end } = visibleRange;

    // ยกเลิกคำขอของหน้าที่เลื่อนหลุดนอกช่วงมองเห็นไปแล้วทันที
    for (const [pageIdx, ctrl] of inflightRef.current.entries()) {
      if (pageIdx < start || pageIdx > end) {
        ctrl.abort();
        inflightRef.current.delete(pageIdx);
      }
    }

    const timer = window.setTimeout(() => {
      const needed = [];
      for (let p = start; p <= end; p += 1) {
        if (p === currentPageRef.current) continue; // useSession โหลด currentPage อยู่แล้ว
        if (cacheRef.current.has(p) || inflightRef.current.has(p)) continue;
        needed.push(p);
      }
      if (!needed.length) return;

      // โหลดหน้าที่ใกล้ currentPage ก่อน
      needed.sort((a, b) => Math.abs(a - currentPageRef.current) - Math.abs(b - currentPageRef.current));

      let cursor = 0;
      const pump = () => {
        while (inflightRef.current.size < MAX_CONCURRENT_FETCHES && cursor < needed.length) {
          const pageIdx = needed[cursor];
          cursor += 1;
          if (cacheRef.current.has(pageIdx) || inflightRef.current.has(pageIdx)) continue;
          const ctrl = new AbortController();
          inflightRef.current.set(pageIdx, ctrl);
          api.renderPage(session.sessionId, pageIdx, zoom, { signal: ctrl.signal })
            .then((data) => {
              if (ctrl.signal.aborted) return;
              cacheRef.current.set(pageIdx, data.image_base64);
              setCachedPages(cacheRef.current.toObject());
            })
            .catch(() => { /* ยกเลิกตอนเลื่อนผ่านหรือโหลดชั่วคราวไม่สำเร็จ — ข้ามได้ */ })
            .finally(() => {
              if (inflightRef.current.get(pageIdx) === ctrl) {
                inflightRef.current.delete(pageIdx);
              }
              if (!ctrl.signal.aborted) pump();
            });
        }
      };
      pump();
    }, FETCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [active, session, zoom, visibleRange]);

  // ล้างคำขอทั้งหมดตอน unmount
  useEffect(() => abortAll, [abortAll]);

  const scrollToPage = useCallback((pageIdx) => {
    const el = canvasAreaRef?.current;
    const target = layouts[pageIdx];
    if (!el || !target) return;
    ignoreScrollUntilRef.current = Date.now() + 250;
    el.scrollTop = Math.max(0, target.top);
  }, [layouts, canvasAreaRef]);

  return {
    active,
    layouts,
    cachedPages,
    invalidate,
    scrollToPage,
  };
}
