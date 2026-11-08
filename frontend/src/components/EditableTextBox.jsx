import React, { useEffect, useRef } from "react";
import { fontFamilyForKey, fontWeightForKey, fontStyleForKey } from "../utils/textEditUtils.js";

/**
 * EditableTextBox — กล่องข้อความที่กำลังแก้ไขอยู่ แสดงทับตำแหน่งเดิมบนหน้า PDF โดยตรง
 * (ไม่ต้องพิมพ์ผ่าน textarea ในแถบ properties อีกต่อไป — พิมพ์แก้ที่หน้าจอได้เลย)
 *
 * - แก้ข้อความ: ใช้ contentEditable ธรรมดา ตั้งค่าเริ่มต้นแค่ตอน mount ครั้งเดียว (useEffect deps ว่าง)
 *   แล้วปล่อยให้เป็น DOM ที่ควบคุมตัวเอง (uncontrolled) ไม่ sync ค่ากลับจาก React ทุก keystroke —
 *   ถ้า sync ทุกครั้งจะเจอปัญหา cursor กระโดดไปต้นข้อความเวลาพิมพ์ (ปัญหาคลาสสิกของ contentEditable+React)
 *   ฝั่งเรียกใช้ (PDFCanvas/App.jsx) ต้อง key={blockId} กำกับไว้ให้ remount ใหม่ทุกครั้งที่เปลี่ยนย่อหน้า
 * - ย่อ/ขยายกล่อง: ลากที่ handle เล็กๆ รอบกล่อง (มุม/ขอบ) แปลง delta พิกเซลบนจอกลับเป็นหน่วย point
 *   ของ PDF (หาร zoom) แล้วส่ง rect ใหม่ขึ้นไปให้ parent เก็บเป็น draft (ยังไม่ save จนกว่าจะกดบันทึก)
 * - ย้ายตำแหน่ง: ลากที่ "จุดจับย้าย" (grip) ด้านบนกล่อง แปลง delta เหมือนกันแต่เลื่อนทั้งกล่อง (คงขนาด
 *   เดิม) แยกจากพื้นที่พิมพ์ข้อความ เพื่อไม่ให้ชนกับการคลิกวาง cursor ในเนื้อข้อความ
 * - พื้นหลังทึบ (bgColor): เดิมกล่องนี้ใช้พื้นหลังโปร่งแสง ทำให้ข้อความเดิมในรูปหน้าเอกสาร (ซึ่งยังไม่ถูก
 *   redact จริงจนกว่าจะกดบันทึก) โผล่ทะลุมาปนกับข้อความใหม่ที่กำลังพิมพ์ ดูเหมือนตัวอักษรซ้อนทับกันเละ —
 *   ทางแก้คือรับสีพื้นหลังที่สุ่มมาจากหน้าเอกสารจริง (ดู utils/bgSample.js) มาทาทึบทั้งกล่อง กันข้อความ
 *   เดิมทะลุขึ้นมา (fallback เป็นขาวทึบถ้าสุ่มไม่สำเร็จ)
 * - readOnly (โหมดพรีวิว): ใช้แสดงย่อหน้าที่กด "ตกลง" ไปแล้วแต่ยังไม่กด "บันทึกการแก้ไข" — ต้องโชว์
 *   ข้อความ "ใหม่" ที่เพิ่งแก้ (ไม่ใช่ข้อความเดิมในไฟล์) คลิกที่กล่องเพื่อกลับไปแก้ไขต่อได้
 */

const HANDLES = [
  { dir: "nw", cursor: "nwse-resize" },
  { dir: "n", cursor: "ns-resize" },
  { dir: "ne", cursor: "nesw-resize" },
  { dir: "e", cursor: "ew-resize" },
  { dir: "se", cursor: "nwse-resize" },
  { dir: "s", cursor: "ns-resize" },
  { dir: "sw", cursor: "nesw-resize" },
  { dir: "w", cursor: "ew-resize" },
];

const MIN_SIZE_PT = 10;

export default function EditableTextBox({
  rect,
  zoom,
  text,
  fontKey,
  fontSize,
  colorHex,
  align = "left", // จัดตัวหนังสือ left/center/right (ผู้ใช้แจ้งเพิ่ม) — ใช้ทั้งตอนพิมพ์แก้สดๆ และพรีวิว
  valign = "top", // จัดแนวตั้ง top/middle/bottom (ผู้ใช้แจ้งเพิ่ม)
  underline = false, // ขีดเส้นใต้ (ผู้ใช้แจ้งเพิ่ม) — พรีวิวสดๆ ด้วย CSS text-decoration เหมือนกับที่
                      // fontWeightForKey/fontStyleForKey พรีวิวตัวหนา/เอียงอยู่แล้ว (ของจริงตอน save จะ
                      // วาดเป็นเส้นแยกต่างหากฝั่ง backend ผ่าน edit_service.replace_text)
  bgColor,        // สีพื้นหลังทึบที่สุ่มมาจากหน้าเอกสารจริง (ดูหมายเหตุด้านบน) — undefined ก็ fallback ขาวทึบ
  onTextChange,
  onRectChange,
  onCancel,
  onDelete,
  readOnly = false, // true = แค่พรีวิวย่อหน้าที่ "ตกลง" ไว้แล้ว ยังไม่กด "บันทึกการแก้ไข" — คลิกกลับไปแก้ต่อ
  pending = false,  // true = ใส่ style เตือนว่ายังไม่กดบันทึกจริง (กรอบส้ม) ใช้คู่กับ readOnly เท่านั้น
  onSelect,         // ใช้ตอน readOnly — คลิกกล่องเพื่อกลับไปแก้ไขต่อ
}) {
  const textRef = useRef(null);

  // ตั้งค่าข้อความเริ่มต้นแค่ตอน mount (component นี้ถูก remount ใหม่ทุกครั้งที่เปลี่ยนย่อหน้าที่แก้
  // ผ่าน key={blockId} จากฝั่งเรียกใช้ — ดูหมายเหตุด้านบน) ข้ามขั้นตอนนี้ถ้าเป็นแค่โหมดพรีวิว (readOnly)
  useEffect(() => {
    if (readOnly) return;
    if (textRef.current) {
      textRef.current.innerText = text;
      // วาง cursor ไว้ท้ายข้อความให้พิมพ์ต่อได้ทันที
      textRef.current.focus({ preventScroll: true });
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(textRef.current);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    }
    syncHeightToContent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // แก้บั๊กที่ผู้ใช้แจ้ง (ดูหมายเหตุยาวใน edit_service.py "แก้บั๊กสำคัญ #8"): เลือกฟอนต์/ขนาดใหญ่ขึ้น
  // โดยไม่ได้ลากขยายกล่องเอง ทำให้ข้อความจริงต้องขึ้นหลายบรรทัดกว่าที่กล่องเดิม (สืบทอดขนาดจากฟอนต์เก่า)
  // จะรับไหว — ต้องขยาย rect.y1 ให้พอดีกับเนื้อหาจริงเสมอ ไม่ใช่แค่ตอนบันทึกจริง (backend ก็ขยายให้เช่น
  // กัน เป็น source of truth ตัวสุดท้าย) แต่ต้องขยายตั้งแต่ตอนกำลังพิมพ์ด้วย ให้ผู้ใช้เห็นผลตรงกับที่จะ
  // บันทึกจริงทันที (WYSIWYG) วัดจาก scrollHeight ของกล่อง (สะท้อนความสูงเนื้อหาจริงเสมอ ไม่ขึ้นกับ
  // overflow/height ที่ตั้งไว้) แปลงกลับเป็นหน่วย point ด้วย zoom ปัจจุบัน ขยายเฉพาะตอนเนื้อหาสูงกว่ากล่อง
  // เดิมเท่านั้น — ไม่ย่อกล่องอัตโนมัติถ้าพิมพ์สั้นลงหรือลดขนาดฟอนต์ลง (ผู้ใช้ลากย่อเองได้เสมอถ้าต้องการ
  // กันกล่องเด้งเล็กลงกะทันหันจนงงตอนพิมพ์ — สอดคล้องกับดีไซน์เดิมที่ไม่ auto-shrink ฟอนต์ให้เองเช่นกัน)
  function syncHeightToContent() {
    if (readOnly || !textRef.current) return;
    const neededPt = textRef.current.scrollHeight / zoom;
    const currentHeightPt = rect.y1 - rect.y0;
    if (neededPt > currentHeightPt + 0.5) {
      onRectChange({ ...rect, y1: rect.y0 + neededPt });
    }
  }

  // เปลี่ยนฟอนต์/ขนาด/จัดตัวหนังสือ/ขีดเส้นใต้ ล้วนกระทบจำนวนบรรทัดที่ต้องใช้ (ไม่ได้มาจากการพิมพ์ — ไม่
  // ผ่าน onInput) วัดใหม่ทุกครั้งที่ค่าพวกนี้เปลี่ยน (requestAnimationFrame กันวัดก่อน browser reflow
  // ตาม style ใหม่เสร็จจริง) *ไม่* ใส่ rect ใน deps กันเรียกตัวเองวนซ้ำตอนเราเป็นคน setRect เอง
  useEffect(() => {
    const raf = requestAnimationFrame(syncHeightToContent);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fontKey, fontSize, align, underline, zoom]);

  function startResize(e, dir) {
    e.stopPropagation();
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...rect };

    function onMove(ev) {
      const dxPt = (ev.clientX - startX) / zoom;
      const dyPt = (ev.clientY - startY) / zoom;
      let { x0, y0, x1, y1 } = startRect;
      if (dir.includes("w")) x0 = Math.min(startRect.x1 - MIN_SIZE_PT, startRect.x0 + dxPt);
      if (dir.includes("e")) x1 = Math.max(startRect.x0 + MIN_SIZE_PT, startRect.x1 + dxPt);
      if (dir.includes("n")) y0 = Math.min(startRect.y1 - MIN_SIZE_PT, startRect.y0 + dyPt);
      if (dir.includes("s")) y1 = Math.max(startRect.y0 + MIN_SIZE_PT, startRect.y1 + dyPt);
      onRectChange({ x0, y0, x1, y1 });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  // ลากย้ายทั้งกล่อง (คงขนาดเดิม) — แยกจาก startResize ข้างบน ใช้จุดจับ (grip) เล็กๆ เหนือกล่องแทน
  function startMove(e) {
    e.stopPropagation();
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...rect };
    const w = startRect.x1 - startRect.x0;
    const h = startRect.y1 - startRect.y0;

    function onMove(ev) {
      const dxPt = (ev.clientX - startX) / zoom;
      const dyPt = (ev.clientY - startY) / zoom;
      const x0 = startRect.x0 + dxPt;
      const y0 = startRect.y0 + dyPt;
      onRectChange({ x0, y0, x1: x0 + w, y1: y0 + h });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  const boxStyle = {
    left: rect.x0 * zoom,
    top: rect.y0 * zoom,
    width: (rect.x1 - rect.x0) * zoom,
    height: (rect.y1 - rect.y0) * zoom,
    background: bgColor || "#ffffff",
  };

  const textStyle = {
    fontFamily: fontFamilyForKey(fontKey),
    fontWeight: fontWeightForKey(fontKey),
    fontStyle: fontStyleForKey(fontKey),
    fontSize: Math.max(6, fontSize * zoom),
    color: colorHex,
    textAlign: align || "left",
    display: "flex",
    flexDirection: "column",
    justifyContent: valign === "middle" ? "center" : valign === "bottom" ? "flex-end" : "flex-start",
    textDecoration: underline ? "underline" : "none",
  };

  if (readOnly) {
    return (
      <div
        className={`edit-box-active edit-box-preview ${pending ? "edit-box-preview-pending" : ""}`}
        style={boxStyle}
        onClick={(e) => {
          e.stopPropagation();
          onSelect?.();
        }}
        title="คลิกเพื่อแก้ไขย่อหน้านี้ต่อ"
      >
        <div className="edit-inline-text edit-inline-text-preview" style={textStyle}>
          {text}
        </div>
      </div>
    );
  }

  return (
    <div className="edit-box-active" style={boxStyle} onClick={(e) => e.stopPropagation()}>
      <button
        className="absolute -bottom-[22px] left-1/2 -translate-x-1/2 w-4 h-4 bg-red-500 hover:bg-red-600 text-white rounded-full flex items-center justify-center shadow z-10 cursor-pointer"
        title="ลบกล่องข้อความนี้ (Ctrl + Delete)"
        onClick={(e) => {
          e.stopPropagation();
          onDelete?.();
        }}
      >
        <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
      </button>
      <div className="edit-box-drag-handle" title="ลากเพื่อย้ายตำแหน่ง" onPointerDown={startMove}>
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
          <path d="M8 1v14M1 8h14" stroke="white" strokeWidth="1.4" strokeLinecap="round" />
          <path
            d="M8 1L5.5 3.5M8 1l2.5 2.5M8 15l-2.5-2.5M8 15l2.5-2.5M1 8l2.5-2.5M1 8l2.5 2.5M15 8l-2.5-2.5M15 8l2.5 2.5"
            stroke="white"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <div
        ref={textRef}
        className="edit-inline-text"
        contentEditable
        suppressContentEditableWarning
        style={textStyle}
        onInput={() => {
          onTextChange(textRef.current.innerText);
          syncHeightToContent();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.currentTarget.blur();
            onCancel?.();
          }
          if ((e.key === "Delete" || e.key === "Backspace") && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            e.currentTarget.blur();
            onDelete?.();
          }
        }}
      />
      {HANDLES.map((h) => (
        <div
          key={h.dir}
          className={`resize-handle handle-${h.dir}`}
          style={{ cursor: h.cursor }}
          onPointerDown={(e) => startResize(e, h.dir)}
        />
      ))}
    </div>
  );
}
