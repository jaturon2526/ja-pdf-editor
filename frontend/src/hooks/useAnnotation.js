// useAnnotation.js — จัดการ annotation ทุกชนิด (highlight, freetext, rect, text_note)

import { useEffect, useState, useRef } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";
import { hexToRgb01, rgb01ToHex } from "../utils/textEditUtils.js";
import { computeSelectedLineRects, unionRects } from "../utils/textSelectionUtils.js";

const EDITABLE_ANNOTATION_TYPES = ["highlight", "rect", "freetext", "text_note"];
// ระยะทางลากที่ถือว่า "แทบไม่ได้ลาก" (คลิกเฉยๆ) — fallback เป็นกล่องขนาด default
const MIN_DRAG_PT = 3;

export function useAnnotation({ session, currentPage, editMode, zoom, fonts, setStatusMessage }) {
  const { t } = useI18n();
  const [annotations, setAnnotations] = useState([]);
  const [annotationDraft, setAnnotationDraft] = useState(null);
  const [pendingAnnotation, setPendingAnnotation] = useState(null); // {rect, type} — รอผู้ใช้พิมพ์ข้อความ

  // โหลด annotation ของหน้าปัจจุบัน (เฉพาะตอน editMode === null — โหมด select/annotation)
  useEffect(() => {
    setAnnotationDraft(null);
    if (!session || editMode) {
      setAnnotations([]);
      return;
    }
    let cancelled = false;
    api
      .listAnnotations(session.sessionId, currentPage)
      .then((list) => {
        if (!cancelled)
          setAnnotations(list.filter((a) => EDITABLE_ANNOTATION_TYPES.includes(a.type)));
      })
      .catch((err) => !cancelled && setStatusMessage(t("editor.hooks.annotation.loadFailed", { error: err.message })));
    return () => {
      cancelled = true;
    };
  }, [session, currentPage, editMode, t]); // eslint-disable-line react-hooks/exhaustive-deps

  async function refreshAnnotations() {
    if (!session || editMode) return;
    try {
      const list = await api.listAnnotations(session.sessionId, currentPage);
      setAnnotations(list.filter((a) => EDITABLE_ANNOTATION_TYPES.includes(a.type)));
    } catch (err) {
      setStatusMessage(t("editor.hooks.annotation.loadFailed", { error: err.message }));
    }
  }

  // ---------- วาง annotation ใหม่ด้วยการลากเมาส์ ----------
  // 4 ชนิด: highlight, freetext, rect, text_note — แต่ละชนิดมีพฤติกรรมต่างกัน
  async function handleAnnotationDrag(tool, rectPt) {
    if (!session) return;
    const isTinyDrag = rectPt.x1 - rectPt.x0 < MIN_DRAG_PT && rectPt.y1 - rectPt.y0 < MIN_DRAG_PT;

    if (tool === "rect") {
      const rect = isTinyDrag
        ? { x0: rectPt.x0, y0: rectPt.y0, x1: rectPt.x0 + 120, y1: rectPt.y0 + 24 }
        : rectPt;
      
      // ผู้ใช้ต้องการให้วาดเสร็จทันที ไม่ต้องมีหน้าต่าง popup กดยืนยัน (สร้างลง PDF เลย)
      try {
        await api.addAnnotation(session.sessionId, {
          page_number: currentPage,
          type: "rect",
          rect: rect,
          color: [0.9, 0.57, 0.1], // สีส้มค่าเริ่มต้น (#E69119)
        });
        const data = await api.renderPage(session.sessionId, currentPage, zoom);
        _onPageRendered(data.image_base64, currentPage);
        await refreshAnnotations();
        _onHistoryChange(true, false);
        setStatusMessage(t("editor.hooks.annotation.rectCreated"));
      } catch (err) {
        setStatusMessage(t("editor.hooks.annotation.rectCreateFailed", { error: err.message }));
      }
      return;
    }

    if (tool === "freetext") {
      const rect = isTinyDrag
        ? { x0: rectPt.x0, y0: rectPt.y0, x1: rectPt.x0 + 160, y1: rectPt.y0 + 40 }
        : rectPt;
      // คลิกวางเฉยๆ (ไม่ลากขนาด): server ปรับความสูงกรอบให้พอดีกับข้อความ — ลากขยายต่อทีหลังได้
      setPendingAnnotation({ rect, type: "freetext", autoHeight: isTinyDrag });
      return;
    }

    // highlight / text_note: ต้องเลือกข้อความจริงใต้บริเวณที่ลาก (snap คำ/บรรทัด)
    let words;
    try {
      words = await api.getWords(session.sessionId, currentPage);
    } catch (err) {
      setStatusMessage(t("editor.hooks.annotation.loadWordsFailed", { error: err.message }));
      return;
    }
    const lineRects = computeSelectedLineRects(words, rectPt);

    if (tool === "highlight") {
      if (lineRects.length === 0) {
        setStatusMessage(t("editor.hooks.annotation.noTextInSelection"));
        return;
      }
      try {
        // ไฮไลต์เดียวหลายบรรทัด — Undo ครั้งเดียวหายทั้งหมด (เดิมสร้างทีละบรรทัด ต้อง Undo ทีละบรรทัด)
        await api.addAnnotation(session.sessionId, {
          page_number: currentPage,
          type: "highlight",
          rect: unionRects(lineRects),
          line_rects: lineRects,
          color: [1, 0.92, 0.3],
        });
        const data = await api.renderPage(session.sessionId, currentPage, zoom);
        // setPageImage จะถูกเรียกผ่าน App.jsx ไม่ใช่ hook นี้ — คืน data กลับไปแทน
        _onPageRendered(data.image_base64, currentPage);
        await refreshAnnotations();
        _onHistoryChange(true, false);
        setStatusMessage(
          lineRects.length > 1
            ? t("editor.hooks.annotation.highlightCreatedMulti", { count: lineRects.length })
            : t("editor.hooks.annotation.highlightCreated")
        );
      } catch (err) {
        setStatusMessage(t("editor.hooks.annotation.highlightFailed", { error: err.message }));
      }
      return;
    }

    // text_note: ยึดตำแหน่งที่กรอบรวมของข้อความที่เลือกได้
    const anchorRect = unionRects(lineRects) || {
      x0: rectPt.x0,
      y0: rectPt.y0,
      x1: rectPt.x0 + 20,
      y1: rectPt.y0 + 20,
    };
    setPendingAnnotation({ rect: anchorRect, type: "text_note" });
  }

  // ฟังก์ชัน callback สำหรับส่งผลกลับไปยัง App.jsx (หน้า render ใหม่, undo/redo state)
  // ถูก override โดย App.jsx ผ่าน setCallbacks()
  const callbacksRef = useRef({
    onPageRendered: () => {},
    onHistoryChange: () => {}
  });

  function setCallbacks({ onPageRendered, onHistoryChange }) {
    if (onPageRendered) callbacksRef.current.onPageRendered = onPageRendered;
    if (onHistoryChange) callbacksRef.current.onHistoryChange = onHistoryChange;
  }
  
  const _onPageRendered = (img, page) => callbacksRef.current.onPageRendered(img, page);
  const _onHistoryChange = (canUndo, canRedo) => callbacksRef.current.onHistoryChange(canUndo, canRedo);

  // สร้าง annotation ใหม่จาก pendingAnnotation (หลังผู้ใช้พิมพ์ข้อความแล้ว)
  async function createAnnotation(type, rect, content, autoHeight = false) {
    if (!session) return;
    try {
      await api.addAnnotation(session.sessionId, {
        page_number: currentPage,
        type,
        rect,
        content: content || undefined,
        color: type === "highlight" ? [1, 0.92, 0.3] : undefined,
        auto_height: autoHeight || undefined,
      });
      const data = await api.renderPage(session.sessionId, currentPage, zoom);
      _onPageRendered(data.image_base64, currentPage);
      await refreshAnnotations();
      _onHistoryChange(true, false);
      setStatusMessage(
        type === "text_note"
          ? t("editor.hooks.annotation.noteCreated")
          : t("editor.hooks.annotation.freetextCreated")
      );
    } catch (err) {
      setStatusMessage(
        type === "text_note"
          ? t("editor.hooks.annotation.noteCreateFailed", { error: err.message })
          : t("editor.hooks.annotation.freetextCreateFailed", { error: err.message })
      );
    }
  }

  function submitPendingAnnotation(text) {
    if (!pendingAnnotation) return;
    void createAnnotation(pendingAnnotation.type, pendingAnnotation.rect, text, pendingAnnotation.autoHeight);
    setPendingAnnotation(null);
  }

  // ---------- เลือก/แก้ไข annotation ที่มีอยู่แล้ว ----------
  function handleSelectAnnotation(annot) {
    const original = {
      rect: { ...annot.rect },
      content: annot.content || "",
      colorHex: rgb01ToHex(annot.color) || (annot.type === "highlight" ? "#ffe066" : "#1b2130"),
      fontKey: annot.fontname || fonts[0]?.key || "sarabun",
      fontSize: annot.fontsize || 12,
    };
    setAnnotationDraft({
      original,
      xref: annot.xref,
      pageNumber: annot.page_number,
      type: annot.type,
      rect: { ...annot.rect },
      content: annot.content || "",
      colorHex: rgb01ToHex(annot.color) || (annot.type === "highlight" ? "#ffe066" : "#1b2130"),
      fontKey: annot.fontname || fonts[0]?.key || "sarabun",
      fontSize: annot.fontsize || 12,
    });
  }

  function handleAnnotationDraftRectChange(rect) {
    setAnnotationDraft((d) => (d ? { ...d, rect } : d));
  }
  function handleAnnotationDraftContentChange(content) {
    setAnnotationDraft((d) => (d ? { ...d, content } : d));
  }
  function handleAnnotationDraftColorChange(colorHex) {
    setAnnotationDraft((d) => (d ? { ...d, colorHex } : d));
  }
  function handleAnnotationDraftFontKeyChange(fontKey) {
    setAnnotationDraft((d) => (d ? { ...d, fontKey } : d));
  }
  function handleAnnotationDraftFontSizeChange(fontSize) {
    setAnnotationDraft((d) => (d ? { ...d, fontSize } : d));
  }
  function handleCancelAnnotationEdit() {
    setAnnotationDraft(null);
  }

  // ส่งเฉพาะสิ่งที่เปลี่ยน — ไม่เปลี่ยนอะไรเลยไม่ต้องเรียก server (เดิมสร้าง Undo เปล่า ๆ ทุกครั้งที่กดตกลง)
  // และไฮไลต์หลายบรรทัดที่แค่เปลี่ยนสีจะไม่ถูกรวมเป็นกรอบเดียว (ส่ง rect = สร้างใหม่จากกรอบรวม)
  async function handleCommitAnnotationEdit() {
    if (!annotationDraft || !session) return;
    const { xref, pageNumber, type, rect, content, colorHex, fontKey, fontSize, original = {} } = annotationDraft;
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    const changes = {};
    if (!same(rect, original.rect)) changes.rect = rect;
    if (type !== "highlight" && content !== original.content) changes.content = content;
    if (colorHex !== original.colorHex) changes.color = hexToRgb01(colorHex);
    if (type === "freetext" && fontKey !== original.fontKey) changes.fontname = fontKey;
    if (type === "freetext" && fontSize !== original.fontSize) changes.fontsize = fontSize;
    if (Object.keys(changes).length === 0) {
      setAnnotationDraft(null);
      return;
    }
    try {
      await api.updateAnnotation(session.sessionId, { page_number: pageNumber, xref, ...changes });
      setAnnotationDraft(null);
      const data = await api.renderPage(session.sessionId, currentPage, zoom);
      _onPageRendered(data.image_base64, currentPage);
      await refreshAnnotations();
      _onHistoryChange(true, false);
      setStatusMessage(t("editor.hooks.annotation.updateSuccess"));
    } catch (err) {
      setStatusMessage(t("editor.hooks.annotation.updateFailed", { error: err.message }));
    }
  }

  async function handleMoveAnnotation(annot, rect) {
    if (!annot || !session) return;
    try {
      await api.updateAnnotation(session.sessionId, { page_number: annot.page_number, xref: annot.xref, rect });
      const data = await api.renderPage(session.sessionId, currentPage, zoom);
      _onPageRendered(data.image_base64, currentPage);
      await refreshAnnotations();
      _onHistoryChange(true, false);
      setStatusMessage(t("editor.hooks.annotation.moveNoteSuccess"));
    } catch (err) {
      setStatusMessage(t("editor.hooks.annotation.moveNoteFailed", { error: err.message }));
    }
  }

  async function handleDeleteAnnotation(target) {
    const item = target && typeof target.xref === "number"
      ? { pageNumber: target.page_number, xref: target.xref }
      : annotationDraft;
    if (!item || !session) return;
    try {
      await api.deleteAnnotation(session.sessionId, item.pageNumber, item.xref);
      if (annotationDraft?.xref === item.xref) setAnnotationDraft(null);
      const data = await api.renderPage(session.sessionId, currentPage, zoom);
      _onPageRendered(data.image_base64, currentPage);
      await refreshAnnotations();
      _onHistoryChange(true, false);
      setStatusMessage(t("editor.hooks.annotation.deleteSuccess"));
    } catch (err) {
      setStatusMessage(t("editor.hooks.annotation.deleteFailed", { error: err.message }));
    }
  }

  // รีเซ็ต draft + pendingAnnotation (ใช้ตอน undo/redo/เปลี่ยนเอกสาร)
  function reset() {
    setAnnotationDraft(null);
    setPendingAnnotation(null);
  }

  return {
    // state
    annotations,
    setAnnotations,
    annotationDraft,
    setAnnotationDraft,
    pendingAnnotation,
    setPendingAnnotation,
    // callbacks setup (เรียกจาก App.jsx ครั้งเดียวหลัง mount)
    setCallbacks,
    // handlers
    handleAnnotationDrag,
    handleSelectAnnotation,
    handleAnnotationDraftRectChange,
    handleAnnotationDraftContentChange,
    handleAnnotationDraftColorChange,
    handleAnnotationDraftFontKeyChange,
    handleAnnotationDraftFontSizeChange,
    handleCommitAnnotationEdit,
    handleCancelAnnotationEdit,
    handleMoveAnnotation,
    handleDeleteAnnotation,
    submitPendingAnnotation,
    refreshAnnotations,
    // cross-hook
    reset,
  };
}
