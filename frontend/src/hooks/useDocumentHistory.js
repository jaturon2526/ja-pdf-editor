// เลิกทำ/ทำซ้ำ และงานที่เปลี่ยนเนื้อเอกสาร (ย้าย/ลบ/หมุนหน้า, ลดขนาด, รวมเลเยอร์, ลายน้ำ) — แยกมาจาก Editor.jsx
// ทุกงานในนี้จบด้วยขั้นตอนเดียวกัน: เปิดปุ่ม Undo, ล้าง draft ที่ค้าง แล้วรีเฟรชหน้า/ข้อมูลประกอบ
import * as api from "../api.js";
import { reorderedPages } from "../utils/pageOrder.js";

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
  setActiveTool,
  setCanUndo,
  setCanRedo,
  setStatusMessage,
}) {
  // ล้าง draft + pending ทุกชนิดทิ้ง (ใช้หลัง undo/redo/ย้ายหน้า — state ค้างไม่ valid แล้ว)
  function resetTransientEditState() {
    setActiveTool(null);
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
      if (targetPage >= info.page_count) {
        targetPage = Math.max(0, info.page_count - 1);
        setCurrentPage(targetPage);
      }
    } catch {
      /* ignore */
    }

    sessionHook.setThumbnails({}); // undo/redo อาจกระทบหน้าอื่น — รีโหลดทุก thumbnail
    // bookmark ผูกกับ TOC จริง — undo/redo/reorder อาจเปลี่ยนเลขหน้าอ้างอิง จึงดึงใหม่เสมอ
    try {
      const bm = await api.getBookmarks(session.sessionId);
      sessionHook.setBookmarks((prev) =>
        bm.bookmarks.map((b, i) => ({ ...b, id: prev[i]?.id ?? `${Date.now()}-${i}` }))
      );
    } catch {
      /* ignore */
    }
    try {
      const data = await api.renderPage(session.sessionId, targetPage, zoom);
      sessionHook.setPageImage(data.image_base64);
    } catch (err) {
      setStatusMessage(`รีเฟรชหน้าไม่สำเร็จ: ${err.message}`);
    }
    try {
      if (editMode === "text") {
        textEditHook.setTextBlocks(await api.getTextBlocks(session.sessionId, targetPage));
      } else if (editMode === "image") {
        imageEditHook.setImages(await api.getImages(session.sessionId, targetPage));
      }
    } catch {
      /* ignore */
    }
    if (editMode !== "text" && editMode !== "image") {
      await annotationHook.refreshAnnotations();
    }
  }

  async function undoOrRedo(kind) {
    if (!session) return;
    const isUndo = kind === "undo";
    const label = isUndo ? "เลิกทำ" : "ทำซ้ำ";
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
      resetTransientEditState();
      await refreshAfterHistoryChange();
      setStatusMessage(`${label} (${isUndo ? "Undo" : "Redo"}) สำเร็จ`);
    } catch (err) {
      setStatusMessage(`${label}ไม่สำเร็จ: ${err.message}`);
    }
  }

  // งานที่แก้เอกสารฝั่ง server แล้วต้อง: เปิด Undo + ล้าง draft + รีเฟรช
  // action(sessionId) คืน response ของ API — status "no_change" = ไม่มีอะไรเปลี่ยน (แสดง noChange ถ้ามี)
  // success เป็นข้อความ หรือฟังก์ชัน (res) => ข้อความ ก็ได้ (เช่น แสดงขนาดไฟล์ก่อน/หลัง)
  // คืน true เมื่อเอกสารเปลี่ยนจริง (แผงหน้าเอกสารใช้ย้าย selection ตามหน้าที่ย้าย)
  async function runDocumentChange(action, { busy, success, failure, noChange, nextPage = null } = {}) {
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
      resetTransientEditState();
      await refreshAfterHistoryChange(typeof nextPage === "function" ? nextPage() : nextPage);
      setStatusMessage(typeof success === "function" ? success(res) : success);
      return true;
    } catch (err) {
      setStatusMessage(`${failure}: ${err.message}`);
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
