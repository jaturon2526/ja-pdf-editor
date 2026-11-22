import React from "react";
import { applyHandleDrag, ptToMm } from "../../utils/cropGeometry.js";

const HANDLES = [
  { id: "nw", cursor: "nwse-resize", style: { left: -12, top: -12 } },
  { id: "ne", cursor: "nesw-resize", style: { right: -12, top: -12 } },
  { id: "sw", cursor: "nesw-resize", style: { left: -12, bottom: -12 } },
  { id: "se", cursor: "nwse-resize", style: { right: -12, bottom: -12 } },
  { id: "n", cursor: "ns-resize", style: { left: "50%", top: -11, transform: "translateX(-50%)" } },
  { id: "s", cursor: "ns-resize", style: { left: "50%", bottom: -11, transform: "translateX(-50%)" } },
  { id: "w", cursor: "ew-resize", style: { left: -11, top: "50%", transform: "translateY(-50%)" } },
  { id: "e", cursor: "ew-resize", style: { right: -11, top: "50%", transform: "translateY(-50%)" } },
];

/**
 * กรอบตัดขอบหน้ากระดาษแบบโต้ตอบได้บน PDFCanvas
 * แสดงพื้นที่มืดรอบนอก + เส้นประสีน้ำเงิน + ปุ่มจับ 8 จุดรองรับเมาส์และนิ้วสัมผัส
 */
export default function CropPageLayer({
  margins,
  zoom,
  pageWidthPt,
  pageHeightPt,
  onChange,
}) {
  const leftPx = margins.left * zoom;
  const topPx = margins.top * zoom;
  const rightPx = margins.right * zoom;
  const bottomPx = margins.bottom * zoom;
  const pageWPx = pageWidthPt * zoom;
  const pageHPx = pageHeightPt * zoom;
  const cropWPx = Math.max(12, pageWPx - leftPx - rightPx);
  const cropHPx = Math.max(12, pageHPx - topPx - bottomPx);

  const remainW = ptToMm(Math.max(0, pageWidthPt - margins.left - margins.right));
  const remainH = ptToMm(Math.max(0, pageHeightPt - margins.top - margins.bottom));

  function startDrag(handleId, e) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const startMargins = { ...margins };
    const pointerId = e.pointerId;

    function onMove(ev) {
      if (ev.pointerId !== pointerId) return;
      const dxPt = (ev.clientX - startX) / zoom;
      const dyPt = (ev.clientY - startY) / zoom;
      onChange(applyHandleDrag(startMargins, handleId, dxPt, dyPt, pageWidthPt, pageHeightPt));
    }

    function onUp(ev) {
      if (ev.pointerId !== pointerId) return;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }

  return (
    <div
      className="absolute inset-0 z-30 pointer-events-none select-none"
      data-testid="crop-page-layer"
    >
      {/* แถบมืด 4 ด้านนอกกรอบตัดขอบ */}
      <div className="absolute left-0 right-0 top-0 bg-slate-900/45" style={{ height: topPx }} />
      <div className="absolute left-0 right-0 bottom-0 bg-slate-900/45" style={{ height: bottomPx }} />
      <div className="absolute left-0 bg-slate-900/45" style={{ top: topPx, width: leftPx, height: cropHPx }} />
      <div className="absolute right-0 bg-slate-900/45" style={{ top: topPx, width: rightPx, height: cropHPx }} />

      {/* กรอบตัดขอบสีน้ำเงิน */}
      <div
        className="absolute border-2 border-dashed border-blue-500 shadow-[0_0_0_1px_rgba(255,255,255,0.8)]"
        style={{ left: leftPx, top: topPx, width: cropWPx, height: cropHPx }}
      >
        {/* ป้ายแสดงขนาดหลังตัด (มม.) */}
        <div className="absolute left-1/2 top-2 -translate-x-1/2 px-2 py-0.5 rounded-full bg-blue-600/90 text-white text-[11px] font-medium whitespace-nowrap shadow">
          {remainW} × {remainH} มม.
        </div>

        {/* ปุ่มจับ 8 จุด (4 มุม + 4 ขอบ) */}
        {HANDLES.map((h) => (
          <div
            key={h.id}
            role="presentation"
            data-crop-handle={h.id}
            onPointerDown={(e) => startDrag(h.id, e)}
            className="absolute w-6 h-6 flex items-center justify-center pointer-events-auto touch-none"
            style={{ ...h.style, cursor: h.cursor }}
          >
            <span className="w-3 h-3 rounded-full bg-white border-2 border-blue-600 shadow" />
          </div>
        ))}
      </div>
    </div>
  );
}
