import React, { useEffect, useRef, useState } from "react";

/**
 * AnnotationBox — คลิกเลือก annotation ที่มีอยู่แล้วในหน้า (ไฮไลท์ / กรอบสี่เหลี่ยม / กล่องข้อความ /
 * โน้ต) เพื่อแก้ไข/ลบ/เปลี่ยนสี (ผู้ใช้แจ้งเพิ่มในรอบนี้ — ดู App.jsx handleSelectAnnotation)
 *
 * เนื้อหา/สี/กรอบของ annotation ที่ "ยังไม่ได้เลือก" ถูกวาดโดย backend ทับลงในรูปหน้าเอกสารอยู่แล้ว
 * (เหมือน annotation อื่นๆ ในแอปนี้) component นี้ตอน "ไม่ได้เลือก" จึงเป็นแค่ชั้น "จุดคลิก" โปร่งใส/
 * จางๆ ทับตำแหน่งเดิม (เหมือน .edit-box ตอนแก้ไขข้อความ) ไม่ได้วาดซ้ำเนื้อหาจริง — ตอน "เลือกอยู่"
 * (editing=true) ถึงจะโชว์กรอบ+handle ย่อ/ขยาย+จุดจับย้าย+toolbar สี/ลบ/ตกลง/ยกเลิก (เหมือนแนวทาง
 * EditableTextBox/ImageEditBox ที่มีอยู่แล้วในแอป — ดราฟต์ในเครื่องก่อน ยังไม่ยิง API จนกว่าจะกด "ตกลง")
 *
 * โน้ต (text_note) ต่างจากชนิดอื่น: ไม่มีปุ่มย่อ/ขยาย (เป็นแค่ไอคอนตำแหน่งเดียว) hover แล้วโชว์เนื้อหา
 * ในลูกโป่ง (balloon) แบบเดียวกับ tooltip ปกติของโปรแกรมอ่าน PDF ทั่วไป
 */

const RESIZABLE_TYPES = ["highlight", "rect", "freetext"];
const TEXTUAL_TYPES = ["freetext"];
const COLOR_SWATCHES = ["#ffe066", "#ff6b6b", "#51cf66", "#339af0", "#1b2130"];

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
const MIN_SIZE_PT = 8;

function hexToRgba(hex, alpha) {
  const n = parseInt((hex || "ffe04d").replace("#", ""), 16) || 0xffe04d;
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

export default function AnnotationBox({
  annot,
  zoom,
  editing,
  draftRect,
  draftContent,
  draftColorHex,
  draftFontKey,
  draftFontSize,
  fonts,
  onSelect,
  onDraftRectChange,
  onDraftContentChange,
  onDraftColorChange,
  onDraftFontKeyChange,
  onDraftFontSizeChange,
  onCommit,
  onCancel,
  onDelete,
}) {
  const [hover, setHover] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const textRef = useRef(null);

  const rect = editing ? draftRect : annot.rect;
  const isNote = annot.type === "text_note";
  const isTextual = TEXTUAL_TYPES.includes(annot.type);
  const resizable = RESIZABLE_TYPES.includes(annot.type);
  // ปรับ font/ขนาดตัวอักษรได้เฉพาะ "กล่องข้อความ" (freetext) เท่านั้น (ผู้ใช้แจ้งเพิ่ม) — กรอบสี่เหลี่ยม
  // (rect) ยังคง font/ขนาดตายตัวเหมือนเดิม เปลี่ยนได้แค่สีกรอบผ่าน COLOR_SWATCHES ด้านล่างตามปกติ
  const isFreetext = annot.type === "freetext";

  // ตั้งค่าข้อความเริ่มต้นแค่ตอน "เริ่มแก้ไข" (editing เปลี่ยนจาก false เป็น true) — component นี้ไม่
  // remount ใหม่ตอนเลือก annotation เดิม (key={annot.xref} เหมือนกันทั้งตอนเลือก/ไม่เลือก — ต่างจาก
  // EditableTextBox ที่ remount ทุกครั้ง) จึงต้องใช้ dependency [editing] แทน [] เพื่อ initialize
  // เนื้อหาให้ contentEditable ใหม่ทุกครั้งที่เพิ่งเข้าสู่โหมดแก้ไข ไม่ใช่แค่ตอน mount ครั้งแรก
  useEffect(() => {
    if (editing && isTextual && textRef.current) {
      textRef.current.innerText = draftContent || "";
      textRef.current.focus({ preventScroll: true });
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(textRef.current);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  function startResize(e, dir) {
    e.stopPropagation();
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...draftRect };
    function onMove(ev) {
      const dxPt = (ev.clientX - startX) / zoom;
      const dyPt = (ev.clientY - startY) / zoom;
      let { x0, y0, x1, y1 } = startRect;
      if (dir.includes("w")) x0 = Math.min(startRect.x1 - MIN_SIZE_PT, startRect.x0 + dxPt);
      if (dir.includes("e")) x1 = Math.max(startRect.x0 + MIN_SIZE_PT, startRect.x1 + dxPt);
      if (dir.includes("n")) y0 = Math.min(startRect.y1 - MIN_SIZE_PT, startRect.y0 + dyPt);
      if (dir.includes("s")) y1 = Math.max(startRect.y0 + MIN_SIZE_PT, startRect.y1 + dyPt);
      onDraftRectChange({ x0, y0, x1, y1 });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function startMove(e) {
    e.stopPropagation();
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...draftRect };
    const w = startRect.x1 - startRect.x0;
    const h = startRect.y1 - startRect.y0;
    function onMove(ev) {
      const dxPt = (ev.clientX - startX) / zoom;
      const dyPt = (ev.clientY - startY) / zoom;
      const x0 = startRect.x0 + dxPt;
      const y0 = startRect.y0 + dyPt;
      onDraftRectChange({ x0, y0, x1: x0 + w, y1: y0 + h });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  // ---------- โน้ต (text_note): ตำแหน่งเดียว — hover โชว์ balloon, คลิกเพื่อแก้ไข, ลากเพื่อย้าย ----------
  if (isNote) {
    const hitW = Math.max(18, (rect.x1 - rect.x0) * zoom);
    const hitH = Math.max(18, (rect.y1 - rect.y0) * zoom);

    function startNoteMove(e) {
      if (editing) { e.stopPropagation(); return; }
      e.stopPropagation();
      e.preventDefault();
      const startX = e.clientX;
      const startY = e.clientY;
      const startRect = { ...annot.rect }; // เริ่มจากตำแหน่งจริง ไม่ใช่ draftRect
      const w = startRect.x1 - startRect.x0;
      const h = startRect.y1 - startRect.y0;
      let dragging = false;

      function onMove(ev) {
        const px = Math.hypot(ev.clientX - startX, ev.clientY - startY);
        if (!dragging && px > 5) {
          dragging = true;
          onSelect(annot); // เริ่ม draft → editing เปลี่ยนเป็น true + draftRect ถูก init
        }
        if (dragging) {
          const dxPt = (ev.clientX - startX) / zoom;
          const dyPt = (ev.clientY - startY) / zoom;
          const x0 = startRect.x0 + dxPt;
          const y0 = startRect.y0 + dyPt;
          onDraftRectChange({ x0, y0, x1: x0 + w, y1: y0 + h });
        }
      }

      function onUp() {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        if (!dragging) {
          // เป็นแค่คลิกปกติ (ไม่ได้ลาก) → เปิด editor
          onSelect(annot);
        }
        // ถ้าลากแล้ว → editor เปิดอยู่ที่ตำแหน่งใหม่แล้ว กด "ตกลง" เพื่อบันทึก
      }

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    }

    return (
      <div
        className={`annot-note-marker ${editing ? "selected" : ""}`}
        style={{
          left: rect.x0 * zoom,
          top: rect.y0 * zoom,
          width: hitW,
          height: hitH,
          cursor: editing ? "default" : "grab",
        }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        onPointerDown={startNoteMove}
        title={editing ? undefined : "คลิกเพื่อแก้ไข / ลากเพื่อย้ายตำแหน่ง"}
      >
        {hover && !editing && annot.content && <div className="annot-note-balloon">{annot.content}</div>}
        {editing && (
          <div className="annot-note-editor" onClick={(e) => e.stopPropagation()}>
            <textarea
              ref={(el) => {
                if (el && editing) {
                  // ใช้ setTimeout และ preventScroll เพื่อไม่ให้เด้งลงล่างสุด (autoFocus ทำหน้าเพี้ยน)
                  setTimeout(() => el.focus({ preventScroll: true }), 10);
                }
              }}
              rows={3}
              value={draftContent}
              onChange={(e) => onDraftContentChange(e.target.value)}
              placeholder="ข้อความในโน้ต..."
            />
            <div className="annot-editor-actions">
              {confirmDelete ? (
                <>
                  <span style={{ fontSize: "12px", color: "var(--color-danger, #ef4444)", marginRight: "auto" }}>
                    ยืนยันการลบ?
                  </span>
                  <button className="secondary-btn annot-toolbar-btn" onClick={() => setConfirmDelete(false)}>
                    ยกเลิก
                  </button>
                  <button className="annot-danger-btn annot-toolbar-btn" onClick={onDelete}>
                    ใช่, ลบเลย
                  </button>
                </>
              ) : (
                <>
                  <button className="secondary-btn annot-toolbar-btn" onClick={onCancel}>
                    ยกเลิก
                  </button>
                  <button className="annot-danger-btn annot-toolbar-btn" onClick={() => setConfirmDelete(true)}>
                    ลบ
                  </button>
                  <button className="primary-btn annot-toolbar-btn" onClick={onCommit}>
                    ตกลง
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }


  // ---------- ไฮไลท์ / กรอบสี่เหลี่ยม / กล่องข้อความ ----------
  const boxStyle = {
    left: rect.x0 * zoom,
    top: rect.y0 * zoom,
    width: Math.max(2, (rect.x1 - rect.x0) * zoom),
    height: Math.max(2, (rect.y1 - rect.y0) * zoom),
  };
  if (editing) {
    // กล่องข้อความ: พื้นขาวทึบ บังข้อความเดิมในรูปหน้าเอกสารระหว่างพิมพ์ (ไม่ให้เห็นซ้อนสองชั้น)
    // กรอบสี่เหลี่ยม: โปร่งแสงเล็กน้อย (มักวาดล้อมเนื้อหาเดิม ต้องยังเห็นข้างใน)
    boxStyle.background = annot.type === "highlight" ? hexToRgba(draftColorHex, 0.35)
      : annot.type === "freetext" ? "#fff" : "rgba(255,255,255,0.85)";
    // กล่องข้อความ: กรอบบางสีเดียวกับกล่องแก้ไขตัวอักษร (สีตัวอักษรไม่ใช่สีกรอบ) — ไฮไลท์/กรอบสี่เหลี่ยมยังโชว์สีที่เลือก
    if (annot.type !== "freetext") boxStyle.borderColor = draftColorHex;
  }

  return (
    <div
      className={`annot-box annot-box-${annot.type} ${editing ? "editing" : ""}`}
      style={boxStyle}
      onClick={(e) => {
        e.stopPropagation();
        if (!editing) onSelect(annot);
      }}
      onPointerDown={(e) => e.stopPropagation()}
      title={editing ? undefined : "คลิกเพื่อแก้ไข/ลบ annotation นี้"}
    >
      {editing && isTextual && (
        <div
          ref={textRef}
          className="annot-box-text"
          contentEditable
          suppressContentEditableWarning
          onInput={() => onDraftContentChange(textRef.current.innerText)}
          onClick={(e) => e.stopPropagation()}
        />
      )}
      {/* ไม่แก้ไขอยู่: ข้อความอยู่ในรูปหน้าเอกสารแล้ว (appearance ในไฟล์จริง — ดู backend annotation_service
          _set_text_appearance) จึงไม่วาดทับซ้ำ หน้าจอจึงตรงกับไฟล์ที่ดาวน์โหลด/พิมพ์ */}
      {editing && (
        <>
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
          {resizable &&
            HANDLES.map((h) => (
              <div
                key={h.dir}
                className={`resize-handle handle-${h.dir}`}
                style={{ cursor: h.cursor }}
                onPointerDown={(e) => startResize(e, h.dir)}
              />
            ))}
          <div className="annot-toolbar" onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
            {isFreetext && (
              <div className="annot-toolbar-row">
                <select
                  className="annot-font-select"
                  value={draftFontKey || ""}
                  onChange={(e) => onDraftFontKeyChange(e.target.value)}
                  title="ฟอนต์ของกล่องข้อความ"
                >
                  {(fonts || []).map((f) => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  className="annot-font-size"
                  min={6}
                  max={96}
                  value={draftFontSize ?? 12}
                  onChange={(e) => onDraftFontSizeChange(parseFloat(e.target.value) || 12)}
                  title="ขนาดตัวอักษร"
                />
              </div>
            )}
            <div className="annot-toolbar-row">
              {COLOR_SWATCHES.map((c) => (
                <button
                  key={c}
                  className={`annot-color-swatch ${draftColorHex?.toLowerCase() === c ? "active" : ""}`}
                  style={{ background: c }}
                  onClick={() => onDraftColorChange(c)}
                  title={c}
                />
              ))}
            </div>
            <div className="annot-toolbar-row" style={{ justifyContent: "flex-end", marginTop: "4px" }}>
              {confirmDelete ? (
                <>
                  <span style={{ fontSize: "12px", color: "var(--color-danger, #ef4444)", marginRight: "auto" }}>
                    ยืนยันการลบ?
                  </span>
                  <button className="secondary-btn annot-toolbar-btn" onClick={() => setConfirmDelete(false)}>
                    ยกเลิก
                  </button>
                  <button className="annot-danger-btn annot-toolbar-btn" onClick={onDelete}>
                    ใช่, ลบเลย
                  </button>
                </>
              ) : (
                <>
                  <button className="secondary-btn annot-toolbar-btn" onClick={onCancel}>
                    ยกเลิก
                  </button>
                  <button className="annot-danger-btn annot-toolbar-btn" onClick={() => setConfirmDelete(true)}>
                    ลบ
                  </button>
                  <button className="primary-btn annot-toolbar-btn" onClick={onCommit}>
                    ตกลง
                  </button>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
