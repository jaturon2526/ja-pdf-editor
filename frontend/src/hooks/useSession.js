// useSession.js — จัดการ lifecycle ของ PDF session, page rendering, thumbnail, bookmarks

import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

/** เบราว์เซอร์ที่ต้องเปิด PDF ในแท็บใหม่เพื่อพิมพ์ (iPhone/iPad/Android/Safari — iframe ซ่อนพิมพ์ PDF ไม่ได้) */
export function printOpensNewTab() {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1); // iPadOS แจ้งเป็น Mac
  const android = /Android/.test(ua);
  const safari = /Safari/.test(ua) && !/Chrome|Chromium|CriOS|FxiOS|Edg|OPR|Android/.test(ua);
  return ios || android || safari;
}

const THUMBNAIL_ZOOM = 0.25;

/**
 * จัดการ session lifecycle ทั้งหมด:
 * - อัปโหลด/ปลดล็อก/ปิด session
 * - render หน้าเอกสาร (pageImage) + lazy thumbnail
 * - bookmarks
 * - password prompt state
 *
 * หมายเหตุ: closeDocument และ handleReorderPages/handleMovePages ถูกนิยามใน App.jsx
 * เพราะต้องรีเซ็ต state จาก hooks หลายตัวพร้อมกัน
 */
export function useSession({ zoom, setStatusMessage, setCanUndo, setCanRedo, onSaved }) {
  const { t } = useI18n();
  const fileInputRef = useRef(null);

  const [session, setSession] = useState(null); // { sessionId, filename, pageCount, pageSizes, ... }
  const [currentPage, setCurrentPage] = useState(0);
  const currentPageRef = useRef(0);
  currentPageRef.current = currentPage;
  const [pageImage, setPageImageRaw] = useState(null);
  const [pageImagePage, setPageImagePage] = useState(0);
  const setPageImage = useCallback((img, pageIdx = null) => {
    setPageImageRaw(img);
    if (img !== null) setPageImagePage(pageIdx ?? currentPageRef.current);
  }, []);
  const [pageLoading, setPageLoading] = useState(false);
  const [thumbnails, setThumbnails] = useState({});
  const [bookmarks, setBookmarks] = useState([]);
  const [passwordState, setPasswordState] = useState(null); // { sessionId, filename, error, submitting }

  // ---------- โหลดรูปหน้าปัจจุบันทุกครั้งที่ page/zoom/session เปลี่ยน ----------
  useEffect(() => {
    if (!session) return undefined;
    const ctrl = new AbortController();
    setPageLoading(true);
    api
      .renderPage(session.sessionId, currentPage, zoom, { signal: ctrl.signal })
      .then((data) => {
        if (!ctrl.signal.aborted) {
          setPageImageRaw(data.image_base64);
          setPageImagePage(currentPage);
        }
      })
      .catch((err) => {
        if (!ctrl.signal.aborted) setStatusMessage(t("editor.hooks.session.loadPageFailed", { message: err.message }));
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setPageLoading(false);
      });
    return () => {
      ctrl.abort();
    };
  }, [session, currentPage, zoom]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- โหลด thumbnail แบบ lazy ทีละหน้า ----------
  useEffect(() => {
    if (!session) return;
    const missing = Array.from({ length: session.pageCount }, (_, i) => i).find(
      (p) => thumbnails[p] === undefined
    );
    if (missing === undefined) return;
    let cancelled = false;
    api
      .renderPage(session.sessionId, missing, THUMBNAIL_ZOOM)
      .then((data) => {
        if (!cancelled) setThumbnails((prev) => ({ ...prev, [missing]: data.image_base64 }));
      })
      .catch(() => {
        if (!cancelled) setThumbnails((prev) => ({ ...prev, [missing]: null }));
      });
    return () => {
      cancelled = true;
    };
  }, [session, thumbnails]);

  // ---------- Helper functions ----------
  function currentPageSizePt() {
    return session?.pageSizes?.[currentPage] || [1, 1];
  }

  async function refreshCurrentPage(overrideZoom) {
    if (!session) return;
    const data = await api.renderPage(session.sessionId, currentPage, overrideZoom ?? zoom);
    setPageImage(data.image_base64);
  }

  function goToPage(p) {
    if (!session) return;
    const clamped = Math.max(0, Math.min(session.pageCount - 1, p));
    setCurrentPage(clamped);
  }

  // เลื่อนทีละหน้า (ปัดนิ้ว/เลื่อนเมาส์เกินขอบ) — อ่านหน้าล่าสุดจาก ref ไม่ใช่ค่าใน closure ของ render ก่อน
  // (ปัดติดกันเร็วๆ เดิมได้หน้าเดิมซ้ำ) · คืน false ถ้าเป็นหน้าแรก/หน้าสุดท้ายแล้ว
  function stepPage(delta) {
    if (!session) return false;
    const target = currentPageRef.current + delta;
    if (target < 0 || target >= session.pageCount) return false;
    currentPageRef.current = target;
    setCurrentPage(target);
    return true;
  }

  function openFileDialog() {
    fileInputRef.current?.click();
  }

  // ---------- activateSession — เปิดใช้งาน session ที่ upload/unlock สำเร็จแล้ว ----------
  // onActivate: callback จาก App.jsx ใช้รีเซ็ต state ของ hooks อื่นๆ (text/image/annotation/signature)
  // ก่อน activate session ใหม่ (ป้องกัน state ของเอกสารเก่าค้าง)
  async function _activateSession(sessionId, filename, pageCount, onActivate) {
    if (onActivate) onActivate();

    const info = await api.getInfo(sessionId);
    const actualFilename = filename || info.filename || "Document.pdf";
    const actualPageCount = pageCount ?? info.page_count;
    
    setSession({
      sessionId,
      filename: actualFilename,
      pageCount: actualPageCount,
      pageSizes: info.page_sizes,
      isPasswordProtected: !!info.is_password_protected,
      isSigned: !!info.is_signed,
      signatureType: info.signature_type || null,
    });
    setCurrentPage(0);
    setThumbnails({});

    // อ่าน bookmark จาก PDF outline/TOC จริง (แก้บั๊ก bookmark หายหลังดาวน์โหลดแล้วเปิดใหม่)
    try {
      const bm = await api.getBookmarks(sessionId);
      setBookmarks(bm.bookmarks.map((b, i) => ({ ...b, id: `${Date.now()}-${i}` })));
    } catch {
      setBookmarks([]);
    }

    setCanUndo(!!info.can_undo);
    setCanRedo(!!info.can_redo);
    setStatusMessage(
      t("editor.hooks.session.openSuccess", { filename: actualFilename, pageCount: actualPageCount })
    );
  }

  // ---------- handleFileSelected — รับไฟล์จาก input หรือ drag-drop ----------
  // resetCallback: App.jsx ส่งมาให้ใช้รีเซ็ต state ของ hooks อื่นๆ ก่อนเปิดเอกสารใหม่
  const handleFileSelected = useCallback(async (file, resetCallback) => {
    if (!file) return;
    setStatusMessage(t("editor.hooks.session.uploading", { filename: file.name }));
    try {
      let res;
      const officeExts = [".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".rtf", ".odt", ".ods", ".odp"];
      if (officeExts.some(ext => file.name.toLowerCase().endsWith(ext))) {
        setStatusMessage(t("editor.hooks.session.convertingOffice"));
        res = await api.uploadOffice(file);
      } else {
        res = await api.uploadPdf(file);
      }
      if (res.status === "password_required") {
        setPasswordState({
          sessionId: res.session_id,
          filename: res.filename,
          error: null,
          submitting: false,
        });
        return;
      }
      await _activateSession(res.session_id, res.filename, res.page_count, resetCallback);
    } catch (err) {
      setStatusMessage(t("editor.hooks.session.openFailed", { message: err.message }));
    }
  }, [t]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleUnlockSubmit(password, resetCallback) {
    if (!passwordState) return;
    setPasswordState((s) => ({ ...s, submitting: true, error: null }));
    try {
      const res = await api.unlockPdf(passwordState.sessionId, password);
      if (res.status === "invalid_password") {
        setPasswordState((s) => ({ ...s, submitting: false, error: t("editor.hooks.session.invalidPassword") }));
        return;
      }
      await _activateSession(passwordState.sessionId, passwordState.filename, res.page_count, resetCallback);
      setPasswordState(null);
    } catch (err) {
      setPasswordState((s) => ({ ...s, submitting: false, error: err.message }));
    }
  }

  function handleUnlockCancel() {
    if (passwordState) api.closeSession(passwordState.sessionId).catch(() => {});
    setPasswordState(null);
  }

  // ดาวน์โหลด/พิมพ์ไม่บันทึกทับไฟล์ในเอกสารของฉันอีกต่อไป — เดิมบันทึกทับให้เองเงียบ ๆ: เซ็นเซอร์ข้อมูลเพื่อส่งต่อ
  // แล้วกดดาวน์โหลด ไฟล์ต้นฉบับในบัญชีถูกเซ็นเซอร์ถาวรไปด้วย (บันทึกเมื่อกด ไฟล์ → บันทึก / Ctrl+S เท่านั้น)
  async function handleDownload() {
    if (!session) return;
    try {
      await api.downloadPdf(session.sessionId);
    } catch (err) {
      setStatusMessage(t("editor.hooks.session.downloadFailed", { message: err.message }));
    }
  }

  // layout: "auto" = ไฟล์ปกติ (เครื่องพิมพ์หมุนหน้าแนวนอนเอง), "as_shown" = ตามที่เห็นบนจอ
  // targetWindow: แท็บว่างที่เปิดไว้ตอนกด (มือถือ/Safari — ดู printOpensNewTab) เปิดหลัง await ไม่ได้ เบราว์เซอร์บล็อก popup
  async function handlePrint({ layout = "auto", targetWindow = null } = {}) {
    if (!session) return;
    setStatusMessage(t("editor.hooks.session.preparingPrint"));
    try {
      // ไฟล์สำหรับพิมพ์ไม่เข้ารหัสเสมอ (เดิม "auto" ใช้ไฟล์ดาวน์โหลด — ถ้าตั้งรหัสผ่านไว้ หน้าต่างพิมพ์ขึ้นช่องรหัสผ่าน
      // ที่มองไม่เห็น) และรวมไฮไลต์/กล่องข้อความลงหน้าแล้ว
      const { blob, filename } = await api.fetchPrintBlob(session.sessionId, layout === "as_shown" ? "as_shown" : "auto");
      const blobUrl = URL.createObjectURL(blob);

      if (targetWindow || printOpensNewTab()) {
        // มือถือ / Safari: พิมพ์ PDF จาก iframe ซ่อนไม่ได้ (ได้หน้าว่าง) — เปิดไฟล์ในแท็บใหม่ให้พิมพ์จากเบราว์เซอร์
        // เดิมเรียก window.open หลังโหลดไฟล์เสร็จ iPhone บล็อกเงียบๆ แต่ขึ้นว่า "เปิดเรียบร้อยแล้ว"
        if (targetWindow && !targetWindow.closed) {
          targetWindow.location.href = blobUrl;
          setStatusMessage(t("editor.hooks.session.printOpenedInTab"));
          setTimeout(() => URL.revokeObjectURL(blobUrl), 120000);
          return "tab";
        } else {
          api.saveBlob(blob, filename || "print.pdf");
          setStatusMessage(t("editor.hooks.session.printPopupBlocked"));
        }
        setTimeout(() => URL.revokeObjectURL(blobUrl), 120000);
        return;
      }

      // สร้าง iframe ซ่อนสำหรับสั่งพิมพ์
      let iframe = document.getElementById("pdf-print-iframe");
      if (iframe) {
        try { document.body.removeChild(iframe); } catch (_) {}
      }
      iframe = document.createElement("iframe");
      iframe.id = "pdf-print-iframe";
      iframe.style.position = "fixed";
      iframe.style.right = "0";
      iframe.style.bottom = "0";
      iframe.style.width = "0";
      iframe.style.height = "0";
      iframe.style.border = "0";
      iframe.style.zIndex = "-1";
      iframe.src = blobUrl;

      document.body.appendChild(iframe);

      let printed = false;
      const triggerPrint = () => {
        if (printed) return;
        printed = true;
        try {
          iframe.contentWindow.focus();
          iframe.contentWindow.print();
          setStatusMessage(t("editor.hooks.session.printDialogOpened"));
        } catch (err) {
          console.warn("Direct iframe print failed, falling back to window.open:", err);
          if (!window.open(blobUrl, "_blank")) api.saveBlob(blob, filename || "print.pdf");
        } finally {
          setTimeout(() => {
            try {
              if (document.body.contains(iframe)) {
                document.body.removeChild(iframe);
              }
              URL.revokeObjectURL(blobUrl);
            } catch (_) {}
          }, 60000);
        }
      };

      iframe.onload = () => {
        setTimeout(triggerPrint, 500);
      };

      // Fallback กรณี onload ไม่ยิง — เดิม 2.5 วินาที ไฟล์ใหญ่ยังโหลดไม่เสร็จ ได้หน้าต่างพิมพ์ว่าง/ไม่ครบ
      setTimeout(() => {
        if (!printed && iframe && iframe.parentNode) {
          triggerPrint();
        }
      }, 8000);
    } catch (err) {
      console.error("Print error:", err);
      if (targetWindow && !targetWindow.closed) targetWindow.close();
      setStatusMessage(t("editor.hooks.session.printFailed", { message: err.message }));
    }
  }

  async function handleSaveToServer() {
    if (!session) return;
    setStatusMessage(t("editor.hooks.session.saving"));
    try {
      await api.saveToServer(session.sessionId);
      onSaved?.();
      setStatusMessage(t("editor.hooks.session.saveSuccess"));
    } catch (err) {
      setStatusMessage(t("editor.hooks.session.saveFailed", { message: err.message }));
    }
  }

  async function handleExportPages(pageNumbers) {
    if (!session || !pageNumbers || pageNumbers.length === 0) return;
    try {
      await api.exportPages(session.sessionId, pageNumbers);
    } catch (err) {
      setStatusMessage(t("editor.hooks.session.exportPagesFailed", { message: err.message }));
    }
  }

  // ---------- Bookmarks ----------
  // ทุกการเปลี่ยนแปลง (เพิ่ม/ลบ/เปลี่ยนชื่อ) ส่งรายการทั้งชุดไปเขียนทับ PDF outline/TOC จริง
  // backend เขียนสำเร็จแล้วยัง push_history() ให้ด้วย จึง undo/redo ย้อน bookmark กลับได้
  async function commitBookmarks(nextList) {
    if (!session) return;
    try {
      const res = await api.setBookmarks(
        session.sessionId,
        nextList.map(({ page, label, level, ref }) => ({ page, label, level: level ?? null, ref: ref ?? null }))
      );
      setBookmarks(
        res.bookmarks.map((b, i) => ({ ...b, id: nextList[i]?.id ?? `${Date.now()}-${i}` }))
      );
      setCanUndo(true);
      setCanRedo(false);
    } catch (err) {
      setStatusMessage(t("editor.hooks.session.saveBookmarksFailed", { message: err.message }));
    }
  }

  // แทรกตามลำดับหน้า (เดิมต่อท้ายเสมอ — บุ๊กมาร์กหน้า 2 ที่เพิ่มทีหลังไปอยู่ใต้หน้า 10) เป็นชั้นบนสุด
  function addBookmark() {
    const at = bookmarks.findIndex((b) => b.page > currentPage);
    const item = {
      id: `${Date.now()}`,
      page: currentPage,
      label: t("editor.hooks.session.defaultBookmarkLabel", { page: currentPage + 1 }),
      level: 1,
    };
    const next = [...bookmarks];
    next.splice(at === -1 ? next.length : at, 0, item);
    void commitBookmarks(next);
  }

  function removeBookmark(id) {
    void commitBookmarks(bookmarks.filter((b) => b.id !== id));
  }

  function renameBookmark(id, label) {
    void commitBookmarks(bookmarks.map((b) => (b.id === id ? { ...b, label } : b)));
  }

  return {
    // state
    session,
    setSession,
    currentPage,
    setCurrentPage,
    pageImage,
    pageImagePage,
    setPageImage,
    pageLoading,
    thumbnails,
    setThumbnails,
    bookmarks,
    setBookmarks,
    passwordState,
    setPasswordState,
    // refs
    fileInputRef,
    // handlers
    handleFileSelected,
    handleUnlockSubmit,
    handleUnlockCancel,
    handleDownload,
    handlePrint,
    stepPage,
    handleSaveToServer,
    handleExportPages,
    // navigation
    goToPage,
    // helpers
    openFileDialog,
    refreshCurrentPage,
    currentPageSizePt,
    // bookmarks
    commitBookmarks,
    addBookmark,
    removeBookmark,
    renameBookmark,
    // internal (ใช้จาก App.jsx เพื่อ activate หลังปลดล็อก)
    _activateSession,
  };
}
