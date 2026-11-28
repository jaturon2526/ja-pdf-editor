// เลิกทำ/ทำซ้ำ และงานที่เปลี่ยนเนื้อเอกสาร (ย้าย/ลบ/หมุนหน้า, ลดขนาด, รวมเลเยอร์, ลายน้ำ) — แยกมาจาก Editor.jsx
// ทุกงานในนี้จบด้วยขั้นตอนเดียวกัน: เปิดปุ่ม Undo, ล้าง draft ที่ค้าง แล้วรีเฟรชหน้า/ข้อมูลประกอบ
import { useRef } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";
import { reorderedPages } from "../utils/pageOrder.js";

// เครื่องมือที่ไม่มี draft ค้าง (อ่านข้อมูลใหม่จากหน้าเอง) — undo/redo แล้วยังเปิดอยู่ แก้/ดูต่อได้
const TOOLS_KEPT_ON_HISTORY = new Set(["edit_table", "edit_barcode", "inspect_font", "fill_form"]);

export function useDocumentHistory({
  session,
  setSession,
  currentPage,
  setCurrentPage,
  zoom,
  editMode,
  sessionHook,
  textEditHook,
  imageEditHook,
  annotationHook,
  signatureHook,
  redactHook,
  activeTool,
  setActiveTool,
  setCanUndo,
  setCanRedo,
  setStatusMessage,
}) {
  const { t } = useI18n();
  const historyBusyRef = useRef(false); // กันกด Ctrl+Z / Ctrl+Y รัวซ้อนกันระหว่างรอคำตอบ

  // ล้าง draft + pending ทุกชนิดทิ้ง (ใช้หลัง undo/redo/ย้ายหน้า — state ค้างไม่ valid แล้ว)
  function resetTransientEditState({ keepTool = false } = {}) {
    if (!keepTool) setActiveTool(null);
    textEditHook.reset();
    imageEditHook.reset();
    annotationHook.reset();
    signatureHook.reset();
    if (redactHook) redactHook.reset();
  }

  // รีเฟรชรูปหน้า + ข้อมูลที่เกี่ยวข้องกับ editMode หลัง undo/redo/ย้ายหน้า
  // nextPage: หน้าที่ควรแสดงหลังเปลี่ยน (เช่น ย้ายหน้าที่กำลังดูอยู่ → ตามไปตำแหน่งใหม่)
  async function refreshAfterHistoryChange(nextPage = null) {
    if (!session) return;

    let targetPage = nextPage ?? currentPage;
    if (nextPage != null && nextPage !== currentPage) setCurrentPage(nextPage);
    try {
      const info = await api.getInfo(session.sessionId);
      setSession((s) =>
        s
          ? {
              ...s,
              pageCount: info.page_count,
              pageSizes: info.page_sizes,
              isPasswordProtected: !!info.is_password_protected,
              isSigned: !!info.is_signed,
              signatureType: info.signature_type || null,
            }
          : s
      );
      if (typeof info.can_undo === "boolean") setCanUndo(info.can_undo);
      if (typeof info.can_redo === "boolean") setCanRedo(info.can_redo);
      if (targetPage >= info.page_count) {
        targetPage = Math.max(0, info.page_count - 1);
        setCurrentPage(targetPage);
      }
    } catch {
      /* ignore */
    }

    sessionHook.setThumbnails({}); // undo/redo อาจกระทบหน้าอื่น — รีโหลดทุก thumbnail

    // ยิงโหลด bookmark, ภาพหน้าปัจจุบัน, และข้อมูลตามโหมดแก้ไขพร้อมกัน (Promise.all) ให้ตอบสนองเร็วขึ้น
    const loadBookmarks = api
      .getBookmarks(session.sessionId)
      .then((bm) => {
        sessionHook.setBookmarks((prev) =>
          bm.bookmarks.map((b, i) => ({ ...b, id: prev[i]?.id ?? `${Date.now()}-${i}` }))
        );
      })
      .catch(() => { /* ignore */ });

    const loadPage = api
      .renderPage(session.sessionId, targetPage, zoom)
      .then((data) => sessionHook.setPageImage(data.image_base64))
      .catch((err) => setStatusMessage(t("editor.hooks.history.refreshPageFailed", { error: err.message })));

    let loadModeData;
    if (editMode === "text") {
      loadModeData = api
        .getTextBlocks(session.sessionId, targetPage)
        .then((blocks) => textEditHook.setTextBlocks(blocks))
        .catch(() => { /* ignore */ });
    } else if (editMode === "image") {
      loadModeData = api
        .getImages(session.sessionId, targetPage)
        .then((imgs) => imageEditHook.setImages(imgs))
        .catch(() => { /* ignore */ });
    } else {
      loadModeData = annotationHook.refreshAnnotations();
    }

    await Promise.all([loadBookmarks, loadPage, loadModeData]);
  }

  function tryUndoPendingEdit() {
    if (editMode === "redact" && redactHook?.undoLastPending?.()) return true;
    if (editMode === "text" && textEditHook?.undoLastPending?.()) return true;
    if (editMode === "image" && imageEditHook?.undoLastPending?.()) return true;
    return false;
  }

  async function undoOrRedo(kind) {
    if (!session || historyBusyRef.current) return;
    const isUndo = kind === "undo";
    if (isUndo && tryUndoPendingEdit()) {
      setStatusMessage(t("editor.hooks.history.pendingEditUndone"));
      return;
    }
    historyBusyRef.current = true;
    try {
      const res = await (isUndo ? api.undo : api.redo)(session.sessionId);
      setCanUndo(res.can_undo);
      setCanRedo(res.can_redo);
      // undo/redo อาจข้ามจุดที่เซ็น — อัปเดตสถานะเซ็นตามนั้น
      setSession((s) => (s ? { ...s, isSigned: res.is_signed, signatureType: res.signature_type } : s));
      if (res.status === (isUndo ? "nothing_to_undo" : "nothing_to_redo")) {
        setStatusMessage(
          isUndo ? t("editor.hooks.history.nothingToUndo") : t("editor.hooks.history.nothingToRedo")
        );
        return;
      }
      resetTransientEditState({ keepTool: TOOLS_KEPT_ON_HISTORY.has(activeTool) });
      await refreshAfterHistoryChange();
      setStatusMessage(
        isUndo ? t("editor.hooks.history.undoSuccess") : t("editor.hooks.history.redoSuccess")
      );
    } catch (err) {
      setStatusMessage(
        isUndo
          ? t("editor.hooks.history.undoFailed", { error: err.message })
          : t("editor.hooks.history.redoFailed", { error: err.message })
      );
    } finally {
      historyBusyRef.current = false;
    }
  }

  // งานที่แก้เอกสารฝั่ง server แล้วต้อง: เปิด Undo + ล้าง draft + รีเฟรช
  // action(sessionId) คืน response ของ API — status "no_change" = ไม่มีอะไรเปลี่ยน (แสดง noChange ถ้ามี)
  // success เป็นข้อความ หรือฟังก์ชัน (res) => ข้อความ ก็ได้ (เช่น แสดงขนาดไฟล์ก่อน/หลัง)
  // คืน true เมื่อเอกสารเปลี่ยนจริง (แผงหน้าเอกสารใช้ย้าย selection ตามหน้าที่ย้าย)
  async function runDocumentChange(action, { busy, success, failure, noChange, nextPage = null, rethrow = false, keepTool = false } = {}) {
    if (!session) return false;
    if (busy) setStatusMessage(busy);
    try {
      const res = await action(session.sessionId);
      if (res?.status === "no_change") {
        if (noChange) setStatusMessage(noChange);
        return false;
      }
      setCanUndo(true);
      setCanRedo(false);
      resetTransientEditState({ keepTool });
      await refreshAfterHistoryChange(typeof nextPage === "function" ? nextPage() : nextPage);
      setStatusMessage(typeof success === "function" ? success(res) : success);
      return true;
    } catch (err) {
      setStatusMessage(`${failure}: ${err.message}`);
      if (rethrow) throw err; // หน้าต่างที่เรียก (เช่น แทรกหน้า) แสดงข้อความเองและยังไม่ปิด
      return false;
    }
  }

  const plural = (pages, manyKey, oneKey) =>
    pages.length > 1 ? t(manyKey, { count: pages.length }) : t(oneKey);
  const hasPages = (pages) => session && pages && pages.length > 0;

  const pageOps = {
    reorder(pageNumbers, targetPage) {
      if (!hasPages(pageNumbers)) return;
      const order = reorderedPages(session.pageCount, pageNumbers, { targetPage });
      return runDocumentChange((sid) => api.reorderPages(sid, pageNumbers, { targetPage }), {
        nextPage: order.indexOf(currentPage),
        success: plural(
          pageNumbers,
          "editor.hooks.history.reorderManySuccess",
          "editor.hooks.history.reorderOneSuccess"
        ),
        failure: t("editor.hooks.history.reorderFailed"),
      });
    },
    remove(pageNumbers) {
      if (!hasPages(pageNumbers)) return;
      return runDocumentChange((sid) => api.deletePages(sid, pageNumbers), {
        success: plural(
          pageNumbers,
          "editor.hooks.history.deleteManySuccess",
          "editor.hooks.history.deleteOneSuccess"
        ),
        failure: t("editor.hooks.history.deleteFailed"),
      });
    },
    rotate(pageNumbers, angle) {
      if (!hasPages(pageNumbers)) return;
      return runDocumentChange((sid) => api.rotatePages(sid, pageNumbers, angle), {
        success: plural(
          pageNumbers,
          "editor.hooks.history.rotateManySuccess",
          "editor.hooks.history.rotateOneSuccess"
        ),
        failure: t("editor.hooks.history.rotateFailed"),
      });
    },
    // แทรกหน้า (v1.39.0): body = { position, source_session_id, pages } | { position, blank } — ไปที่หน้าแรกที่แทรก
    insert(body) {
      if (!session) return false;
      return runDocumentChange((sid) => api.insertPages(sid, body), {
        busy: t("editor.hooks.history.insertBusy"),
        nextPage: body.position,
        success: (res) =>
          res.flattened_fields
            ? t("editor.hooks.history.insertSuccessWithFlattened", {
                count: res.inserted,
                flattened: res.flattened_fields,
              })
            : t("editor.hooks.history.insertSuccess", { count: res.inserted }),
        failure: t("editor.hooks.history.insertFailed"),
        rethrow: true,
      });
    },
    move(pageNumbers, direction) {
      if (!hasPages(pageNumbers)) return;
      const up = direction === "up";
      const order = reorderedPages(session.pageCount, pageNumbers, { direction });
      return runDocumentChange((sid) => api.reorderPages(sid, pageNumbers, { direction }), {
        nextPage: order.indexOf(currentPage),
        success: up ? t("editor.hooks.history.moveUpSuccess") : t("editor.hooks.history.moveDownSuccess"),
        failure: t("editor.hooks.history.moveFailed"),
        noChange: up ? t("editor.hooks.history.moveUpNoChange") : t("editor.hooks.history.moveDownNoChange"),
      });
    },
  };

  return {
    resetTransientEditState,
    refreshAfterHistoryChange,
    handleUndo: () => undoOrRedo("undo"),
    handleRedo: () => undoOrRedo("redo"),
    runDocumentChange,
    pageOps,
  };
}
