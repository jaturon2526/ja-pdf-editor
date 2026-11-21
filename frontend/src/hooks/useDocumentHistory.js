// เลิกทำ/ทำซ้ำ และงานที่เปลี่ยนเนื้อเอกสาร (ย้าย/ลบ/หมุนหน้า, ลดขนาด, รวมเลเยอร์, ลายน้ำ) — แยกมาจาก Editor.jsx
// ทุกงานในนี้จบด้วยขั้นตอนเดียวกัน: เปิดปุ่ม Undo, ล้าง draft ที่ค้าง แล้วรีเฟรชหน้า/ข้อมูลประกอบ
import { useRef } from "react";
import * as api from "../api.js";
import { reorderedPages } from "../utils/pageOrder.js";

// เครื่องมือที่ไม่มี draft ค้าง (อ่านข้อมูลใหม่จากหน้าเอง) — undo/redo แล้วยังเปิดอยู่ แก้/ดูต่อได้
const TOOLS_KEPT_ON_HISTORY = new Set(["edit_table", "edit_barcode", "inspect_font"]);

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
      .catch((err) => setStatusMessage(`รีเฟรชหน้าไม่สำเร็จ: ${err.message}`));

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
      setStatusMessage("ยกเลิกรายการแก้ไขล่าสุดที่รอยืนยันแล้ว");
      return;
    }
    const label = isUndo ? "เลิกทำ" : "ทำซ้ำ";
    historyBusyRef.current = true;
    try {
      const res = await (isUndo ? api.undo : api.redo)(session.sessionId);
      setCanUndo(res.can_undo);
      setCanRedo(res.can_redo);
      // undo/redo อาจข้ามจุดที่เซ็น — อัปเดตสถานะเซ็นตามนั้น
      setSession((s) => (s ? { ...s, isSigned: res.is_signed, signatureType: res.signature_type } : s));
      if (res.status === (isUndo ? "nothing_to_undo" : "nothing_to_redo")) {
        setStatusMessage(isUndo ? "ไม่มีขั้นตอนก่อนหน้าให้เลิกทำแล้ว" : "ไม่มีขั้นตอนที่ทำซ้ำได้แล้ว");
        return;
      }
      resetTransientEditState({ keepTool: TOOLS_KEPT_ON_HISTORY.has(activeTool) });
      await refreshAfterHistoryChange();
      setStatusMessage(`${label} (${isUndo ? "Undo" : "Redo"}) สำเร็จ`);
    } catch (err) {
      setStatusMessage(`${label}ไม่สำเร็จ: ${err.message}`);
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

  const plural = (pages, many, one) => (pages.length > 1 ? `${many} ${pages.length} หน้าสำเร็จ` : one);
  const hasPages = (pages) => session && pages && pages.length > 0;

  const pageOps = {
    reorder(pageNumbers, targetPage) {
      if (!hasPages(pageNumbers)) return;
      const order = reorderedPages(session.pageCount, pageNumbers, { targetPage });
      return runDocumentChange((sid) => api.reorderPages(sid, pageNumbers, { targetPage }), {
        nextPage: order.indexOf(currentPage),
        success: plural(pageNumbers, "ย้ายหน้าที่เลือก", "ย้ายหน้าสำเร็จ"),
        failure: "ย้ายหน้าไม่สำเร็จ",
      });
    },
    remove(pageNumbers) {
      if (!hasPages(pageNumbers)) return;
      return runDocumentChange((sid) => api.deletePages(sid, pageNumbers), {
        success: plural(pageNumbers, "ลบหน้าที่เลือก", "ลบหน้าสำเร็จ"),
        failure: "ลบหน้าไม่สำเร็จ",
      });
    },
    rotate(pageNumbers, angle) {
      if (!hasPages(pageNumbers)) return;
      return runDocumentChange((sid) => api.rotatePages(sid, pageNumbers, angle), {
        success: plural(pageNumbers, "หมุนหน้าที่เลือก", "หมุนหน้าสำเร็จ"),
        failure: "หมุนหน้าไม่สำเร็จ",
      });
    },
    // แทรกหน้า (v1.39.0): body = { position, source_session_id, pages } | { position, blank } — ไปที่หน้าแรกที่แทรก
    insert(body) {
      if (!session) return false;
      return runDocumentChange((sid) => api.insertPages(sid, body), {
        busy: "กำลังแทรกหน้า...",
        nextPage: body.position,
        success: (res) => `แทรก ${res.inserted} หน้าแล้ว${res.flattened_fields
          ? ` · ช่องกรอกฟอร์ม ${res.flattened_fields} ช่องของไฟล์ที่แทรกกลายเป็นข้อความตายตัว` : ""}`,
        failure: "แทรกหน้าไม่สำเร็จ",
        rethrow: true,
      });
    },
    move(pageNumbers, direction) {
      if (!hasPages(pageNumbers)) return;
      const up = direction === "up";
      const order = reorderedPages(session.pageCount, pageNumbers, { direction });
      return runDocumentChange((sid) => api.reorderPages(sid, pageNumbers, { direction }), {
        nextPage: order.indexOf(currentPage),
        success: up ? "เลื่อนหน้าขึ้นสำเร็จ" : "เลื่อนหน้าลงสำเร็จ",
        failure: "เลื่อนหน้าไม่สำเร็จ",
        noChange: up ? "อยู่หน้าบนสุดแล้ว เลื่อนขึ้นต่อไม่ได้" : "อยู่หน้าล่างสุดแล้ว เลื่อนลงต่อไม่ได้",
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
