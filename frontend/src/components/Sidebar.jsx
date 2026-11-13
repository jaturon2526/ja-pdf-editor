import React, { useEffect, useRef, useState, useLayoutEffect } from "react";
import { pageImageSrc } from "../utils/pageImage.js";
import { keepInViewport } from "../utils/viewport.js";
import { newPositions, reorderedPages } from "../utils/pageOrder.js";

/**
 * Sidebar — ด้านซ้ายของจอ มี 2 แท็บมาตรฐานของ PDF editor ทั่วไป:
 * - Pages: thumbnail รายหน้า คลิกเพื่อกระโดดไปหน้านั้น — เลือกได้หลายหน้า (ctrl/cmd-click สลับทีละหน้า,
 *   shift-click เลือกเป็นช่วง), คลิกขวาเพื่อเปิดเมนูของแอปเอง (แทนที่เมนูขวาเริ่มต้นของเบราว์เซอร์ทั้งหมด)
 *   สำหรับ "เลื่อนหน้าขึ้น/ลง" และ "ส่งออกหน้าที่เลือกเป็นไฟล์ PDF ใหม่", และ "กดเมาส์ค้างที่ thumbnail
 *   แล้วลาก" เพื่อสลับ/ย้ายตำแหน่งหน้าจริงในเอกสาร (ผู้ใช้แจ้งขอฟีเจอร์นี้เพิ่ม — ดูหมายเหตุ "ลากสลับ
 *   ตำแหน่งหน้า (reorder)" ด้านล่าง)
 * - Bookmarks: รายการที่คั่นไว้ (เก็บใน state ฝั่ง frontend), คลิกเพื่อกระโดดไปหน้านั้น
 *
 * เรื่อง "ลากพื้นที่ว่างเพื่อเลื่อนจอขึ้นลง" (ฟีเจอร์เดิม จากรอบก่อนหน้า) — ใช้ pattern เดียวกับ
 * pointerdown+window-level pointermove/up ที่มีอยู่แล้วใน PDFCanvas.jsx (handlePanMouseDown, hand tool)
 * ผูกกับ .thumbnail-list (ตัว container) แต่ต่างตรงที่รายการ thumbnail แต่ละอันเป็น <button> ที่ต้อง
 * คลิกเพื่อกระโดดไปหน้านั้นได้ตามปกติด้วย — e.preventDefault() ตอน pointerdown ไม่ทำให้ browser ยกเลิก
 * click event ที่จะตามมาหลัง pointerup บน element เดียวกัน จึงต้องแยกแยะเอง "ลาก" กับ "คลิก" ด้วย ref
 * (didDragRef): ตั้งเป็น true ก็ต่อเมื่อระยะทางที่ลากเกิน threshold เล็กน้อย (กันมือสั่น/คลิกธรรมดาโดน
 * ตีความเป็นลาก) แล้วปล่อยให้ handler ของ onClick ที่ thumbnail แต่ละอัน "เช็คแล้วเคลียร์ทิ้ง" เอง
 * (didDragRef.current) เพราะ click จะยิงตามหลัง pointerup ทันทีบน target เดียวกันเสมอ
 *
 * เรื่อง "ลากสลับตำแหน่งหน้า (reorder)" (ฟีเจอร์ใหม่รอบนี้ — ผู้ใช้แจ้งว่าอยากได้ "กดเมาส์ค้างแล้วลาก
 * สลับหน้าได้" ต่างจาก "ลากพื้นที่ว่างเพื่อเลื่อนจอ" ด้านบนซึ่งแค่ scroll ไม่ได้ย้ายตำแหน่งหน้าจริงในไฟล์)
 * — ผูก pointerdown แยกไว้ที่ตัว thumbnail แต่ละอันเอง (handleThumbnailPointerDown) แล้วเรียก
 * e.stopPropagation() กันไม่ให้ pointerdown เดียวกันไป bubble ต่อถึง handleListPointerDown ของ container
 * (ไม่งั้นทั้งสองกลไกจะแย่งกันทำงานพร้อมกัน) ลากหน้าหนึ่งไปวางระหว่าง thumbnail อื่น จะเห็นเส้นไฮไลท์บอก
 * ตำแหน่งที่จะแทรก (computeDropTargetPage หาโดยเทียบ clientY กับจุดกึ่งกลางของแต่ละ thumbnail) ปล่อยเมาส์
 * แล้วเรียก onReorderPages(pagesที่ย้าย, หน้าที่จะแทรกก่อนหน้านั้น) ถ้ากำลังลากหน้าที่อยู่ใน multi-select
 * (เลือกไว้หลายหน้าด้วย ctrl/shift-click) จะย้ายทั้งกลุ่มไปด้วยกัน ไม่ใช่แค่หน้าเดียวที่กดลง — ระหว่างลาก
 * ถ้าเมาส์เข้าใกล้ขอบบน/ล่างของแผง จะ auto-scroll ให้เอง (เผื่อเอกสารยาวเกินจอ ต้องลากข้ามหน้าที่มองไม่เห็น)
 *
 * เรื่อง "ปรับขนาด/ซ่อนแผงหน้าเอกสารด้วยเมาส์" (ฟีเจอร์ใหม่รอบนี้ — ผู้ใช้แจ้งขอ) — มีแถบลาก
 * (.sidebar-resize-handle) แปะไว้ที่ขอบขวาของแผง ลากซ้าย/ขวาปรับความกว้าง (handleResizeStart, pattern
 * pointerdown+window pointermove/up เดียวกับด้านบน) จำกัดช่วงความกว้างไว้ (SIDEBAR_MIN/MAX_WIDTH) และมี
 * ปุ่มยุบ/ขยาย (« / ») ที่มุมแถบแท็บ — ตอนยุบ (collapsed) จะไม่ซ่อนทั้งแผงไปเลย (ไม่งั้นจะไม่มีทางกดขยาย
 * กลับมาได้อีก) แต่เหลือไว้เป็นแถบบางๆ (SIDEBAR_COLLAPSED_WIDTH) มีแค่ปุ่มขยายเท่านั้น ความกว้าง/สถานะ
 * ยุบเก็บเป็น local state ในนี้เอง (ไม่ได้ยกไปไว้ที่ App.jsx เพราะไม่มีส่วนอื่นต้องรู้ค่านี้)
 *
 * เรื่อง "เปลี่ยนชื่อ bookmark" (ฟีเจอร์ใหม่รอบนี้ — ผู้ใช้แจ้งขอ) — ดับเบิลคลิกที่ชื่อ bookmark หรือกด
 * ปุ่มดินสอ จะสลับรายการนั้นเป็นช่อง input แก้ไขชื่อได้ในที่ (renamingBookmarkId ชี้ว่ากำลังแก้อันไหนอยู่)
 * กด Enter/blur เพื่อบันทึก (เรียก onRenameBookmark) หรือกด Escape เพื่อยกเลิก
 *
 * แก้บั๊กรอบตรวจแถบหน้าเอกสาร/บุ๊กมาร์ก:
 * - เลื่อน/ลากย้ายหน้าแล้ว selection ค้างที่ตำแหน่งเดิม (จำนวนหน้าไม่เปลี่ยน จึงไม่ถูกล้าง) — กด "เลื่อนหน้าลง"
 *   ซ้ำครั้งที่ 2 กลายเป็นย้ายหน้าอื่น · ตอนนี้ selection ย้ายตามหน้าที่ย้ายไป (utils/pageOrder.js)
 * - มือถือ: เลื่อนแผงด้วยนิ้วแล้วเมนูคลิกขวาเด้งขึ้นเอง (เบราว์เซอร์ยึด touch ไป scroll → ได้ pointercancel ไม่ใช่
 *   pointermove ตัวจับเวลากดค้างเลยไม่ถูกยกเลิก) — ฟัง pointercancel ด้วย, กดค้างเปิดเมนูเฉพาะนิ้ว/ปากกา
 * - หน้าที่กำลังดูเลื่อนเข้ามาในแผงเอง (เดิมเลื่อนเอกสารไปหน้า 30 แผงยังค้างหน้า 1)
 * - ลบทุกหน้าไม่ได้ (เมนูปิดไว้ + backend กัน) · ปุ่มแก้ชื่อ/ลบบุ๊กมาร์กแสดงบนจอสัมผัส (เดิมโผล่เฉพาะตอน hover)
 * - บุ๊กมาร์กหลายชั้นแสดงย่อหน้าตามชั้น
 */
const SIDEBAR_MIN_WIDTH = 160;
const SIDEBAR_MAX_WIDTH = 480;
const SIDEBAR_DEFAULT_WIDTH = 232;
const SIDEBAR_COLLAPSED_WIDTH = 32;

export default function Sidebar({
  pageCount,
  currentPage,
  thumbnails,
  onSelectPage,
  bookmarks,
  onAddBookmark,
  onRemoveBookmark,
  onRenameBookmark,
  onExportPages,
  onExportPagesAsImage,
  onReorderPages,
  onMovePages,
  onDeletePages,
  onRotatePages,
  isOpenOnMobile,
  onCloseMobile,
}) {
  const [tab, setTab] = useState("pages");
  const [selectedPages, setSelectedPages] = useState(() => new Set());
  const [lastClickedPage, setLastClickedPage] = useState(null);
  const [contextMenu, setContextMenu] = useState(null); // { x, y } | null
  const [reorderDrag, setReorderDrag] = useState(null); // { movingPages: number[], dropBeforePage: number|null } | null
  const [width, setWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [collapsed, setCollapsed] = useState(false);
  const [renamingBookmarkId, setRenamingBookmarkId] = useState(null);
  const [renameDraft, setRenameDraft] = useState("");
  // โหมดเลือกหลายหน้า (มือถือไม่มี Ctrl/Shift) — แตะหน้า = เลือก/เลิกเลือก ไม่กระโดดหน้า · เข้าจากเมนูกดค้าง/คลิกขวา
  const [selectMode, setSelectMode] = useState(false);

  const listRef = useRef(null);
  const scrollRef = useRef(null); // .sidebar-body — element ที่ overflow-y:auto จริง (scroll ต้องแก้ที่นี่ ไม่ใช่ .thumbnail-list)
  const didDragRef = useRef(false);
  const menuRef = useRef(null);
  const ghostRef = useRef(null);
  const longPressTimerRef = useRef(null);
  const lastPointerTypeRef = useRef("mouse"); // นิ้ว/ปากกา: เมนูมาจากตัวจับเวลากดค้าง ไม่ใช่ contextmenu ของเบราว์เซอร์

  // เอกสารเปลี่ยน (เปิดไฟล์ใหม่/จำนวนหน้าเปลี่ยน — รวมถึงหลังลากสลับตำแหน่งหน้าสำเร็จ) — เคลียร์
  // selection เดิมทิ้ง กันเลือกหน้าที่ไม่มีอยู่แล้ว/อ้างอิงตำแหน่งเก่าที่ไม่ตรงแล้ว
  useEffect(() => {
    setSelectedPages(new Set());
    setLastClickedPage(null);
    setContextMenu(null);
    setRenamingBookmarkId(null);
    setSelectMode(false);
  }, [pageCount]);

  // Esc ออกจากโหมดเลือกหลายหน้า (เมนูเปิดอยู่: ปิดเมนูก่อน)
  useEffect(() => {
    if (!selectMode) return undefined;
    function onKey(e) {
      if (e.key !== "Escape" || contextMenu) return;
      e.stopPropagation();
      exitSelectMode();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [selectMode, contextMenu]); // eslint-disable-line react-hooks/exhaustive-deps

  function exitSelectMode() {
    setSelectMode(false);
    setContextMenu(null);
    setSelectedPages(new Set(currentPage != null ? [currentPage] : []));
  }

  function enterSelectMode() {
    setSelectMode(true);
    setContextMenu(null);
  }

  // หน้าที่กำลังดูอยู่เลื่อนเข้ามาในแผงเสมอ (เปลี่ยนหน้าจากเอกสาร/แป้นพิมพ์/ค้นหา)
  useEffect(() => {
    if (tab !== "pages" || reorderDrag) return;
    const el = listRef.current?.querySelector(`[data-page-num="${currentPage}"]`);
    el?.scrollIntoView?.({ block: "nearest" });
  }, [currentPage, tab, pageCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // ย้ายหน้า (ลาก/เลื่อนขึ้นลง) สำเร็จ → selection ตามหน้าที่ย้ายไปตำแหน่งใหม่
  function followMovedPages(result, pages, opts) {
    Promise.resolve(result).then((ok) => {
      if (!ok) return;
      const next = newPositions(reorderedPages(pageCount, pages, opts), pages);
      setSelectedPages(new Set(next));
      setLastClickedPage(next[0] ?? null);
    });
  }

  // ปิดเมนูคลิกขวาเมื่อคลิกนอกเมนู หรือกด Escape (ดู pattern เดียวกับ MenuBar.jsx)
  useEffect(() => {
    if (!contextMenu) return undefined;
    function onDocClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setContextMenu(null);
      }
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setContextMenu(null);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [contextMenu]);

  // ลากขอบขวาแผงเพื่อปรับความกว้าง (ผู้ใช้แจ้งขอ) — pattern pointerdown+window pointermove/up เดียวกับ
  // การลากอื่นๆ ในไฟล์นี้ ระหว่างลากปิด text selection ทั้งหน้าไว้ก่อน (กันลากผ่านข้อความอื่นแล้วเบราว์
  // เซอร์ดันไปเลือกข้อความให้ generic แทน) แล้วค่อยคืนตอนปล่อยเมาส์
  function handleResizeStart(e) {
    if (e.button !== 0) return;
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = width;
    document.body.classList.add("no-select");
    function onMove(ev) {
      const next = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, startWidth + (ev.clientX - startX)));
      setWidth(next);
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.classList.remove("no-select");
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  // ---------- เปลี่ยนชื่อ bookmark (ผู้ใช้แจ้งขอ) ----------
  function startRenameBookmark(bm) {
    setRenamingBookmarkId(bm.id);
    setRenameDraft(bm.label);
  }
  function commitRenameBookmark() {
    const trimmed = renameDraft.trim();
    if (renamingBookmarkId != null && trimmed) {
      onRenameBookmark?.(renamingBookmarkId, trimmed);
    }
    setRenamingBookmarkId(null);
  }
  function cancelRenameBookmark() {
    setRenamingBookmarkId(null);
  }

  // หาว่าตำแหน่งเมาส์ปัจจุบัน (clientY) อยู่ใกล้ thumbnail ไหนที่สุด แล้วควร "แทรกก่อนหน้าไหน" —
  // เทียบกับจุดกึ่งกลาง (แนวตั้ง) ของแต่ละ thumbnail ที่ render อยู่จริงตอนนี้ คืน null แปลว่าวางท้ายสุด
  function computeDropTargetPage(clientY) {
    if (!listRef.current) return null;
    const items = listRef.current.querySelectorAll(".thumbnail-item");
    for (const item of items) {
      const r = item.getBoundingClientRect();
      if (clientY < r.top + r.height / 2) {
        return Number(item.dataset.pageNum);
      }
    }
    return null;
  }

  function handleListPointerDown(e) {
    if (e.button !== 0 || !listRef.current || !scrollRef.current) return; // ลากด้วยปุ่มซ้ายเท่านั้น
    const list = listRef.current;
    const scrollEl = scrollRef.current; // .sidebar-body — ตัวจริงที่มี overflow-y:auto (ดูหมายเหตุ scrollRef ด้านบน)
    const startY = e.clientY;
    const startScrollTop = scrollEl.scrollTop;
    let dragging = false;

    function onMove(ev) {
      const dy = ev.clientY - startY;
      if (!dragging && Math.abs(dy) > 6) {
        dragging = true;
        didDragRef.current = true;
        list.classList.add("dragging");
      }
      if (dragging) {
        scrollEl.scrollTop = startScrollTop - dy;
      }
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      list.classList.remove("dragging");
      // didDragRef ไม่ reset "ทันที" ตรงนี้ตั้งใจ — ถ้าปล่อยเมาส์อยู่บน thumbnail เดียวกับที่เริ่มลาก
      // เบราว์เซอร์จะยิง click ตามมาทันที (synchronous ในทริกเดียวกัน) ต้องปล่อยให้ onClick ของ
      // thumbnail นั้นเป็นคน "เช็คแล้วเคลียร์" เองก่อน (ดูหมายเหตุหัวไฟล์) — แต่ถ้าลากข้ามไปปล่อยที่
      // thumbnail อื่น (คนละ element กับตอนกดลง) เบราว์เซอร์จะ "ไม่" ยิง click ให้เลยสักตัว (พฤติกรรม
      // มาตรฐาน) ทำให้ didDragRef ค้างเป็น true ตลอดไปและไปกลืน click ถัดไปที่ไม่เกี่ยวข้องโดยไม่ตั้งใจ
      // จึงตั้ง setTimeout(0) ไว้เคลียร์ทิ้งเป็น fallback เสมอ — click แบบ synchronous (ถ้ามี) จะยิง
      // ก่อน timeout นี้ทำงานแน่นอน (มา macrotask หลัง) จึงยังกลืน click นั้นได้ทันเวลาเหมือนเดิม
      if (dragging) {
        setTimeout(() => {
          didDragRef.current = false;
        }, 0);
      }
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  // กดเมาส์ค้างที่ thumbnail หนึ่งอันแล้วลาก -> ย้ายตำแหน่งหน้าจริงในเอกสาร (ผู้ใช้แจ้งขอ) แยกจาก
  // handleListPointerDown ด้านบนโดยสิ้นเชิง (คนละท่าทาง) — stopPropagation กันไม่ให้ทั้งสองทำงานพร้อมกัน
  function handleThumbnailPointerDown(e, pageNum) {
    if (e.button !== 0 || !listRef.current || !scrollRef.current) return;
    e.stopPropagation();
    lastPointerTypeRef.current = e.pointerType;
    const scrollEl = scrollRef.current;
    const startX = e.clientX;
    const startY = e.clientY;
    let dragging = false;
    let longPressed = false;

    // กดค้าง = เปิดเมนู (แทนคลิกขวา) เฉพาะนิ้ว/ปากกา — เมาส์ใช้คลิกขวาอยู่แล้ว
    clearTimeout(longPressTimerRef.current);
    if (e.pointerType !== "mouse") {
      longPressTimerRef.current = setTimeout(() => {
        if (!dragging) {
          longPressed = true;
          didDragRef.current = true; // กลืน click ที่ตามมาตอนยกนิ้ว ไม่ให้ล้าง selection/กระโดดหน้า
          window.getSelection?.()?.removeAllRanges(); // เผื่อเบราว์เซอร์เริ่มเลือกข้อความไปแล้ว
          navigator.vibrate?.(10); // สั่นสั้นๆ ให้รู้ว่ากดค้างติดแล้ว (Android — iOS ไม่รองรับ เงียบไป)
          // เมนูวางเยื้องจากนิ้ว ไม่ให้นิ้วบังรายการแรก (keepInViewport ดันกลับเข้าจอถ้าล้น)
          handleThumbnailContextMenu({ preventDefault: () => {}, clientX: startX + 12, clientY: startY + 12 }, pageNum);
        }
      }, 500);
    }

    // หน้าที่จะย้าย: ถ้าหน้าที่กดลงอยู่ใน multi-select เดิมอยู่แล้ว ย้ายทั้งกลุ่มไปด้วยกัน ไม่ใช่แค่หน้าเดียว
    const movingPages = selectedPages.has(pageNum) && selectedPages.size > 1
      ? Array.from(selectedPages).sort((a, b) => a - b)
      : [pageNum];

    function onMove(ev) {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (!dragging && Math.hypot(dx, dy) > 6) {
        if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
        
        // บนมือถือ (touch) การลาก = การเลื่อนหน้าจอ (Scroll) ไม่ใช่การสลับหน้า (Reorder)
        if (e.pointerType === 'mouse') {
          dragging = true;
          didDragRef.current = true;
          setReorderDrag({ movingPages, dropBeforePage: computeDropTargetPage(ev.clientY) });
          if (ghostRef.current) {
            ghostRef.current.style.display = 'block';
          }
        }
      }
      if (!dragging) return;

      if (ghostRef.current) {
        // Offset by half of thumbnail width/height (60px, 80px) to center on cursor
        ghostRef.current.style.transform = `translate(${ev.clientX - 60}px, ${ev.clientY - 80}px)`;
      }

      // auto-scroll ตอนลากเมาส์เข้าใกล้ขอบบน/ล่างของแผงหน้าเอกสาร (เผื่อเอกสารยาวเกินจอ)
      const rect = scrollEl.getBoundingClientRect();
      if (ev.clientY < rect.top + 40) scrollEl.scrollTop -= 14;
      else if (ev.clientY > rect.bottom - 40) scrollEl.scrollTop += 14;

      const nextDrop = computeDropTargetPage(ev.clientY);
      setReorderDrag((prev) => {
        if (prev && prev.dropBeforePage === nextDrop) return prev; // ไม่มีอะไรเปลี่ยน ไม่ re-render ซ้ำ
        return { movingPages, dropBeforePage: nextDrop };
      });
    }
    function onUp(ev) {
      if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      if (ghostRef.current) ghostRef.current.style.display = 'none';
      if (longPressed) setTimeout(() => { didDragRef.current = false; }, 0);
      if (dragging && ev.type === "pointercancel") {
        setReorderDrag(null);
        setTimeout(() => { didDragRef.current = false; }, 0);
      } else if (dragging) {
        const dropBeforePage = computeDropTargetPage(ev.clientY);
        setReorderDrag(null);
        followMovedPages(onReorderPages?.(movingPages, dropBeforePage), movingPages, { targetPage: dropBeforePage });
        // ดูหมายเหตุ setTimeout(0) เดียวกับ handleListPointerDown ด้านบน — เผื่อลากข้าม thumbnail
        // คนละอันแล้วเบราว์เซอร์ไม่ยิง click ตามมาให้เคลียร์ flag เอง
        setTimeout(() => {
          didDragRef.current = false;
        }, 0);
      }
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  function handleListBackgroundClick(e) {
    if (didDragRef.current) {
      didDragRef.current = false;
      return;
    }
    if (e.target === listRef.current) {
      setSelectedPages(new Set());
      setLastClickedPage(null);
    }
  }

  function handleThumbnailClick(e, pageNum) {
    if (didDragRef.current) {
      didDragRef.current = false;
      return; // เพิ่งลาก (เลื่อนจอ หรือ สลับตำแหน่งหน้า) ไม่ใช่ตั้งใจคลิก — ไม่กระโดดหน้า/ไม่แก้ selection
    }
    if (selectMode || e.ctrlKey || e.metaKey) {
      setSelectedPages((prev) => {
        const next = new Set(prev);
        if (next.has(pageNum)) next.delete(pageNum);
        else next.add(pageNum);
        return next;
      });
      setLastClickedPage(pageNum);
      return;
    }
    if (e.shiftKey && lastClickedPage !== null) {
      const lo = Math.min(lastClickedPage, pageNum);
      const hi = Math.max(lastClickedPage, pageNum);
      const range = new Set();
      for (let i = lo; i <= hi; i++) range.add(i);
      setSelectedPages(range);
      onSelectPage(pageNum);
      return;
    }
    // คลิกธรรมดา — พฤติกรรมเดิม: กระโดดไปหน้านั้น และล้าง multi-select ก่อนหน้าทิ้ง
    setSelectedPages(new Set([pageNum]));
    setLastClickedPage(pageNum);
    onSelectPage(pageNum);
  }

  // เมนูคลิกขวาต้องอยู่ในหน้าจอเสมอ (ดู utils/viewport.js)
  useLayoutEffect(() => {
    if (contextMenu) keepInViewport(menuRef.current);
  }, [contextMenu]);

  function handleThumbnailContextMenu(e, pageNum) {
    e.preventDefault(); // แทนที่เมนูคลิกขวาเริ่มต้นของเบราว์เซอร์ด้วยเมนูของแอปเอง (ผู้ใช้แจ้งขอ)
    setSelectedPages((prev) => {
      if (prev.has(pageNum) && prev.size > 1) return prev; // คลิกขวาบนหน้าที่อยู่ใน selection หลายหน้าอยู่แล้ว — คงไว้ทั้งหมด
      if (selectMode) return new Set([...prev, pageNum]); // โหมดเลือกหลายหน้า: เพิ่มหน้านี้เข้าไป ไม่ล้างที่เลือกไว้
      return new Set([pageNum]);
    });
    setLastClickedPage(pageNum);
    setContextMenu({ x: e.clientX, y: e.clientY });
  }

  function handleExportImageClick(format) {
    const pages = Array.from(selectedPages).sort((a, b) => a - b);
    setContextMenu(null);
    if (pages.length > 0) onExportPagesAsImage?.(pages, format);
  }

  function handleExportClick() {
    const pages = Array.from(selectedPages).sort((a, b) => a - b);
    setContextMenu(null);
    if (pages.length > 0) onExportPages?.(pages);
  }

  // เลื่อนหน้าที่เลือกขึ้น/ลงทีละ 1 ตำแหน่ง (สลับกับหน้าที่อยู่ติดกัน) — ผู้ใช้แจ้งขอเพิ่มจากเมนูคลิกขวา
  // (ดู backend pdf_service.reorder_pages โหมด direction) ใช้ selectedPages ชุดเดียวกับปุ่มส่งออกด้านบน
  function handleMoveClick(direction) {
    const pages = Array.from(selectedPages).sort((a, b) => a - b);
    setContextMenu(null);
    if (pages.length > 0) followMovedPages(onMovePages?.(pages, direction), pages, { direction });
  }

  const multiSelectActive = selectedPages.size > 1 || selectMode;
  const hasSelection = selectedPages.size > 0;
  const sortedSelected = Array.from(selectedPages).sort((a, b) => a - b);
  // เลื่อนขึ้นไม่ได้อีกแล้วก็ต่อเมื่อหน้าที่เลือกอยู่ต้นสุดของเอกสารพอดี (index 0) — เลื่อนลงไม่ได้อีกแล้ว
  // ก็ต่อเมื่อหน้าสุดท้ายที่เลือกอยู่ท้ายสุดของเอกสารพอดี (ไม่ว่ากลุ่มที่เลือกจะติดกันหรือไม่ก็ตาม)
  const canMoveUp = sortedSelected.length > 0 && sortedSelected[0] > 0;
  function openSelectionMenu(e) {
    const r = e.currentTarget.getBoundingClientRect();
    setContextMenu({ x: r.left, y: r.bottom + 4 });
  }
  const canMoveDown = sortedSelected.length > 0 && sortedSelected[sortedSelected.length - 1] < pageCount - 1;
  const canDelete = selectedPages.size > 0 && selectedPages.size < pageCount; // ต้องเหลืออย่างน้อย 1 หน้า

  // ยุบแผงไว้ (ผู้ใช้แจ้งขอ "ซ่อนแถบได้") — เหลือแถบบางๆ ไว้เสมอ ไม่ซ่อนหายไปทั้งหมด ไม่งั้นจะไม่มีทาง
  // กดขยายกลับมาได้อีก (ปุ่มขยายต้องมีที่อยู่ให้กดเสมอ)
  if (collapsed) {
    return (
      <>
        {isOpenOnMobile && <div className="fixed inset-0 bg-black/20 z-10 desk:hidden" onClick={onCloseMobile} />}
        <div className={`flex flex-col bg-slate-50 border-r border-slate-200 relative shrink-0 transition-all z-20 ${isOpenOnMobile ? "absolute inset-y-0 left-0 shadow-2xl h-full" : "hidden desk:flex"}`} style={{ width: SIDEBAR_COLLAPSED_WIDTH }}>
          <button className="w-full p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-200 transition-colors font-bold text-lg" title="ขยายแผงหน้าเอกสาร" onClick={() => setCollapsed(false)}>
            »
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      {isOpenOnMobile && <div className="fixed inset-0 bg-black/20 z-10 desk:hidden" onClick={onCloseMobile} />}
      {/* กดค้างบนมือถือ = เมนูของแอป — ปิดการเลือกข้อความ/เมนู "คัดลอก ค้นดู" ของ iOS ทั้งแผง (เดิมขึ้นซ้อนกับเมนูของแอป
          และเลือกคำว่า "บุ๊คมาร์ค" ค้างไว้) · ช่องเปลี่ยนชื่อบุ๊คมาร์คคืน select-text */}
      <div className={`flex flex-col bg-slate-50 border-r border-slate-200 relative shrink-0 transition-all z-20 select-none [-webkit-touch-callout:none] ${isOpenOnMobile ? "absolute inset-y-0 left-0 shadow-2xl h-full" : "hidden desk:flex"}`} style={{ width }} data-testid="page-sidebar">
        <div className="flex items-center px-2 py-1 bg-slate-100 border-b border-slate-200 gap-1 shrink-0">
        <button
          className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition-colors ${tab === "pages" ? "bg-white text-sky-600 border border-slate-200 border-b-0" : "text-slate-500 hover:text-slate-700 hover:bg-slate-200"}`}
          onClick={() => setTab("pages")}
        >
          หน้าเอกสาร
        </button>
        <button
          className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition-colors ${tab === "bookmarks" ? "bg-white text-sky-600 border border-slate-200 border-b-0" : "text-slate-500 hover:text-slate-700 hover:bg-slate-200"}`}
          onClick={() => setTab("bookmarks")}
        >
          บุ๊คมาร์ค
        </button>
        <button className="ml-auto p-1 px-2 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded transition-colors text-lg leading-none" title="ซ่อนแผงหน้าเอกสาร" onClick={() => setCollapsed(true)}>
          «
        </button>
      </div>

      {selectMode && tab === "pages" && (
        <div className="flex items-center gap-1 px-2 py-1.5 bg-sky-50 border-b border-sky-200 shrink-0 text-xs" data-testid="select-mode-bar">
          <span className="font-semibold text-sky-800 mr-auto whitespace-nowrap" aria-live="polite">เลือก {selectedPages.size} หน้า</span>
          <button className="px-2 py-1.5 rounded text-sky-700 hover:bg-sky-100 whitespace-nowrap"
            onClick={() => setSelectedPages(selectedPages.size === pageCount ? new Set() : new Set(Array.from({ length: pageCount }, (_, i) => i)))}>
            {selectedPages.size === pageCount ? "ล้าง" : "ทั้งหมด"}
          </button>
          <button className="px-2 py-1.5 rounded bg-sky-600 text-white font-medium hover:bg-sky-700 disabled:opacity-40 whitespace-nowrap"
            disabled={!hasSelection} onClick={openSelectionMenu}>
            จัดการ ▾
          </button>
          <button className="px-2 py-1.5 rounded text-slate-600 hover:bg-slate-200 whitespace-nowrap" onClick={exitSelectMode}>เสร็จ</button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto bg-slate-50 p-3" ref={scrollRef}>
        {tab === "pages" && (
          <div
            className={`flex flex-col gap-4 ${reorderDrag ? "opacity-80" : ""}`}
            ref={listRef}
            onPointerDown={handleListPointerDown}
            onClick={handleListBackgroundClick}
            onContextMenu={(e) => e.preventDefault()}
          >
            {pageCount === 0 && <div className="text-center text-slate-400 text-xs mt-10">ยังไม่มีเอกสาร</div>}
            {Array.from({ length: pageCount }, (_, i) => i).map((pageNum, idx) => {
              const isSelected = multiSelectActive && selectedPages.has(pageNum);
              const isDraggingSource = !!reorderDrag && reorderDrag.movingPages.includes(pageNum);
              const isDropBefore = !!reorderDrag && reorderDrag.dropBeforePage === pageNum;
              const isDropAfter = !!reorderDrag && reorderDrag.dropBeforePage === null && idx === pageCount - 1;
              const classes = [
                "thumbnail-item group relative flex flex-col items-center gap-1.5 p-1 rounded-xl transition-all cursor-pointer border-2",
                pageNum === currentPage ? "border-sky-400 bg-sky-50 shadow-md" : "border-transparent hover:bg-slate-200",
                isSelected ? "!border-sky-500 ring-2 ring-sky-200 bg-sky-100" : "",
                isDraggingSource ? "opacity-30 scale-95" : "",
                isDropBefore ? "border-t-4 border-t-sky-500 rounded-none !border-l-0 !border-r-0 !border-b-0 mt-2 pt-2" : "",
                isDropAfter ? "border-b-4 border-b-sky-500 rounded-none !border-l-0 !border-r-0 !border-t-0 mb-2 pb-2" : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <button
                  key={pageNum}
                  className={classes}
                  data-page-num={pageNum}
                  onPointerDown={(e) => handleThumbnailPointerDown(e, pageNum)}
                  onClick={(e) => handleThumbnailClick(e, pageNum)}
                  onContextMenu={(e) => {
                    // Android ยิง contextmenu ตอนกดค้างด้วย — เปิดซ้ำกับตัวจับเวลาและวางเมนูใต้นิ้ว
                    if (lastPointerTypeRef.current !== "mouse") { e.preventDefault(); return; }
                    handleThumbnailContextMenu(e, pageNum);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Delete" || e.key === "Backspace") {
                      e.preventDefault();
                      e.stopPropagation();
                      if (canDelete) onDeletePages(Array.from(selectedPages));
                    }
                  }}
                >
                  {/* กรอบหน้ากระดาษพอดีกับรูป (หน้าแนวนอนเป็นกรอบแนวนอน) — เดิมกรอบตั้งตายตัว 120x160 หน้าที่หมุนแล้ว
                      เลยดูเหมือนหน้าแนวตั้งที่มีแค่ข้อความหมุน */}
                  <div className="w-[120px] h-[160px] flex items-center justify-center">
                    <div className="relative bg-white border border-slate-300 shadow-sm rounded overflow-visible">
                      {thumbnails[pageNum] ? (
                        <img
                          src={pageImageSrc(thumbnails[pageNum])}
                          alt={`หน้า ${pageNum + 1}`}
                          className="ios-no-callout block w-auto h-auto max-w-[118px] max-h-[158px] rounded"
                          draggable={false}
                        />
                      ) : (
                        <div className="w-[118px] h-[158px] bg-slate-100 animate-pulse" />
                      )}
                      {isSelected && <span className="absolute -top-2 -right-2 bg-sky-500 text-white w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shadow-md z-10">✓</span>}
                      {selectMode && !isSelected && <span className="absolute -top-2 -right-2 bg-white border-2 border-slate-300 w-6 h-6 rounded-full shadow-sm z-10" aria-hidden="true" />}
                    </div>
                  </div>
                  <span className="text-xs font-medium text-slate-500 group-hover:text-slate-800">{pageNum + 1}</span>
                </button>
              );
            })}
          </div>
        )}

        {tab === "bookmarks" && (
          <div className="flex flex-col gap-1">
            <button
              className="w-full py-1.5 px-2 bg-white border border-slate-300 rounded text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-sky-600 transition-colors mb-4 shadow-sm"
              onClick={onAddBookmark}
              disabled={pageCount === 0}
            >
              + เพิ่มที่คั่นหน้าหน้านี้
            </button>
            {bookmarks.length === 0 && <div className="text-center text-slate-400 text-xs mt-10">ยังไม่มีบุ๊คมาร์ค</div>}
            {bookmarks.map((bm) => {
              const isRenaming = renamingBookmarkId === bm.id;
              return (
                <div key={bm.id} data-testid="bookmark-item"
                  style={{ paddingLeft: 8 + Math.min((bm.level || 1) - 1, 6) * 12 }}
                  className={`flex items-center gap-2 pr-2 py-1.5 rounded-md group transition-colors ${bm.page === currentPage ? "bg-sky-100" : "hover:bg-slate-200"}`}>
                  {isRenaming ? (
                    <input
                      autoFocus
                      maxLength={300}
                      aria-label="ชื่อบุ๊คมาร์ค"
                      className="flex-1 w-full text-xs px-2 py-1 border border-sky-400 rounded focus:outline-none focus:ring-1 focus:ring-sky-500 select-text [-webkit-touch-callout:default]"
                      value={renameDraft}
                      onChange={(e) => setRenameDraft(e.target.value)}
                      onBlur={commitRenameBookmark}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRenameBookmark();
                        else if (e.key === "Escape") cancelRenameBookmark();
                      }}
                    />
                  ) : (
                    <button
                      className="flex-1 flex items-center gap-2 overflow-hidden text-left focus:outline-none"
                      onClick={() => onSelectPage(bm.page)}
                      onDoubleClick={() => startRenameBookmark(bm)}
                      title={bm.label}
                    >
                      <span className="text-[10px]">🔖</span>
                      <span className="text-xs font-medium text-slate-700 truncate">{bm.label}</span>
                      <span className="text-[10px] text-slate-400 shrink-0 ml-auto">หน้า {bm.page + 1}</span>
                    </button>
                  )}
                  {!isRenaming && (
                    <button
                      className="opacity-0 group-hover:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100 p-1 text-slate-400 hover:text-sky-600 transition-opacity text-[10px]"
                      title="เปลี่ยนชื่อบุ๊คมาร์ค"
                      onClick={() => startRenameBookmark(bm)}
                    >
                      ✎
                    </button>
                  )}
                  <button
                    className="opacity-0 group-hover:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-opacity text-sm leading-none"
                    title="ลบบุ๊คมาร์ค"
                    onClick={() => onRemoveBookmark(bm.id)}
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {contextMenu && (
        <div
          className="fixed bg-white border border-slate-200 shadow-xl rounded-lg py-1 min-w-[180px] z-[100] text-sm overflow-hidden select-none [-webkit-touch-callout:none] [&_button]:[@media(pointer:coarse)]:py-2.5"
          ref={menuRef}
          style={{ left: contextMenu.x, top: contextMenu.y }}
          role="menu"
        >
          {!selectMode && (
            <>
              <button
                className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none"
                role="menuitem"
                onClick={enterSelectMode}
              >
                ☑ เลือกหลายหน้า
              </button>
              <div className="h-px bg-slate-200 my-1 mx-2" />
            </>
          )}
          <button
            className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none disabled:opacity-40 disabled:hover:bg-transparent"
            role="menuitem"
            disabled={!canMoveUp}
            onClick={() => handleMoveClick("up")}
          >
            เลื่อนหน้าขึ้น{selectedPages.size > 1 ? ` (${selectedPages.size} หน้า)` : ""}
          </button>
          <button
            className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none disabled:opacity-40 disabled:hover:bg-transparent"
            role="menuitem"
            disabled={!canMoveDown}
            onClick={() => handleMoveClick("down")}
          >
            เลื่อนหน้าลง{selectedPages.size > 1 ? ` (${selectedPages.size} หน้า)` : ""}
          </button>
          <div className="h-px bg-slate-200 my-1 mx-2" />
          <button
            className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none disabled:opacity-40 disabled:hover:bg-transparent"
            role="menuitem"
            disabled={!hasSelection}
            onClick={() => { onRotatePages(Array.from(selectedPages), 90); setContextMenu(null); }}
          >
            หมุนขวา ↻ (90°){selectedPages.size > 1 ? ` (${selectedPages.size} หน้า)` : ""}
          </button>
          <button
            className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none disabled:opacity-40 disabled:hover:bg-transparent"
            role="menuitem"
            disabled={!hasSelection}
            onClick={() => { onRotatePages(Array.from(selectedPages), -90); setContextMenu(null); }}
          >
            หมุนซ้าย ↺ (-90°){selectedPages.size > 1 ? ` (${selectedPages.size} หน้า)` : ""}
          </button>
          <div className="h-px bg-slate-200 my-1 mx-2" />
          <button
            className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none disabled:opacity-40 disabled:hover:bg-transparent"
            role="menuitem"
            style={{ color: "var(--color-danger, #ef4444)" }}
            disabled={!canDelete}
            title={canDelete ? undefined : "ลบทุกหน้าไม่ได้ — เอกสารต้องเหลืออย่างน้อย 1 หน้า"}
            onClick={() => { onDeletePages(Array.from(selectedPages)); setContextMenu(null); }}
          >
            {selectedPages.size > 1 ? "ลบหน้าที่เลือก" : "ลบหน้านี้ทิ้ง"}{selectedPages.size > 1 ? ` (${selectedPages.size} หน้า)` : ""}
          </button>
          <div className="h-px bg-slate-200 my-1 mx-2" />
          <button
            className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none disabled:opacity-40 disabled:hover:bg-transparent"
            role="menuitem"
            disabled={!hasSelection}
            onClick={handleExportClick}
          >
            ส่งออกหน้าที่เลือกเป็นไฟล์ใหม่{selectedPages.size > 0 ? ` (${selectedPages.size} หน้า)` : ""}
          </button>
          {["png", "jpg"].map((fmt) => (
            <button
              key={fmt}
              className="w-full text-left px-4 py-1.5 text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none disabled:opacity-40 disabled:hover:bg-transparent"
              role="menuitem"
              disabled={!hasSelection}
              onClick={() => handleExportImageClick(fmt)}
            >
              ส่งออกเป็นรูปภาพ {fmt.toUpperCase()}{selectedPages.size > 1 ? ` (${selectedPages.size} หน้า .zip)` : ""}
            </button>
          ))}
        </div>
      )}

      <div className="absolute top-0 right-0 w-1.5 h-full cursor-col-resize hover:bg-sky-400/50 transition-colors z-30" onPointerDown={handleResizeStart} title="ลากเพื่อปรับความกว้าง" />

      {/* Ghost element for dragging */}
      <div 
        ref={ghostRef} 
        className="fixed top-0 left-0 pointer-events-none z-[200] opacity-90 scale-105 hidden"
        style={{ willChange: "transform" }}
      >
        {reorderDrag && reorderDrag.movingPages.map((p, i) => (
          <div 
            key={p} 
            className="absolute top-0 left-0 w-[120px] h-[160px] bg-white border border-sky-400 shadow-2xl rounded flex items-center justify-center overflow-hidden"
            style={{ 
              transform: `translate(${i * 6}px, ${i * 6}px)`,
              zIndex: reorderDrag.movingPages.length - i
            }}
          >
            {thumbnails[p] ? (
              <img src={pageImageSrc(thumbnails[p])} alt="ghost" className="w-full h-full object-contain ios-no-callout" />
            ) : (
              <div className="w-full h-full bg-slate-100" />
            )}
            {reorderDrag.movingPages.length > 1 && i === 0 && (
              <div className="absolute -top-2 -right-2 bg-sky-500 text-white text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center shadow-md">
                {reorderDrag.movingPages.length}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
    </>
  );
}
