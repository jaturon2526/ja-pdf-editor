// useTextEdit.js — จัดการการแก้ไขข้อความใน PDF (text blocks, draft, pending edits)

import { useEffect, useState } from "react";
import * as api from "../api.js";
import { sampleBackgroundColor } from "../utils/bgSample.js";
import { colorIntToHex, guessDefaultFontKey } from "../utils/textEditUtils.js";

/**
 * จัดการ text editing workflow:
 * 1. โหลด text blocks ของหน้าปัจจุบัน (เมื่ออยู่ editMode="text")
 * 2. เลือกย่อหน้า → สร้าง draft → ผู้ใช้พิมพ์/ลาก
 * 3. กด "ตกลง" → ย้าย draft ไป pendingEdits (ยังไม่ยิง API)
 * 4. App.jsx เรียก handleApplyAllEdits → ยิง API จริงทีเดียว
 */
export function useTextEdit({
  session,
  currentPage,
  editMode,
  pageImgElRef,
  fonts,
  fontFamilies,
  setStatusMessage,
}) {
  const [textBlocks, setTextBlocks] = useState([]);
  const [draftEdit, setDraftEdit] = useState(null);
  const [pendingEdits, setPendingEdits] = useState({});
  const [textEditError, setTextEditError] = useState(null);
  const [applyingEdits, setApplyingEdits] = useState(false);

  // computed
  const textPendingCount = Object.values(pendingEdits).reduce(
    (s, m) => s + Object.keys(m).length,
    0
  );
  const pendingEditsForPage = pendingEdits[currentPage] || {};

  // โหลดย่อหน้าของหน้าปัจจุบันใหม่ทุกครั้งที่เข้าโหมดแก้ไขข้อความ หรือเปลี่ยนหน้า/เอกสาร
  useEffect(() => {
    setDraftEdit(null);
    setTextEditError(null);
    if (!session || editMode !== "text") {
      setTextBlocks([]);
      return;
    }
    let cancelled = false;
    api
      .getTextBlocks(session.sessionId, currentPage)
      .then((blocks) => !cancelled && setTextBlocks(blocks))
      .catch((err) => !cancelled && setStatusMessage(`โหลดข้อความไม่สำเร็จ: ${err.message}`));
    return () => {
      cancelled = true;
    };
  }, [session, currentPage, editMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // สุ่มสีพื้นหลังจากหน้าเอกสารจริงรอบๆ rect ที่ระบุ (ใช้ลาดพื้นกัน text เดิมโผล่ทะลุมาขณะ draft)
  function _sampleBgAt(rect, marginPt = 0) {
    const [w, h] = session?.pageSizes?.[currentPage] || [1, 1];
    return sampleBackgroundColor(pageImgElRef.current, w, h, rect, marginPt) || "#ffffff";
  }

  // คลิกย่อหน้าที่ \"ยังไม่เคย\" มีการแก้ไขค้างอยู่ — เปิด draft ใหม่ สุ่มสีพื้นหลังครั้งเดียวตอนเริ่ม
  function handleSelectTextBlock(block) {
    if (!session) return;

    // Backend ส่ง fontname ที่ match กับระบบมาให้แล้ว (ผ่าน fonts.match_pdf_font_name)
    // ยังคง fallback ไป guessDefaultFontKey() สำหรับ block เก่าที่อาจยังมีชื่อ raw PDF font
    const resolvedFontKey =
      block.fontname && fonts && fonts.some((f) => f.key === block.fontname)
        ? block.fontname
        : guessDefaultFontKey(block.fontname || "", fonts, fontFamilies);

    // อ่าน bold/italic จาก block ที่ backend ตรวจให้ แล้วเลือก style variant ที่ถูกต้อง
    const wantsBold   = block.is_bold   || false;
    const wantsItalic = block.is_italic || false;
    let styledFontKey = resolvedFontKey;
    if (wantsBold || wantsItalic) {
      // ถ้า resolvedFontKey ยังไม่มี style suffix ให้ลองเพิ่มให้ (backend อาจส่งมาพร้อมแล้วก็ได้)
      if (!resolvedFontKey.includes("-bold") && !resolvedFontKey.includes("-italic")) {
        const suffix = wantsBold && wantsItalic ? "-bolditalic" : wantsBold ? "-bold" : "-italic";
        const candidate = resolvedFontKey + suffix;
        if (fonts && fonts.some((f) => f.key === candidate)) {
          styledFontKey = candidate;
        }
      }
    }

    setDraftEdit({
      blockId: block.block_id,
      serverRect: { ...block.rect },
      rect: { ...block.rect },
      text: block.text,
      fontKey: styledFontKey,
      fontSize: block.fontsize || 12,
      colorHex: colorIntToHex(block.color),
      bgColor: _sampleBgAt(block.rect),
      align: block.align || "left",
      valign: block.valign || "top",
      underline: block.underline || false,
    });
  }

  // กลับมาแก้ไขย่อหน้าที่ "ตกลง" ไปแล้วแต่ยังไม่กด "บันทึกการแก้ไข"
  function handleResumeTextEdit(blockId) {
    const existing = pendingEditsForPage[blockId];
    if (!existing) return;
    setDraftEdit({ blockId, ...existing });
  }

  
  // สร้างข้อความใหม่จากการลากเมาส์ (แทรกข้อความ)
  function handleInsertTextDrag(rectPt) {
    if (!session) return;
    
    // ถ้ายิงคลิกเฉยๆ ระยะทางน้อย ให้ใช้ค่า default กว้าง/สูง
    const MIN_DRAG_PT = 5;
    const isTinyDrag = Math.abs(rectPt.x1 - rectPt.x0) < MIN_DRAG_PT && Math.abs(rectPt.y1 - rectPt.y0) < MIN_DRAG_PT;
    
    const rect = isTinyDrag 
        ? { x0: rectPt.x0, y0: rectPt.y0, x1: rectPt.x0 + 150, y1: rectPt.y0 + 30 }
        : rectPt;

    // ไม่มี blockId (เป็น null/undefined) จะแปลว่าเป็นการ Insert ตอนยิง API
    setDraftEdit({
      blockId: `insert-${Date.now()}-${Math.floor(Math.random()*1000)}`,
      serverRect: null, // ไม่มี rect เดิม
      rect: rect,
      text: "",
      fontKey: "sarabun", // default
      fontSize: 16,
      colorHex: "#000000",
      bgColor: _sampleBgAt(rect),
      align: "left",
      valign: "top",
      underline: false,
    });
    
    setStatusMessage('พิมพ์ข้อความใหม่ที่ต้องการแทรก แล้วกด "ตกลง" หรือกดด้านนอกกรอบเพื่อยืนยัน');
  }

  function handleCancelEdit() {
    setDraftEdit(null);
    setTextEditError(null);
  }

  function handleDeleteEdit() {
    if (!draftEdit) return;
    // If it's a newly inserted text block that hasn't been saved yet, just cancel it.
    if (draftEdit.blockId.startsWith("insert-")) {
      handleCancelEdit();
      return;
    }
    // If it's an existing text block, commit it as empty text so the backend deletes it on save.
    const { blockId, ...rest } = draftEdit;
    setPendingEdits((prev) => ({
      ...prev,
      [currentPage]: {
        ...(prev[currentPage] || {}),
        [blockId]: {
          ...rest,
          text: "",
        },
      },
    }));
    setDraftEdit(null);
    setTextEditError(null);
  }

  // กด "ตกลง" ใน EditableTextBox — ย้าย draft ไป pendingEdits (ยังไม่ยิง API)
  function handleCommitBlockEdit() {
    if (!draftEdit) return;
    const { blockId, ...rest } = draftEdit;
    setPendingEdits((prev) => ({
      ...prev,
      [currentPage]: { ...(prev[currentPage] || {}), [blockId]: rest },
    }));
    setDraftEdit(null);
    setStatusMessage('ยืนยันย่อหน้านี้แล้ว — กด "บันทึกการแก้ไข" บน toolbar เมื่อแก้ไขครบทุกจุด');
  }

  // ยกเลิกการแก้ไขที่อยู่ในสถานะ pending (เช่นกดยกเลิกการลบ)
  function handleRestoreTextEdit(blockId) {
    setPendingEdits((prev) => {
      const pageEdits = { ...(prev[currentPage] || {}) };
      delete pageEdits[blockId];
      return { ...prev, [currentPage]: pageEdits };
    });
  }

  // รีเซ็ต draft + pending (ใช้ตอน undo/redo/เปลี่ยนเอกสาร — state ค้างไม่ valid กับเอกสารใหม่แล้ว)
  function reset() {
    setDraftEdit(null);
    setPendingEdits({});
    setTextEditError(null);
    setApplyingEdits(false);
  }

  return {
    // state
    textBlocks,
    setTextBlocks,
    draftEdit,
    setDraftEdit,
    pendingEdits,
    setPendingEdits,
    textEditError,
    setTextEditError,
    applyingEdits,
    setApplyingEdits,
    // computed
    textPendingCount,
    pendingEditsForPage,
    // handlers
    handleSelectTextBlock,
    handleInsertTextDrag,
    handleResumeTextEdit,
    handleCancelEdit,
    handleDeleteEdit,
    handleRestoreTextEdit,
    handleCommitBlockEdit,
    // cross-hook
    reset,
  };
}
