import React, { forwardRef, useEffect, useLayoutEffect, useRef, useState } from "react";
import { pageImageSrc } from "../utils/pageImage.js";
import CanvasContextMenu from "./CanvasContextMenu.jsx";
import EditableTextBox from "./EditableTextBox.jsx";
import ImageEditBox from "./ImageEditBox.jsx";
import AnnotationBox from "./AnnotationBox.jsx";
import { ZOOM_MAX, ZOOM_MIN } from "../hooks/useZoom.js";

// เครื่องมือ annotation ที่ใช้ "ลากเมาส์" กำหนดตำแหน่ง+ขนาด (mousedown-move-up) แทนการคลิกจุดเดียว
// แล้วได้กล่องขนาดคงที่แบบเดิม — highlight/text_note ใช้ผลลัพธ์ของการลากไป snap กับคำจริงในหน้า
// (ดู App.jsx handleAnnotationDrag + utils/textSelectionUtils.js) ส่วน freetext/rect ใช้กรอบที่ลากได้ตรงๆ
const DRAG_ANNOTATION_TOOLS = ["highlight", "freetext", "rect", "text_note", "insert_text", "redact"];
// แว่นขยายตอนลากด้วยนิ้ว (เลือกข้อความ/วาดกรอบ) — เห็นส่วนที่นิ้วบัง แบบเดียวกับหน้าสแกน (scan/CornerEditor)
const LOUPE = 128;
const LOUPE_ZOOM = 2.2;
const LOUPE_GAP = 36; // ระยะจากปลายนิ้วถึงขอบแว่น

/**
 * PDFCanvas — พื้นที่แสดงผลหลักตรงกลางจอ
 * - ถ้ายังไม่มีเอกสาร: แสดง empty state พร้อม drag & drop เปิดไฟล์
 * - ถ้ามีเอกสาร: แสดงรูป render ของหน้าปัจจุบัน และรับคลิก/ลากเมาส์เพื่อวาง annotation / แทรกข้อความ-รูปภาพใหม่
 *   / เลื่อนหน้าจอ (พิกัดจะถูกแปลงกลับเป็นหน่วย point ของ PDF ก่อนส่งไป backend)
 *
 * รับ ref (forwardRef) ไปที่ container .canvas-area ตัวนอกสุด เพื่อให้ App.jsx
 * วัดขนาดพื้นที่ที่มองเห็นได้จริง (clientWidth/clientHeight) ไปคำนวณซูมแบบ
 * "พอดีความกว้าง/ความสูง" (fit width / fit height) ได้ — container เดียวกันนี้ยังเป็นตัวที่ scroll
 * ตอนใช้ "มือจับเลื่อนหน้า" (hand tool) ด้วย
 *
 * โหมดต่างๆ ที่ activeTool ควบคุม (ดู App.jsx ที่คำนวณ editMode จาก activeTool):
 *   - "edit_text" / "insert_text"  -> editMode === "text"  (แก้ย่อหน้าเดิม / แทรกย่อหน้าใหม่)
 *   - "edit_image" -> editMode === "image" (ย้าย/ปรับขนาด/แทนที่รูปเดิม · ลากไฟล์รูปมาวางเพื่อแทรกรูปใหม่)
 *   - "insert_text"/"insert_image": คลิกบนพื้นที่ว่างของหน้าเอกสารจะสร้างย่อหน้า/รูปใหม่ตรงจุดที่คลิก
 *     (ผ่าน onCanvasInsertClick) ต่างจาก "edit_text"/"edit_image" ที่ต้องคลิกกล่องที่มีอยู่แล้วเท่านั้น
 *   - "highlight"/"freetext"/"rect"/"text_note": ลากเมาส์ (mousedown-move-up) กำหนดตำแหน่ง+ขนาด
 *     กล่อง annotation เอง (ผ่าน onAnnotationDrag) — คลิกเฉยๆ ไม่ลาก ก็ยังใช้ได้ (ตกลงเป็นขนาด default)
 *   - "hand": ลากเมาส์เพื่อเลื่อนมุมมองหน้าเอกสาร (pan) แทนการวาง annotation ใดๆ
 */
const PDFCanvas = forwardRef(function PDFCanvas({
  pageImage,
  pageWidthPt,
  pageHeightPt,
  zoom,
  loading,
  hasDocument,
  activeTool,
  onAnnotationDrag, // (tool, rectPt) — ลากเมาส์เสร็จตอนอยู่เครื่องมือ highlight/freetext/rect/text_note
  onImageDrop, // (file, {xPt,yPt}) — ลากไฟล์รูปมาวางบนหน้าตอนอยู่โหมดแก้ไขรูปภาพ
  onOpenClick,
  onFileDrop,
  onSelectTool,
  onRotateLeft,
  onRotateRight,
  onZoomIn,
  onZoomOut,
  onZoomOriginal,
  onSetZoom,
  onImageElementReady, // (imgEl) — ส่ง DOM element ของรูปหน้าเอกสารขึ้นไปให้ App.jsx ใช้สุ่มสีพื้นหลัง
  editMode,        // null | "text" | "image" — โหมดแก้ไข/แทรกข้อความ-รูปภาพ (ดู App.jsx)
  textBlocks,      // รายการย่อหน้าของหน้าปัจจุบัน (เมื่อ editMode === "text")
  images,          // รายการรูปภาพของหน้าปัจจุบัน (เมื่อ editMode === "image")
  onSelectTextBlock,   // คลิกย่อหน้าที่ "ยังไม่เคย" มีการแก้ไขค้างอยู่ (เริ่ม draft ใหม่จากของเดิมในไฟล์)
  onResumeTextEdit,    // คลิกกล่องพรีวิวที่ "ตกลง" ไปแล้ว (ทั้งย่อหน้าเดิมที่แก้ หรือย่อหน้าที่เพิ่งแทรกใหม่)
  onSelectImage,       // คลิกรูปที่ "ยังไม่เคย" มีการแก้ไขค้างอยู่
  onResumeImageEdit,   // คลิกกล่องพรีวิวรูปที่ "ตกลง" ไปแล้ว (ทั้งรูปเดิมที่ย้าย/แทนที่ หรือรูปที่เพิ่งแทรกใหม่)
  pendingRedactions,   // รายการกรอบเซ็นเซอร์ที่รอการกดยืนยัน (สำหรับโหมด redact)
  piiHighlights,       // PDPA: [{id, rects, selected, active}] ของหน้านี้ — กรอบที่จะถูกปิด (ยังไม่ปิดจริง)
  draftEdit,       // ย่อหน้าที่กำลังแก้ไขอยู่ตอนนี้ { blockId, text, rect, fontKey, fontSize, colorHex, bgColor }
  onDraftTextChange,
  onDraftRectChange,
  onCancelEdit,
  onDeleteEdit,
  onRestoreTextEdit,
  pendingEditsForPage, // { [blockId]: {rect,text,fontKey,fontSize,colorHex,bgColor,...} } ของหน้านี้ —
                       // ย่อหน้าที่กด "ตกลง" ไปแล้วแต่ยังไม่กด "บันทึกการแก้ไข" (ดู pendingEdits ใน App.jsx)
  draftImageEdit,      // รูปที่กำลังแก้ไขอยู่ตอนนี้ { key, kind, xref, rect, previewUrl, ... }
  onDraftImageRectChange,
  onImageReplaceFile,
  onCommitImageEdit,
  onCancelImageEdit,
  onDeleteImageEdit,
  onRestoreImageEdit,
  pendingImageEditsForPage, // { [key]: {kind,xref,rect,previewUrl,...} } ของหน้านี้
  annotations,          // annotation ทั้งหมดของหน้านี้ (โหมด select/hand/วางเครื่องมือ annotation — editMode === null)
  annotationDraft,      // annotation ที่กำลังเลือก/แก้ไขอยู่ตอนนี้ { xref, pageNumber, type, rect, content, colorHex, fontKey, fontSize }
  fonts,                // [{key,label}] จาก GET /edit/fonts — ใช้ทำ dropdown ฟอนต์ของกล่องข้อความ (freetext) ใน AnnotationBox ด้วย
  onSelectAnnotation,
  onAnnotationDraftRectChange,
  onAnnotationDraftContentChange,
  onAnnotationDraftColorChange,
  onAnnotationDraftFontKeyChange,
  onAnnotationDraftFontSizeChange,
  onCommitAnnotationEdit,
  onCancelAnnotationEdit,
  onDeleteAnnotation,
  onNavigatePage, // (delta: 1 | -1) — เลื่อนเมาส์ (wheel) เกินขอบบน/ล่างของหน้าปัจจุบันแล้วให้สลับหน้าเอง
  // ---------- เมนู Digital Signature (Electronic Sign / Digital Sign — ผู้ใช้แจ้งขอ) ----------
  // ไม่ผูกกับระบบ editMode ("text"/"image") ข้างบนเลย ทำงานเป็นชั้นแยกต่างหากอิสระ (ตั้งใจ — กันไม่ให้
  // ไปแทรกแซง logic ผูกขาดกันเองของโหมดแก้ไขข้อความ/รูปภาพเดิมที่มีอยู่แล้ว) draftSignature มีค่าได้ทั้ง
  // ตอนวาง Electronic Sign (previewUrl = รูปลายเซ็นที่ frontend เรนเดอร์เอง) และ Digital Sign (ยังไม่มี
  // รูปจริงให้พรีวิวตอนเลือกพื้นที่ เพราะยังไม่ได้เซ็นจริง — previewUrl จะเป็น undefined กรณีนี้ กล่องจะ
  // โชว์แค่กรอบเปล่าให้ลาก/ย้าย/ย่อ/ขยายก่อนกด "ตกลง" ไปเรียก digital sign จริง)
  draftSignature,      // { rect, previewUrl? } | null
  onDraftSignatureRectChange,
  onCommitSignature,
  onCancelSignature,
}, canvasAreaRef) {
  const imgRef = useRef(null);
  const pageSheetRef = useRef(null);
  const isPanningRef = useRef(false);
  const [isPanning, setIsPanning] = useState(false); // แค่ไว้สลับ cursor grab/grabbing เท่านั้น
  
  // Pinch-to-zoom support — ขอบเขตเดียวกับปุ่มซูม (useZoom) เดิม 0.5–4 ทำให้ซูมจาก 500% แล้วกางนิ้ว กลับหดเหลือ 400%
  const pinchZoomRef = useRef({ initialDist: null, initialZoom: null });
  // หลังหุบ/กางนิ้วเสร็จ: จุดที่อยู่ใต้กึ่งกลางสองนิ้วต้องอยู่ที่เดิมหลังซูมจริง (เดิมกระโดดไปมุมซ้ายบน)
  const pendingPinchFocusRef = useRef(null); // { cx, cy, ux, uy } — ux/uy = พิกัดในแผ่นหน้าที่ซูมใหม่แล้ว (px)
  // นิ้วเดียวบนมือถือ: ปัดซ้าย/ขวา = เปลี่ยนหน้า · กดค้างแล้วลาก = เลือกข้อความเพื่อคัดลอก (ไม่มีเครื่องมือ)
  const swipeRef = useRef(null); // { x, y, t, scrollLeft, multi, target }
  const touchSelectRef = useRef(false); // กำลังเลือกข้อความด้วยนิ้ว — touchmove ต้อง preventDefault (ไม่ให้เลื่อนจอ)
  const [loupe, setLoupe] = useState(null); // { x, y } จุดใต้นิ้ว (client px) ระหว่างลากด้วยนิ้ว
  const loupeCanvasRef = useRef(null);
  
  // dragSelect — สถานะ "กำลังลากเมาส์" วาง annotation อยู่ตอนนี้ (highlight/freetext/rect/text_note)
  // เก็บเป็นพิกัด PDF point ทั้งจุดเริ่มและจุดปัจจุบัน ใช้ทั้งวาดกรอบพรีวิวสดๆ ระหว่างลาก และคำนวณ
  // กรอบสุดท้ายตอนปล่อยเมาส์ (ดู handlePageMouseDown ด้านล่าง)
  const [dragSelect, setDragSelect] = useState(null); // { tool, x0,y0,x1,y1 }
  const [contextMenu, setContextMenu] = useState(null);

  useEffect(() => {
    const handleGlobalClick = () => setContextMenu(null);
    window.addEventListener("click", handleGlobalClick);
    return () => window.removeEventListener("click", handleGlobalClick);
  }, []);
  const dragSelectRef = useRef(null); // ค่าล่าสุดของ dragSelect แบบ side-effect-free อ่านตอน pointerup (ดูหมายเหตุ handlePageMouseDown)

  // ------- เลื่อนเมาส์ (scroll wheel/trackpad) เกินขอบหน้าเอกสารแล้วสลับไปหน้าถัดไป/ก่อนหน้าเอง
  // (ผู้ใช้แจ้งขอ — ไม่ต้องกดปุ่ม "หน้าถัดไป"/"หน้าก่อนหน้า" ที่ StatusBar เอง) -------
  // เก็บ editMode/onNavigatePage ล่าสุดไว้ใน ref แยก เพราะ effect ผูก listener แค่ครั้งเดียว (ดูด้านล่าง)
  // ไม่อยาก resubscribe ทุกครั้งที่ค่าเหล่านี้เปลี่ยน (เช่นทุกครั้งที่ re-render จาก parent)
  const editModeRef = useRef(editMode);
  useEffect(() => {
    editModeRef.current = editMode;
  }, [editMode]);
  const onNavigatePageRef = useRef(onNavigatePage);
  useEffect(() => {
    onNavigatePageRef.current = onNavigatePage;
  }, [onNavigatePage]);

  // เพิ่งเปิดโหมดลากวางตำแหน่งลายเซ็น (draftSignature เปลี่ยนจาก null -> มีค่า) — ตำแหน่งเริ่มต้นอยู่
  // มุมล่างขวาของหน้าเอกสารเสมอ (ดู App.jsx defaultSignatureRectPt) ซึ่งอาจอยู่นอกจอที่กำลังเลื่อนดู
  // ส่วนอื่นของหน้าอยู่พอดี (ผู้ใช้แจ้งว่ากด "ตกลง" ใน popup แล้วมองไม่เห็นกล่องลายเซ็นเลย) — เลื่อนพื้นที่
  // ดูเอกสารอัตโนมัติให้กล่องอยู่กึ่งกลางจอเสมอทันทีที่กล่องปรากฏ
  const prevDraftSignatureRef = useRef(null);
  useEffect(() => {
    if (draftSignature && !prevDraftSignatureRef.current && canvasAreaRef?.current) {
      const boxEl = canvasAreaRef.current.querySelector(".image-edit-box");
      boxEl?.scrollIntoView({ block: "center", inline: "center" });
    }
    prevDraftSignatureRef.current = draftSignature;
  }, [draftSignature, canvasAreaRef]);
  // ทิศทางที่ต้องเลื่อน scrollTop กลับไปสุดขอบ ("top"/"bottom") หลังภาพหน้าใหม่โหลดเสร็จ — ตั้งค่าตอน
  // wheel สั่งเปลี่ยนหน้า แล้วไปเคลียร์/ใช้งานจริงใน useEffect ที่ผูกกับ [pageImage] ด้านล่าง (ให้ความรู้สึก
  // เหมือนเลื่อนต่อเนื่องข้ามหน้าไปเรื่อยๆ แทนที่จะกระโดดไปโผล่กลางหน้าถัดไป)
  const pendingScrollResetRef = useRef(null);
  // กันเลื่อนเมาส์ครั้งเดียว (โดยเฉพาะ trackpad ที่ยิง wheel event รัวๆ ในการปัดครั้งเดียว) สลับหลายหน้า
  // รวดเดียว — ล็อกไว้พักหนึ่งหลังสลับหน้าแต่ละครั้ง
  const wheelCooldownRef = useRef(false);

  // ต้องผูก listener แบบ native (ไม่ใช่ผ่าน prop onWheel ของ React) เพราะ React แนบ wheel listener แบบ
  // passive ไว้ที่ root โดยดีฟอลต์ (เพื่อประสิทธิภาพการ scroll) ทำให้ e.preventDefault() ใน onWheel ของ
  // React ใช้ไม่ได้จริง (เบราว์เซอร์เพิกเฉยเงียบๆ) — ต้องแนบเองด้วย { passive: false } ถึงจะ preventDefault
  // ได้จริงตอนกันไม่ให้ browser เด้ง scroll เกินขอบเอง (rubber-band) ระหว่างที่เรากำลังจะสลับหน้า
  //
  // ใช้ dependency [hasDocument] แทน [] เฉยๆ — เพราะตอนยังไม่มีเอกสาร กับตอนมีเอกสารแล้ว เป็นคนละ
  // <div> กันจริงๆ (ดู JSX ด้านล่าง ทั้งคู่ใช้ ref={canvasAreaRef} เดียวกัน แต่เป็น element คนละตัว) การ
  // สลับ hasDocument ทำให้ DOM node ที่ canvasAreaRef.current ชี้ไปเปลี่ยน จึงต้อง resubscribe ใหม่ทุกครั้ง
  useEffect(() => {
    const el = canvasAreaRef?.current;
    if (!el) return undefined;

    function handleWheel(e) {
      if (editModeRef.current || wheelCooldownRef.current) return; // ปิดใช้งานระหว่างแก้ไขข้อความ/รูปภาพ กันสลับหน้าหนีดราฟต์ที่ยังไม่บันทึกโดยไม่ตั้งใจ
      if (isPanningRef.current || dragSelectRef.current) return; // กำลังลากมือจับเลื่อนจอ/วาง annotation อยู่ ไม่ยุ่ง
      if (e.deltaY === 0 || Math.abs(e.deltaY) < Math.abs(e.deltaX)) return; // สนใจแค่การเลื่อนแนวตั้งเป็นหลัก

      const atTop = el.scrollTop <= 2;
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 2;

      if (e.deltaY > 0 && atBottom) {
        e.preventDefault();
        wheelCooldownRef.current = true;
        // ไปหน้าถัดไป — เริ่มที่ขอบบนสุดของหน้าใหม่ (หน้าสุดท้ายแล้ว: ไม่ตั้งค่าค้างไว้ ไม่งั้นซูมครั้งหน้ากระโดดขึ้นบน)
        if (onNavigatePageRef.current?.(1) !== false) pendingScrollResetRef.current = "top";
        setTimeout(() => {
          wheelCooldownRef.current = false;
        }, 550);
      } else if (e.deltaY < 0 && atTop) {
        e.preventDefault();
        wheelCooldownRef.current = true;
        // ย้อนหน้าก่อนหน้า — โผล่ที่ขอบล่างสุดของหน้าใหม่ (ความรู้สึกเหมือนเลื่อนขึ้นต่อเนื่อง)
        if (onNavigatePageRef.current?.(-1) !== false) pendingScrollResetRef.current = "bottom";
        setTimeout(() => {
          wheelCooldownRef.current = false;
        }, 550);
      }
    }

    // กดค้างเพื่อเลือกข้อความด้วยนิ้ว: กันเบราว์เซอร์เลื่อนจอระหว่างลาก (ต้องเป็น listener แบบ non-passive)
    function handleTouchMoveNative(e) {
      if (touchSelectRef.current && e.cancelable) e.preventDefault();
    }
    el.addEventListener("wheel", handleWheel, { passive: false });
    el.addEventListener("touchmove", handleTouchMoveNative, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
      el.removeEventListener("touchmove", handleTouchMoveNative);
    };
  }, [hasDocument, canvasAreaRef]);

  // ส่ง element ของรูปหน้าเอกสารขึ้นไปให้ App.jsx ทุกครั้งที่เปลี่ยนรูป (หน้า/ซูมเปลี่ยน) ใช้สุ่มสี
  // พื้นหลังจริงตรงตำแหน่งกล่องที่กำลังจะแก้ไข (ดู utils/bgSample.js กับ EditableTextBox.jsx)
  useEffect(() => {
    onImageElementReady?.(imgRef.current);
    // เพิ่งสลับหน้าจากการเลื่อนเมาส์เกินขอบ (ดู handleWheel ด้านบน) — เลื่อน scrollTop ไปสุดขอบตรงข้าม
    // ของหน้าใหม่ทันทีที่ภาพโหลดเสร็จ ให้ความรู้สึกเหมือนเลื่อนต่อเนื่องข้ามหน้าจริงๆ ไม่ใช่กระโดดไป
    // โผล่กลางหน้าถัดไป
    if (pendingScrollResetRef.current && canvasAreaRef?.current) {
      const el = canvasAreaRef.current;
      if (pendingScrollResetRef.current === "top") {
        el.scrollTop = 0;
      } else if (pendingScrollResetRef.current === "bottom") {
        el.scrollTop = el.scrollHeight - el.clientHeight;
      } else if (pendingScrollResetRef.current === "swipe") {
        el.scrollTop = 0;
        el.scrollLeft = 0;
      }
      pendingScrollResetRef.current = null;
    }
  }, [pageImage, onImageElementReady, canvasAreaRef]);

  function pagePointFromEvent(e) {
    const boxRect = imgRef.current.getBoundingClientRect();
    const xRatio = (e.clientX - boxRect.left) / boxRect.width;
    const yRatio = (e.clientY - boxRect.top) / boxRect.height;
    return { xPt: xRatio * pageWidthPt, yPt: yRatio * pageHeightPt };
  }

  function handleClick() {
    // เครื่องมือ annotation จัดการผ่าน mousedown-drag (ดู handlePageMouseDown) · select/edit-mode คลิกกล่องที่มีอยู่โดยตรง
    // · "hand" ลากเลื่อนหน้าจอ · แทรกรูปใช้ปุ่ม/เมนู (เลือกไฟล์) หรือลากไฟล์มาวาง (handleDrop) — ไม่มีอะไรต้องทำตรงนี้
  }

  // ลากเมาส์วาง annotation (highlight/freetext/rect/text_note) — คลิกเฉยๆ ไม่ลาก ก็ยังนับเป็น "ลาก
  // ระยะทาง 0" ได้ปกติ (ฝั่ง App.jsx จะ fallback เป็นกล่องขนาด default ให้เองถ้าระยะทางสั้นเกินไป)
  //
  // หมายเหตุสำคัญ: เก็บค่าล่าสุดของการลากไว้ใน ref (dragSelectRef) ควบคู่กับ state (dragSelect ใช้
  // แค่ re-render กรอบพรีวิว) แล้วอ่านค่าสุดท้ายจาก ref ตอนปล่อยเมาส์ (onUp) เพื่อเรียก onAnnotationDrag
  // นอก setState updater เสมอ — ถ้าเรียก side effect (ยิง callback ออกไปข้างนอก) อยู่ *ข้างใน* ฟังก์ชัน
  // updater ของ setState ตรงๆ, React StrictMode (dev mode) จะเรียกฟังก์ชัน updater นั้นซ้ำ 2 ครั้งโดย
  // ตั้งใจ (เพื่อช่วยตรวจจับ side effect ที่ไม่ควรมีใน render/updater) ทำให้ callback ถูกยิงซ้ำสอง
  // ครั้งโดยไม่ได้ตั้งใจ (bug ที่เจอจริงตอนทดสอบ: กด "ตกลง" ทีเดียวแต่ addAnnotation ถูกยิง 2 รอบ)
  function handlePageMouseDown(e) {
    if (!e.isPrimary) return;
    if (!imgRef.current || (activeTool !== null && !DRAG_ANNOTATION_TOOLS.includes(activeTool))) return;
    // นิ้วบนมือถือ ไม่มีเครื่องมือ: ลากนิ้ว = เลื่อนจอ/ปัดเปลี่ยนหน้า (เดิมลากแล้วกลายเป็นกรอบเลือกข้อความ เลื่อนหน้าไม่ได้)
    // กดค้าง ~0.45 วินาทีแล้วลาก = เลือกข้อความเพื่อคัดลอก
    if (e.pointerType === "touch" && activeTool === null) {
      startTouchTextSelect(e);
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    const start = pagePointFromEvent(e);
    const initial = { tool: activeTool, x0: start.xPt, y0: start.yPt, x1: start.xPt, y1: start.yPt };
    dragSelectRef.current = initial;
    setDragSelect(initial);
    if (e.pointerType === "touch") setLoupe({ x: e.clientX, y: e.clientY });

    function onMove(ev) {
      if (ev.pointerId !== e.pointerId) return;
      updateDragSelect(ev);
    }
    function cleanup() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
    }
    function onUp(ev) {
      if (ev.pointerId !== e.pointerId) return;
      cleanup();
      commitDragSelect(ev);
    }
    function onCancel(ev) {
      if (ev.pointerId !== e.pointerId) return;
      cleanup();
      dragSelectRef.current = null;
      setDragSelect(null);
      setLoupe(null);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
  }

  function updateDragSelect(ev) {
    if (!dragSelectRef.current || !imgRef.current) return;
    const p = pagePointFromEvent(ev);
    dragSelectRef.current = { ...dragSelectRef.current, x1: p.xPt, y1: p.yPt };
    setDragSelect(dragSelectRef.current);
    if (ev.pointerType === "touch") setLoupe({ x: ev.clientX, y: ev.clientY });
  }

  function commitDragSelect(ev) {
    const d = dragSelectRef.current;
    dragSelectRef.current = null;
    setDragSelect(null);
    setLoupe(null);
    if (!d || !imgRef.current) return;
    const p = pagePointFromEvent(ev);
    const rectPt = {
      x0: Math.min(d.x0, p.xPt),
      y0: Math.min(d.y0, p.yPt),
      x1: Math.max(d.x0, p.xPt),
      y1: Math.max(d.y0, p.yPt),
    };
    onAnnotationDrag?.(d.tool, rectPt);
  }

  function startTouchTextSelect(e) {
    const { pointerId, clientX: startX, clientY: startY } = e;
    let timer = setTimeout(begin, 450);
    function cleanup() {
      clearTimeout(timer);
      timer = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
    }
    function begin() {
      timer = null;
      if (pinchZoomRef.current.initialDist || !imgRef.current) {
        cleanup();
        return;
      }
      touchSelectRef.current = true;
      navigator.vibrate?.(10);
      window.getSelection?.()?.removeAllRanges();
      const p = pagePointFromEvent({ clientX: startX, clientY: startY });
      const initial = { tool: null, x0: p.xPt, y0: p.yPt, x1: p.xPt, y1: p.yPt };
      setLoupe({ x: startX, y: startY });
      dragSelectRef.current = initial;
      setDragSelect(initial);
    }
    function onMove(ev) {
      if (ev.pointerId !== pointerId) return;
      if (!touchSelectRef.current) {
        // ขยับก่อนครบเวลากดค้าง = ตั้งใจเลื่อนจอ/ปัด — ปล่อยให้เบราว์เซอร์เลื่อนตามปกติ
        if (Math.hypot(ev.clientX - startX, ev.clientY - startY) > 8) cleanup();
        return;
      }
      updateDragSelect(ev);
    }
    function onUp(ev) {
      if (ev.pointerId !== pointerId) return;
      const active = touchSelectRef.current;
      cleanup();
      touchSelectRef.current = false;
      if (active) commitDragSelect(ev);
    }
    function onCancel(ev) {
      if (ev.pointerId !== pointerId) return;
      cleanup();
      touchSelectRef.current = false;
      dragSelectRef.current = null;
      setDragSelect(null);
      setLoupe(null);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
  }

  // move/end ฟังที่ window ตลอดท่าทาง: ถ้าจุดที่นิ้วแตะถูกเอาออกจากหน้า (เช่นข้อความ "กำลังโหลดหน้า…" หายไปตอนรูปมา)
  // touchend จะไม่ขึ้นมาถึง .canvas-area — เดิมปัดซ้ำเร็วๆ หลังเปลี่ยนหน้าแล้วไม่ไปไหน / ซูมค้างกลางทาง
  const gestureListenersRef = useRef(null);
  function ensureGestureListeners() {
    if (gestureListenersRef.current) return;
    const onMove = (ev) => handleTouchMove(ev);
    const onEnd = (ev) => {
      handleTouchEnd(ev);
      if (ev.touches.length === 0) {
        window.removeEventListener("touchmove", onMove, true);
        window.removeEventListener("touchend", onEnd, true);
        window.removeEventListener("touchcancel", onEnd, true);
        gestureListenersRef.current = null;
      }
    };
    gestureListenersRef.current = { onMove, onEnd };
    window.addEventListener("touchmove", onMove, true);
    window.addEventListener("touchend", onEnd, true);
    window.addEventListener("touchcancel", onEnd, true);
  }

  function handleTouchStart(e) {
    ensureGestureListeners();
    if (e.touches.length === 1) {
      const t = e.touches[0];
      const el = canvasAreaRef.current;
      swipeRef.current = { x: t.clientX, y: t.clientY, t: Date.now(), scrollLeft: el ? el.scrollLeft : 0, multi: false, target: e.target };
    }
    if (e.touches.length >= 2) {
      if (swipeRef.current) swipeRef.current.multi = true;
      // Abort any ongoing drawing/text selection or panning drags if multiple fingers are detected
      touchSelectRef.current = false;
      dragSelectRef.current = null;
      setDragSelect(null);
      setLoupe(null);
      isPanningRef.current = false;
      setIsPanning(false);

      const touch1 = e.touches[0];
      const touch2 = e.touches[1];
      const dist = Math.hypot(touch1.clientX - touch2.clientX, touch1.clientY - touch2.clientY);
      const centerX = (touch1.clientX + touch2.clientX) / 2;
      const centerY = (touch1.clientY + touch2.clientY) / 2;
      
      if (pageSheetRef.current) {
        const rect = pageSheetRef.current.getBoundingClientRect();
        const originX = (centerX - rect.left) + "px";
        const originY = (centerY - rect.top) + "px";
        pageSheetRef.current.style.transformOrigin = `${originX} ${originY}`;
        pageSheetRef.current.style.transition = "none"; 
      }
      
      const el = canvasAreaRef.current;
      pinchZoomRef.current = { 
        initialDist: dist, 
        initialZoom: zoom, 
        lastScale: 1,
        initialCenterX: centerX,
        initialCenterY: centerY,
        lastCenterX: centerX,
        lastCenterY: centerY,
        initialScrollLeft: el ? el.scrollLeft : 0,
        initialScrollTop: el ? el.scrollTop : 0
      };
    }
  }

  function handleTouchMove(e) {
    if (e.touches.length === 2 && pinchZoomRef.current.initialDist) {
      const touch1 = e.touches[0];
      const touch2 = e.touches[1];
      const dist = Math.hypot(touch1.clientX - touch2.clientX, touch1.clientY - touch2.clientY);
      const centerX = (touch1.clientX + touch2.clientX) / 2;
      const centerY = (touch1.clientY + touch2.clientY) / 2;
      
      // ไม่ให้ภาพหดเล็ก/ใหญ่เกินขอบเขตซูมจริง (เดิมกางได้ไม่จำกัด แล้วเด้งกลับตอนปล่อยนิ้ว)
      const pz = pinchZoomRef.current;
      const scale = Math.min(ZOOM_MAX / pz.initialZoom, Math.max(ZOOM_MIN / pz.initialZoom, dist / pz.initialDist));
      pz.lastScale = scale;
      pz.lastCenterX = centerX;
      pz.lastCenterY = centerY;
      
      if (pageSheetRef.current) {
        pageSheetRef.current.style.transform = `scale(${scale})`;
      }
      
      const el = canvasAreaRef.current;
      if (el) {
        const dx = centerX - pz.initialCenterX;
        const dy = centerY - pz.initialCenterY;
        el.scrollLeft = pz.initialScrollLeft - dx;
        el.scrollTop = pz.initialScrollTop - dy;
      }
    }
  }

  function finishPinch() {
    const pz = pinchZoomRef.current;
    pinchZoomRef.current = { initialDist: null, initialZoom: null, lastScale: null };
    const sheet = pageSheetRef.current;
    if (!pz.initialDist || !pz.lastScale || !sheet) return;
    const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, pz.initialZoom * pz.lastScale));
    if (typeof onSetZoom !== "function" || Math.abs(newZoom - pz.initialZoom) < 0.01) {
      sheet.style.transform = "none"; // สองนิ้วเลื่อนจอเฉยๆ ไม่ได้ซูม
      return;
    }
    // จุดใต้กึ่งกลางสองนิ้ว ในพิกัดแผ่นหน้าหลังซูมจริง — คงภาพที่ขยายไว้ (transform) จนกว่าขนาดจริงจะเปลี่ยน
    // (ดู useLayoutEffect [zoom]) ไม่งั้นภาพเด้งกลับขนาดเดิมแวบหนึ่งก่อนขยาย
    const r = sheet.getBoundingClientRect();
    const visScale = sheet.offsetWidth ? r.width / sheet.offsetWidth : pz.lastScale;
    const ratio = newZoom / pz.initialZoom;
    pendingPinchFocusRef.current = {
      cx: pz.lastCenterX,
      cy: pz.lastCenterY,
      ux: ((pz.lastCenterX - r.left) / visScale) * ratio,
      uy: ((pz.lastCenterY - r.top) / visScale) * ratio,
    };
    onSetZoom(newZoom);
  }

  // ปัดนิ้วเดียวซ้าย/ขวา = หน้าถัดไป/ก่อนหน้า — เฉพาะตอนดูเอกสาร (ไม่มีเครื่องมือ หรือมือจับ) และหน้ากว้างไม่เกินจอ
  // หรือเลื่อนไปสุดขอบด้านนั้นแล้ว (ไม่แย่งการเลื่อนดูส่วนที่ล้นจอ)
  function maybeSwipe(touch) {
    const sw = swipeRef.current;
    const el = canvasAreaRef.current;
    if (!sw || sw.multi || !touch || !el) return;
    if (dragSelectRef.current || touchSelectRef.current || isPanningRef.current) return;
    if (editModeRef.current || (activeTool && activeTool !== "hand") || annotationDraft || draftSignature) return;
    if (sw.target?.closest?.("input, textarea, select, button, a, [contenteditable='true'], .resize-handle, .edit-box-drag-handle, .annot-note-marker, .annot-toolbar, .image-edit-box")) return;
    const dx = touch.clientX - sw.x;
    const dy = touch.clientY - sw.y;
    if (Date.now() - sw.t > 700 || Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.8) return;
    const maxLeft = el.scrollWidth - el.clientWidth;
    if (dx < 0 && sw.scrollLeft < maxLeft - 2) return;
    if (dx > 0 && sw.scrollLeft > 2) return;
    if (onNavigatePageRef.current?.(dx < 0 ? 1 : -1) !== false) pendingScrollResetRef.current = "swipe";
  }

  function handleTouchEnd(e) {
    if (e.touches.length < 2 && pinchZoomRef.current.initialDist) finishPinch();
    if (e.touches.length === 0) {
      if (e.type === "touchend") maybeSwipe(e.changedTouches?.[0]);
      swipeRef.current = null;
    }
  }

  // วาดแว่นขยาย: ภาพหน้าเอกสาร (ความละเอียดเต็มของรูป) รอบจุดใต้นิ้ว + กรอบที่กำลังลาก + เป้ากลาง
  const showLoupe = !!(loupe && dragSelect);
  useLayoutEffect(() => {
    if (!showLoupe) return;
    const canvas = loupeCanvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !img.naturalWidth) return;
    const r = img.getBoundingClientRect();
    if (!r.width) return;
    const dpr = window.devicePixelRatio || 1;
    const size = Math.round(LOUPE * dpr);
    if (canvas.width !== size) {
      canvas.width = size;
      canvas.height = size;
    }
    const ctx = canvas.getContext("2d");
    const k = size / LOUPE; // canvas px ต่อ css px ของแว่น
    const natPerCss = img.naturalWidth / r.width;
    const srcSize = (LOUPE / LOUPE_ZOOM) * natPerCss;
    const sx = (loupe.x - r.left) * natPerCss - srcSize / 2;
    const sy = (loupe.y - r.top) * natPerCss - srcSize / 2;
    ctx.fillStyle = "#e2e8f0";
    ctx.fillRect(0, 0, size, size);
    ctx.drawImage(img, sx, sy, srcSize, srcSize, 0, 0, size, size);
    // จุดบนจอ (css px) → พิกัดในแว่น (canvas px)
    const toLoupe = (cx, cy) => [((cx - loupe.x) * LOUPE_ZOOM + LOUPE / 2) * k, ((cy - loupe.y) * LOUPE_ZOOM + LOUPE / 2) * k];
    const ptToClient = (xPt, yPt) => [r.left + (xPt / pageWidthPt) * r.width, r.top + (yPt / pageHeightPt) * r.height];
    const [ax, ay] = toLoupe(...ptToClient(Math.min(dragSelect.x0, dragSelect.x1), Math.min(dragSelect.y0, dragSelect.y1)));
    const [bx, by] = toLoupe(...ptToClient(Math.max(dragSelect.x0, dragSelect.x1), Math.max(dragSelect.y0, dragSelect.y1)));
    const red = dragSelect.tool === "redact";
    ctx.fillStyle = red ? "rgba(239,68,68,0.18)" : dragSelect.tool === "highlight" || dragSelect.tool === "text_note" ? "rgba(250,204,21,0.30)" : "rgba(14,165,233,0.16)";
    ctx.strokeStyle = red ? "#ef4444" : "#0ea5e9";
    ctx.lineWidth = 1.5 * k;
    ctx.fillRect(ax, ay, bx - ax, by - ay);
    ctx.strokeRect(ax, ay, bx - ax, by - ay);
    const m = size / 2;
    ctx.strokeStyle = "rgba(15,23,42,0.7)";
    ctx.lineWidth = 1 * k;
    ctx.beginPath();
    ctx.moveTo(m - 8 * k, m); ctx.lineTo(m + 8 * k, m);
    ctx.moveTo(m, m - 8 * k); ctx.lineTo(m, m + 8 * k);
    ctx.stroke();
  }, [showLoupe, loupe, dragSelect, pageWidthPt, pageHeightPt]);

  // ซูมจากการหุบ/กางนิ้วถูกใช้แล้ว (ขนาดแผ่นหน้าเปลี่ยนใน commit นี้) — เอา transform ออกแล้วเลื่อนให้จุดใต้นิ้วอยู่ที่เดิม
  useLayoutEffect(() => {
    const f = pendingPinchFocusRef.current;
    const sheet = pageSheetRef.current;
    const el = canvasAreaRef?.current;
    if (!f || !sheet || !el) return;
    pendingPinchFocusRef.current = null;
    sheet.style.transform = "none";
    const r = sheet.getBoundingClientRect();
    el.scrollLeft += r.left + f.ux - f.cx;
    el.scrollTop += r.top + f.uy - f.cy;
  }, [zoom, canvasAreaRef]);

  // "มือจับเลื่อนหน้า" (hand tool) — ลากเมาส์เพื่อเลื่อน scroll ของ .canvas-area (container ที่ forward
  // ref มาจาก App.jsx) แทนการวาง annotation ใดๆ ทำงานได้ทุกจุดในพื้นที่มองเห็น ไม่ใช่แค่บนตัวรูปหน้าเอกสาร
  function handlePanMouseDown(e) {
    if (!e.isPrimary) return;
    if (activeTool !== "hand" || !canvasAreaRef?.current) return;
    if (e.pointerType === "touch") return; // นิ้ว: เบราว์เซอร์เลื่อนเอง (มีแรงเฉื่อย) — ดู touch-action ใน styles.css
    e.preventDefault();
    const el = canvasAreaRef.current;
    const startX = e.clientX;
    const startY = e.clientY;
    const startScrollLeft = el.scrollLeft;
    const startScrollTop = el.scrollTop;
    isPanningRef.current = true;
    setIsPanning(true);

    function onMove(ev) {
      el.scrollLeft = startScrollLeft - (ev.clientX - startX);
      el.scrollTop = startScrollTop - (ev.clientY - startY);
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      isPanningRef.current = false;
      setIsPanning(false);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  // โหมดแก้ไขรูปภาพ: ลากไฟล์รูปมาวาง = แทรกรูปตรงจุดที่ปล่อย (ปล่อยนอกหน้ากระดาษ → ชิดขอบหน้าที่ใกล้สุด)
  // โหมดอื่น/ไฟล์ที่ไม่ใช่รูป: เปิดเป็นเอกสารใหม่เหมือนเดิม
  const [imageDragOver, setImageDragOver] = useState(false);
  const acceptsImageDrop = hasDocument && editMode === "image" && !!onImageDrop;

  function handleDragOver(e) {
    e.preventDefault();
    if (acceptsImageDrop && !imageDragOver) setImageDragOver(true);
  }

  function handleDrop(e) {
    e.preventDefault();
    setImageDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (acceptsImageDrop && /^image\//.test(file.type || "") && imgRef.current) {
      const { xPt, yPt } = pagePointFromEvent(e);
      onImageDrop(file, {
        xPt: Math.min(Math.max(0, xPt), pageWidthPt),
        yPt: Math.min(Math.max(0, yPt), pageHeightPt),
      });
      return;
    }
    onFileDrop(file);
  }

  if (!hasDocument) {
    return (
      <div
        ref={canvasAreaRef}
        className="canvas-area canvas-empty"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        <div className="empty-state">
          <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
            <rect x="10" y="4" width="30" height="42" rx="3" stroke="var(--color-text-muted)" strokeWidth="2" />
            <path d="M32 4v11h11" stroke="var(--color-text-muted)" strokeWidth="2" />
            <path d="M17 26h16M17 32h16M17 38h10" stroke="var(--color-text-muted)" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <p className="empty-title">ยังไม่ได้เปิดเอกสาร</p>
          <p className="empty-subtitle">ลากไฟล์ PDF หรือ Office มาวางที่นี่ หรือ</p>
          <button type="button" className="primary-btn" onClick={onOpenClick}>
            เปิดไฟล์ PDF
          </button>
        </div>
      </div>
    );
  }

  const pendingTextIds = new Set(Object.keys(pendingEditsForPage || {}));
  const knownTextBlockIds = new Set((textBlocks || []).map((b) => b.block_id));
  // ย่อหน้าที่เพิ่งแทรกใหม่ (ยังไม่เคยยิง API เลย) จะไม่มีทางโผล่ใน textBlocks — ต้องวาดพรีวิวแยกต่างหาก
  const newlyInsertedTextIds = [...pendingTextIds].filter((id) => !knownTextBlockIds.has(id));

  const pendingImageKeys = new Set(Object.keys(pendingImageEditsForPage || {}));
  const knownImageXrefKeys = new Set((images || []).map((img) => img.id || `img-${img.xref}`));
  const newlyInsertedImageKeys = [...pendingImageKeys].filter((key) => !knownImageXrefKeys.has(key));

  return (
    <div
      ref={canvasAreaRef}
      className={`canvas-area ${activeTool === "hand" ? "tool-hand" : ""} ${isPanning ? "panning" : ""} ${imageDragOver ? "image-drop-target" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setImageDragOver(false); }}
      onDrop={handleDrop}
      onPointerDown={handlePanMouseDown}
      onTouchStart={handleTouchStart}
      onContextMenu={(e) => {
        e.preventDefault();
        setContextMenu({ x: e.clientX, y: e.clientY });
      }}
    >
      {showLoupe && (() => {
        // อยู่เหนือนิ้ว (นิ้วบังด้านล่างอยู่แล้ว) — ชิดขอบบนจอแล้วย้ายไปข้างนิ้วแทน
        const vw = window.innerWidth;
        let top = loupe.y - LOUPE - LOUPE_GAP;
        let left = loupe.x - LOUPE / 2;
        if (top < 8) {
          top = Math.max(8, loupe.y - LOUPE / 2);
          left = loupe.x + LOUPE_GAP + LOUPE <= vw - 8 ? loupe.x + LOUPE_GAP : loupe.x - LOUPE_GAP - LOUPE;
        }
        left = Math.min(vw - LOUPE - 8, Math.max(8, left));
        return (
          <canvas ref={loupeCanvasRef} data-testid="text-loupe" aria-hidden="true"
            className="fixed z-[150] rounded-full border-2 border-white shadow-xl pointer-events-none"
            style={{ width: LOUPE, height: LOUPE, left, top }} />
        );
      })()}
      {contextMenu && (
        <CanvasContextMenu
          position={contextMenu}
          onSelectTool={onSelectTool}
          onRotateLeft={onRotateLeft}
          onRotateRight={onRotateRight}
          onZoomIn={onZoomIn}
          onZoomOut={onZoomOut}
          onZoomOriginal={onZoomOriginal}
        />
      )}
      <div
        className={`page-sheet ${activeTool ? `tool-${activeTool}` : ""}`}
        onClick={handleClick}
        onPointerDown={handlePageMouseDown}
        ref={pageSheetRef}
        // ยังไม่มีรูปหน้า (เปิดไฟล์ครั้งแรก): กันพื้นที่เท่าขนาดหน้าไว้ก่อน — ไม่งั้นกรอบกว้างเกือบ 0 ข้อความ
        // "กำลังโหลดหน้า…" ถูกบีบเป็นบรรทัดละตัวอักษร และหน้าไม่กระโดดตอนรูปมา
        style={!pageImage ? {
          width: (pageWidthPt > 1 ? pageWidthPt : 595) * zoom,
          height: (pageHeightPt > 1 ? pageHeightPt : 842) * zoom,
          maxWidth: "100%",
        } : undefined}
      >
        {loading && <div className="page-loading">กำลังโหลดหน้า…</div>}
        {pageImage && (
          <img
            ref={imgRef}
            src={pageImageSrc(pageImage)}
            alt="หน้าเอกสารปัจจุบัน"
            className="page-image"
            // ขนาดบนจอ = ขนาดหน้า × ซูม (รูปเรนเดอร์ละเอียดกว่านั้นตามความละเอียดจอ — ไม่เบลอบนมือถือ/จอ Retina)
            // ความสูงตามสัดส่วนรูปจริง · ซูมเปลี่ยนแล้วขนาดเปลี่ยนทันที ไม่ต้องรอรูปใหม่
            style={pageWidthPt > 1 ? { width: pageWidthPt * zoom, height: "auto" } : undefined}
            draggable={false}
          />
        )}

        {/* เลเยอร์แสดง Pending Redactions (รอการกดยืนยัน) */}
        {pendingRedactions && pendingRedactions.map((rect, idx) => (
          <div
            key={`redact-${idx}`}
            style={{
              position: "absolute",
              left: rect.x0 * zoom,
              top: rect.y0 * zoom,
              width: (rect.x1 - rect.x0) * zoom,
              height: (rect.y1 - rect.y0) * zoom,
              backgroundColor: "rgba(0, 0, 0, 0.8)",
              border: "1px solid #000",
              pointerEvents: "none",
              zIndex: 35,
            }}
          />
        ))}

        {/* PDPA: ส้มทึบ = เลือกไว้ (จะถูกปิด) · เส้นประเทา = ไม่ได้เลือก */}
        {piiHighlights && piiHighlights.flatMap((h) => h.rects.map((rect, idx) => (
          <div
            key={`pii-${h.id}-${idx}`}
            data-testid="pii-highlight"
            style={{
              position: "absolute",
              left: rect.x0 * zoom,
              top: rect.y0 * zoom,
              width: (rect.x1 - rect.x0) * zoom,
              height: (rect.y1 - rect.y0) * zoom,
              backgroundColor: h.selected ? "rgba(249, 115, 22, 0.28)" : "transparent",
              border: h.selected ? "2px solid #f97316" : "1.5px dashed #9ca3af",
              boxShadow: h.active ? "0 0 0 3px rgba(249, 115, 22, 0.45)" : "none",
              borderRadius: 2,
              pointerEvents: "none",
              zIndex: 35,
            }}
          />
        )))}

        {dragSelect && (
          <div
            className={
              dragSelect.tool === "redact" 
                ? "drag-select-redact"
                : dragSelect.tool === "highlight" || dragSelect.tool === "text_note"
                ? "drag-select-highlight"
                : "drag-select-box"
            }
            style={{
              left: Math.min(dragSelect.x0, dragSelect.x1) * zoom,
              top: Math.min(dragSelect.y0, dragSelect.y1) * zoom,
              width: Math.abs(dragSelect.x1 - dragSelect.x0) * zoom,
              height: Math.abs(dragSelect.y1 - dragSelect.y0) * zoom,
            }}
          />
        )}

        {/* annotation ที่มีอยู่แล้ว (ไฮไลท์/กรอบสี่เหลี่ยม/กล่องข้อความ/โน้ต) — เลือก/แก้ไข/ลบ/เปลี่ยน
            สีได้เฉพาะตอนไม่ได้อยู่โหมดแก้ไขข้อความ/รูปภาพ (editMode null: select/hand/เครื่องมือ
            annotation ก็ยังเห็น+เลือกอันเดิมได้ระหว่างนั้นด้วย — ผู้ใช้แจ้งเพิ่มในรอบนี้) */}
        {!editMode &&
          (annotations || []).map((annot) => {
            const isEditing = annotationDraft?.xref === annot.xref;
            return (
              <AnnotationBox
                key={annot.xref}
                annot={annot}
                zoom={zoom}
                editing={isEditing}
                draftRect={isEditing ? annotationDraft.rect : undefined}
                draftContent={isEditing ? annotationDraft.content : undefined}
                draftColorHex={isEditing ? annotationDraft.colorHex : undefined}
                draftFontKey={isEditing ? annotationDraft.fontKey : undefined}
                draftFontSize={isEditing ? annotationDraft.fontSize : undefined}
                fonts={fonts}
                onSelect={onSelectAnnotation}
                onDraftRectChange={onAnnotationDraftRectChange}
                onDraftContentChange={onAnnotationDraftContentChange}
                onDraftColorChange={onAnnotationDraftColorChange}
                onDraftFontKeyChange={onAnnotationDraftFontKeyChange}
                onDraftFontSizeChange={onAnnotationDraftFontSizeChange}
                onCommit={onCommitAnnotationEdit}
                onCancel={onCancelAnnotationEdit}
                onDelete={onDeleteAnnotation}
              />
            );
          })}

        {
          (textBlocks || [])
            .filter((block) => !draftEdit || draftEdit.blockId !== block.block_id)
            .filter((block) => {
              // ข้ามบล็อกข้อความที่ซ้อนทับกับ annotation — ป้องกันกล่อง annotation ปรากฏเป็นกล่องแก้ไขข้อความ
              if (!annotations || annotations.length === 0) return true;
              return !annotations.some((annot) => {
                const r = block.rect;
                const a = annot.rect;
                if (!a) return false;
                const overlapX = Math.max(0, Math.min(r.x1, a.x1) - Math.max(r.x0, a.x0));
                const overlapY = Math.max(0, Math.min(r.y1, a.y1) - Math.max(r.y0, a.y0));
                const overlapArea = overlapX * overlapY;
                if (overlapArea <= 0) return false;
                const blockArea = (r.x1 - r.x0) * (r.y1 - r.y0);
                const annotArea = (a.x1 - a.x0) * (a.y1 - a.y0);
                // กรองออกถ้า overlap มากกว่า 20% ของ block หรือ annotation ฝั่งใดฝั่งหนึ่ง
                return (blockArea > 0 && overlapArea / blockArea > 0.2)
                    || (annotArea > 0 && overlapArea / annotArea > 0.2);
              });
            })
            .map((block) => {
              const pending = pendingEditsForPage?.[block.block_id];
              if (pending) {
                if (!pending.text || pending.text.trim() === "") {
                  return (
                    <div
                      key={block.block_id}
                      className="deleted-mask"
                      style={{
                        position: "absolute",
                        left: pending.rect.x0 * zoom,
                        top: pending.rect.y0 * zoom,
                        width: (pending.rect.x1 - pending.rect.x0) * zoom,
                        height: (pending.rect.y1 - pending.rect.y0) * zoom,
                        background: pending.bgColor || "#ffffff",
                        cursor: "var(--cursor-hand)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "red",
                      }}
                      title="ยกเลิกการลบ (Restore)"
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        onRestoreTextEdit(block.block_id);
                      }}
                    >
                      <button
                        type="button"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          padding: "2px 6px",
                          background: "#ffffff",
                          border: "1.5px solid #ef4444",
                          borderRadius: "4px",
                          color: "#ef4444",
                          fontSize: "11px",
                          fontWeight: "600",
                          boxShadow: "0 1px 3px rgba(0,0,0,0.18)",
                          cursor: "var(--cursor-hand)",
                          pointerEvents: "auto",
                        }}
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          onRestoreTextEdit(block.block_id);
                        }}
                        title="กู้คืนข้อความนี้"
                      >
                        <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                        </svg>
                        <span>กู้คืน</span>
                      </button>
                    </div>
                  );
                }
                return (
                  <EditableTextBox
                    key={block.block_id}
                    readOnly
                    pending
                    rect={pending.rect}
                    zoom={zoom}
                    text={pending.text}
                    fontKey={pending.fontKey}
                    fontSize={pending.fontSize}
                    colorHex={pending.colorHex}
                    align={pending.align}
                    valign={pending.valign}
                    underline={pending.underline}
                    bgColor={pending.bgColor}
                    onSelect={() => onResumeTextEdit(block.block_id)}
                  />
                );
              }
              if (editMode !== "text") return null;
              return (
                <div
                  key={block.block_id}
                  className="edit-box edit-box-text"
                  style={{
                    left: block.rect.x0 * zoom,
                    top: block.rect.y0 * zoom,
                    width: (block.rect.x1 - block.rect.x0) * zoom,
                    height: (block.rect.y1 - block.rect.y0) * zoom,
                  }}
                  title="คลิกเพื่อแก้ไขย่อหน้านี้"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectTextBlock(block);
                  }}
                />
              );
            })}

        {
          newlyInsertedTextIds
            .filter((id) => !draftEdit || draftEdit.blockId !== id)
            .map((id) => {
              const pending = pendingEditsForPage[id];
              if (!pending || !pending.text || pending.text.trim() === "") return null;
              return (
                <EditableTextBox
                  key={id}
                  readOnly
                  pending
                  rect={pending.rect}
                  zoom={zoom}
                  text={pending.text}
                  fontKey={pending.fontKey}
                  fontSize={pending.fontSize}
                  colorHex={pending.colorHex}
                  align={pending.align}
                  valign={pending.valign}
                  underline={pending.underline}
                  bgColor={pending.bgColor}
                  onSelect={() => onResumeTextEdit(id)}
                />
              );
            })}

        {editMode === "text" && draftEdit && (
          <EditableTextBox
            key={draftEdit.blockId}
            rect={draftEdit.rect}
            zoom={zoom}
            text={draftEdit.text}
            fontKey={draftEdit.fontKey}
            fontSize={draftEdit.fontSize}
            colorHex={draftEdit.colorHex}
            align={draftEdit.align}
            valign={draftEdit.valign}
            underline={draftEdit.underline}
            bgColor={draftEdit.bgColor}
            onTextChange={onDraftTextChange}
            onRectChange={onDraftRectChange}
            onCancel={onCancelEdit}
            onDelete={onDeleteEdit}
          />
        )}

        {
          (images || [])
            .filter((img) => !draftImageEdit || draftImageEdit.key !== (img.id || `img-${img.xref}`))
            .map((img) => {
              const key = img.id || `img-${img.xref}`;
              const pending = pendingImageEditsForPage?.[key];
              if (pending) {
                if (pending.deleted) {
                  return (
                    <div
                      key={key}
                      className="image-edit-original-mask deleted-mask"
                      style={{
                        left: pending.serverRect.x0 * zoom,
                        top: pending.serverRect.y0 * zoom,
                        width: (pending.serverRect.x1 - pending.serverRect.x0) * zoom,
                        height: (pending.serverRect.y1 - pending.serverRect.y0) * zoom,
                        background: pending.bgColor || "#ffffff",
                        cursor: "var(--cursor-hand)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "red",
                      }}
                      title="ยกเลิกการลบ (Restore)"
                      onPointerDown={(e) => e.stopPropagation()}
                      onClick={(e) => {
                        e.stopPropagation();
                        onRestoreImageEdit(key);
                      }}
                    >
                      <button
                        type="button"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          padding: "3px 8px",
                          background: "#ffffff",
                          border: "1.5px solid #ef4444",
                          borderRadius: "4px",
                          color: "#ef4444",
                          fontSize: "12px",
                          fontWeight: "600",
                          boxShadow: "0 1px 3px rgba(0,0,0,0.18)",
                          cursor: "var(--cursor-hand)",
                          pointerEvents: "auto",
                        }}
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          onRestoreImageEdit(key);
                        }}
                        title="กู้คืนรูปภาพนี้"
                      >
                        <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                        </svg>
                        <span>กู้คืน</span>
                      </button>
                    </div>
                  );
                }
                return (
                  <React.Fragment key={key}>
                    {/* ทาทึบตำแหน่งเดิมของรูป (ผู้ใช้แจ้ง: ลากย้ายรูปแล้วไม่ควรเห็นรูปเดิมค้างอยู่ที่
                        ตำแหน่งเก่า) — หน้าเอกสารที่ render มายังไม่ถูก redact จริงจนกว่าจะกด "บันทึกการ
                        แก้ไข" รูปเดิมเลยยังโผล่ทะลุออกมาถ้าไม่ทาทับไว้ */}
                    {pending.serverRect && (
                      <div
                        className="image-edit-original-mask"
                        style={{
                          left: pending.serverRect.x0 * zoom,
                          top: pending.serverRect.y0 * zoom,
                          width: (pending.serverRect.x1 - pending.serverRect.x0) * zoom,
                          height: (pending.serverRect.y1 - pending.serverRect.y0) * zoom,
                          background: pending.bgColor || "#ffffff",
                        }}
                      />
                    )}
                    <div
                      className="edit-box-active image-edit-box-preview edit-box-preview-pending"
                      style={{
                        left: pending.rect.x0 * zoom,
                        top: pending.rect.y0 * zoom,
                        width: (pending.rect.x1 - pending.rect.x0) * zoom,
                        height: (pending.rect.y1 - pending.rect.y0) * zoom,
                      }}
                      title="รูปนี้ยืนยันไว้แล้ว รอกด 'บันทึกการแก้ไข' — คลิกเพื่อแก้ไขต่อ"
                      onClick={(e) => {
                        e.stopPropagation();
                        onResumeImageEdit(key);
                      }}
                    >
                      {pending.previewUrl && (
                        <img src={pending.previewUrl} alt="พรีวิวรูปภาพที่รอบันทึก" className="image-edit-preview" draggable={false} />
                      )}
                    </div>
                  </React.Fragment>
                );
              }
              if (editMode !== "image") return null;
              return (
                <div
                  key={key}
                  className="edit-box edit-box-image"
                  style={{
                    left: img.rect.x0 * zoom,
                    top: img.rect.y0 * zoom,
                    width: (img.rect.x1 - img.rect.x0) * zoom,
                    height: (img.rect.y1 - img.rect.y0) * zoom,
                  }}
                  title="คลิกเพื่อย้าย/ปรับขนาด/แทนที่รูปภาพนี้"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectImage(img);
                  }}
                />
              );
            })}

        {
          newlyInsertedImageKeys
            .filter((key) => !draftImageEdit || draftImageEdit.key !== key)
            .map((key) => {
              const pending = pendingImageEditsForPage[key];
              if (!pending || pending.deleted) return null;
              return (
                <div
                  key={key}
                  className="edit-box-active image-edit-box-preview edit-box-preview-pending"
                  style={{
                    left: pending.rect.x0 * zoom,
                    top: pending.rect.y0 * zoom,
                    width: (pending.rect.x1 - pending.rect.x0) * zoom,
                    height: (pending.rect.y1 - pending.rect.y0) * zoom,
                  }}
                  title="รูปนี้ยืนยันไว้แล้ว รอกด 'บันทึกการแก้ไข' — คลิกเพื่อแก้ไขต่อ"
                  onClick={(e) => {
                    e.stopPropagation();
                    onResumeImageEdit(key);
                  }}
                >
                  {pending.previewUrl && (
                    <img src={pending.previewUrl} alt="พรีวิวรูปภาพที่รอบันทึก" className="image-edit-preview" draggable={false} />
                  )}
                </div>
              );
            })}

        {editMode === "image" && draftImageEdit && draftImageEdit.kind === "existing" && draftImageEdit.serverRect && (
          // ทาทึบตำแหน่งเดิมของรูปที่กำลังลาก/ปรับขนาดอยู่ตอนนี้ (ผู้ใช้แจ้ง: ลากย้ายรูปแล้วไม่ควรเห็น
          // รูปเดิมค้างอยู่ที่ตำแหน่งเก่า) — แต่ถ้าแค่คลิกเลือกเฉยๆ (ยังไม่ลากและยังไม่แทนที่) ไม่ต้องทาทึบ
          (draftImageEdit.file ||
           draftImageEdit.rect.x0 !== draftImageEdit.serverRect.x0 || 
           draftImageEdit.rect.y0 !== draftImageEdit.serverRect.y0 ||
           draftImageEdit.rect.x1 !== draftImageEdit.serverRect.x1 ||
           draftImageEdit.rect.y1 !== draftImageEdit.serverRect.y1) && (
            <div
              className="image-edit-original-mask"
              style={{
                left: draftImageEdit.serverRect.x0 * zoom,
                top: draftImageEdit.serverRect.y0 * zoom,
                width: (draftImageEdit.serverRect.x1 - draftImageEdit.serverRect.x0) * zoom,
                height: (draftImageEdit.serverRect.y1 - draftImageEdit.serverRect.y0) * zoom,
                background: draftImageEdit.bgColor || "#ffffff",
              }}
            />
          )
        )}

        {editMode === "image" && draftImageEdit && (
          <ImageEditBox
            key={draftImageEdit.key}
            rect={draftImageEdit.rect}
            zoom={zoom}
            previewUrl={draftImageEdit.previewUrl}
            canReplace={draftImageEdit.kind === "existing"}
            keepAspect={!!draftImageEdit.barcode}
            onRectChange={onDraftImageRectChange}
            onReplaceFile={onImageReplaceFile}
            onConfirm={onCommitImageEdit}
            onCancel={onCancelImageEdit}
            onDelete={onDeleteImageEdit}
          />
        )}

        {/* กล่องลาก/ย้าย/ย่อ/ขยายตำแหน่งลายเซ็น (Electronic Sign / Digital Sign — ผู้ใช้แจ้งขอ) — เป็น
            อิสระจาก editMode ข้างบนโดยตั้งใจ ใช้งานได้ไม่ว่า activeTool/editMode ตอนนี้จะเป็นอะไร ตราบใด
            ที่ App.jsx เปิด draftSignature ไว้ (เปิดโมดัลเลือก/สร้างลายเซ็นสำเร็จแล้วรอผู้ใช้ลากวาง) */}
        {draftSignature && (
          <ImageEditBox
            key="signature-draft"
            rect={draftSignature.rect}
            zoom={zoom}
            previewUrl={draftSignature.previewUrl}
            canReplace={false}
            onRectChange={onDraftSignatureRectChange}
            onConfirm={onCommitSignature}
            onCancel={onCancelSignature}
          />
        )}
      </div>
    </div>
  );
});

export default PDFCanvas;
