import React, { useRef } from "react";

/**
 * ImageEditBox — กล่องแก้ไขรูปภาพที่กำลังเลือกอยู่ตอนนี้ (แทรกใหม่ หรือ ย้าย/ปรับขนาดรูปเดิม)
 * ใช้แนวทางเดียวกับ EditableTextBox (ลาก handle รอบกล่องเพื่อย่อ/ขยาย, ลาก grip เพื่อย้ายตำแหน่ง)
 * แต่โชว์รูปจริง (<img>) แทนข้อความ พร้อมแถบเครื่องมือเล็กๆ ใต้กล่อง (แทนที่รูป / ตกลง / ยกเลิก)
 *
 * previewUrl มาจาก 2 แหล่งแล้วแต่กรณี:
 *   - รูปที่มีอยู่แล้วในหน้า (ยังไม่เปลี่ยนเนื้อรูป): blob: URL ที่ดึงจาก backend ผ่าน api.fetchImageRawObjectUrl (ต้องแนบ token) โหลดเนื้อรูปจริง
 *   - รูปที่เพิ่งแทรกใหม่ หรือกด "แทนที่รูปภาพ" เลือกไฟล์ใหม่: blob: URL จาก URL.createObjectURL(file)
 *     (ฝั่ง App.jsx เป็นคนสร้าง/เพิกถอน blob URL เหล่านี้ — component นี้แค่โชว์ตาม prop ที่ได้รับ)
 *
 * รูปยืด/บีบเต็มกรอบพอดี (ไม่ใช้ object-fit: contain) ให้ตรงกับพฤติกรรมจริงตอนวาดฝั่ง backend
 * (page.insert_image(..., keep_proportion=False) — ดูหมายเหตุใน edit_service.py) กรอบที่ลาก = ขนาดที่ได้
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

const MIN_SIZE_PT = 12;

export default function ImageEditBox({
  rect,
  zoom,
  previewUrl,
  canReplace = true, // false สำหรับรูปที่เพิ่งแทรกใหม่ยังไม่เคยมี xref จริง (ไม่มีอะไรให้ "แทนที่" อีก)
  onRectChange,
  onReplaceFile,
  onConfirm,
  onCancel,
  onDelete,
  keepAspect = false, // true = คงอัตราส่วนเสมอ (บาร์โค้ด — บีบ/ยืดแล้วสแกนไม่ติด) ไม่ต้องกด Shift
}) {
  const fileInputRef = useRef(null);

  function suppressClickAfterDrag() {
    const handler = (e) => {
      e.stopPropagation();
      e.preventDefault();
    };
    window.addEventListener("click", handler, { capture: true, once: true });
    setTimeout(() => {
      window.removeEventListener("click", handler, { capture: true });
    }, 100);
  }

  function startResize(e, dir) {
    e.stopPropagation();
    e.preventDefault();
    let hasMoved = false;
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...rect };
    const origW = startRect.x1 - startRect.x0;
    const origH = startRect.y1 - startRect.y0;
    const aspectRatio = origW > 0 && origH > 0 ? origW / origH : 1;

    function onMove(ev) {
      hasMoved = true;
      const dxPt = (ev.clientX - startX) / zoom;
      const dyPt = (ev.clientY - startY) / zoom;
      let { x0, y0, x1, y1 } = startRect;
      if (dir.includes("w")) x0 = Math.min(startRect.x1 - MIN_SIZE_PT, startRect.x0 + dxPt);
      if (dir.includes("e")) x1 = Math.max(startRect.x0 + MIN_SIZE_PT, startRect.x1 + dxPt);
      if (dir.includes("n")) y0 = Math.min(startRect.y1 - MIN_SIZE_PT, startRect.y0 + dyPt);
      if (dir.includes("s")) y1 = Math.max(startRect.y0 + MIN_SIZE_PT, startRect.y1 + dyPt);

      // กด Shift ค้างไว้ → คงอัตราส่วนภาพ (aspect ratio) ระหว่างลาก
      if ((ev.shiftKey || keepAspect) && origW > 0 && origH > 0) {
        const newW = x1 - x0;
        const newH = y1 - y0;
        const isCorner = dir.length === 2; // nw / ne / se / sw
        if (isCorner) {
          // มุมทั้งสี่: ใช้ delta ที่ใหญ่กว่าเป็นหลัก อีกด้านปรับตาม
          const wChange = Math.abs(newW - origW);
          const hChange = Math.abs(newH - origH);
          if (wChange >= hChange) {
            const targetH = Math.max(MIN_SIZE_PT, newW / aspectRatio);
            if (dir.includes("n")) y0 = y1 - targetH; else y1 = y0 + targetH;
          } else {
            const targetW = Math.max(MIN_SIZE_PT, newH * aspectRatio);
            if (dir.includes("w")) x0 = x1 - targetW; else x1 = x0 + targetW;
          }
        } else if (dir === "n" || dir === "s") {
          // ลากด้านบน/ล่าง → ปรับความกว้างให้ตรงกัน (ขยายจากกึ่งกลาง)
          const targetW = Math.max(MIN_SIZE_PT, newH * aspectRatio);
          const cx = (startRect.x0 + startRect.x1) / 2;
          x0 = cx - targetW / 2;
          x1 = cx + targetW / 2;
        } else {
          // ลากด้านซ้าย/ขวา → ปรับความสูงให้ตรงกัน (ขยายจากกึ่งกลาง)
          const targetH = Math.max(MIN_SIZE_PT, newW / aspectRatio);
          const cy = (startRect.y0 + startRect.y1) / 2;
          y0 = cy - targetH / 2;
          y1 = cy + targetH / 2;
        }
      }

      onRectChange({ x0, y0, x1, y1 });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (hasMoved) {
        suppressClickAfterDrag();
      }
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function startMove(e) {
    e.stopPropagation();
    e.preventDefault();
    let hasMoved = false;
    const startX = e.clientX;
    const startY = e.clientY;
    const startRect = { ...rect };
    const w = startRect.x1 - startRect.x0;
    const h = startRect.y1 - startRect.y0;
    function onMove(ev) {
      hasMoved = true;
      const dxPt = (ev.clientX - startX) / zoom;
      const dyPt = (ev.clientY - startY) / zoom;
      const x0 = startRect.x0 + dxPt;
      const y0 = startRect.y0 + dyPt;
      onRectChange({ x0, y0, x1: x0 + w, y1: y0 + h });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (hasMoved) {
        suppressClickAfterDrag();
      }
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  React.useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") {
        onCancel?.();
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        onDelete?.();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, onDelete]);

  return (
    <div
      className="image-edit-box"
      style={{
        left: rect.x0 * zoom,
        top: rect.y0 * zoom,
        width: (rect.x1 - rect.x0) * zoom,
        height: (rect.y1 - rect.y0) * zoom,
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        className="absolute -bottom-[22px] left-1/2 -translate-x-1/2 w-4 h-4 bg-red-500 hover:bg-red-600 text-white rounded-full flex items-center justify-center shadow z-10 cursor-pointer"
        title="ลบรูปภาพนี้ (Delete / Backspace)"
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

      {previewUrl && <img src={previewUrl} alt="พรีวิวรูปภาพที่กำลังแก้ไข" className="image-edit-preview" draggable={false}
        onPointerDown={startMove} title="ลากเพื่อย้ายตำแหน่ง" />}

      {HANDLES.map((h) => (
        <div
          key={h.dir}
          className={`resize-handle handle-${h.dir}`}
          style={{ cursor: h.cursor }}
          onPointerDown={(e) => startResize(e, h.dir)}
        />
      ))}

      <div className="image-edit-toolbar" onClick={(e) => e.stopPropagation()}>
        {canReplace && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onReplaceFile(file);
                e.target.value = "";
              }}
            />
            <button className="secondary-btn image-edit-toolbar-btn" onClick={() => fileInputRef.current?.click()}>
              แทนที่รูปภาพ
            </button>
          </>
        )}
        <button className="secondary-btn image-edit-toolbar-btn" onClick={onCancel}>
          ยกเลิก
        </button>
        <button className="primary-btn image-edit-toolbar-btn" onClick={onConfirm}>
          ตกลง
        </button>
      </div>
    </div>
  );
}
