// แสดงหน้าเอกสาร 1 หน้า + กล่องลายเซ็นทับด้านบน
// - placing: คลิกบนหน้าเพื่อวางกล่องใหม่ (onPlace(xPt, yPt)) — ถ้าส่ง ghost {width, height, label, className} มาด้วย
//   จะมีกล่องตัวอย่างลอยตามเมาส์ให้เห็นตำแหน่งก่อนคลิก
// - กล่องที่ editable ลากย้าย/ปรับขนาด (มุมขวาล่าง) ได้ (onBoxChange(id, rect))
import { useRef, useState } from "react";
import { useAuthedImage } from "./useAuthedImage.js";

const MIN_W = 40;
const MIN_H = 20;

export default function SignaturePagePreview({
  imageUrl,
  pageWidthPt,
  pageHeightPt,
  scale,
  boxes = [],
  placing = false,
  ghost = null,
  onPlace,
  onBoxChange,
}) {
  const src = useAuthedImage(imageUrl);
  const sheetRef = useRef(null);
  const [hover, setHover] = useState(null); // ตำแหน่งเมาส์ (pt) ระหว่างวางกล่อง
  const widthPx = pageWidthPt * scale;
  // ตัวอักษรในกล่องย่อตามหน้า (มือถือ) แต่ไม่เล็กกว่า 8px
  const labelStyle = { fontSize: Math.max(8, Math.min(11, 11 * scale)) };
  const heightPx = pageHeightPt * scale;

  function toPt(ev) {
    const r = sheetRef.current.getBoundingClientRect();
    return [(ev.clientX - r.left) / scale, (ev.clientY - r.top) / scale];
  }

  function startDrag(ev, box, mode) {
    if (!box.editable || !onBoxChange) return;
    ev.preventDefault();
    ev.stopPropagation();
    const [sx, sy] = toPt(ev);
    const start = { ...box.rect };
    function onMove(e) {
      const [x, y] = toPt(e);
      const dx = x - sx;
      const dy = y - sy;
      let next;
      if (mode === "move") {
        const w = start.x1 - start.x0;
        const h = start.y1 - start.y0;
        const x0 = Math.min(Math.max(0, start.x0 + dx), pageWidthPt - w);
        const y0 = Math.min(Math.max(0, start.y0 + dy), pageHeightPt - h);
        next = { x0, y0, x1: x0 + w, y1: y0 + h };
      } else {
        next = {
          ...start,
          x1: Math.min(pageWidthPt, Math.max(start.x0 + MIN_W, start.x1 + dx)),
          y1: Math.min(pageHeightPt, Math.max(start.y0 + MIN_H, start.y1 + dy)),
        };
      }
      onBoxChange(box.id, next);
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  return (
    <div
      ref={sheetRef}
      data-testid="signing-page"
      className={`relative bg-white shadow-md mx-auto ${placing ? "cursor-crosshair" : ""}`}
      style={{ width: widthPx, height: heightPx }}
      onClick={(e) => {
        if (!placing || !onPlace) return;
        const [x, y] = toPt(e);
        onPlace(x, y);
      }}
      onPointerMove={(e) => placing && ghost && setHover(toPt(e))}
      onPointerLeave={() => setHover(null)}
    >
      {src ? (
        <img src={src} alt="" draggable={false} className="w-full h-full select-none pointer-events-none" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-sm text-gray-400">กำลังโหลด...</div>
      )}
      {placing && ghost && hover && (() => {
        // จุดเมาส์อยู่กลางกล่อง และกล่องไม่ล้นขอบหน้า (ตรงกับตำแหน่งที่จะวางจริงเมื่อคลิก)
        const x0 = Math.min(Math.max(0, hover[0] - ghost.width / 2), pageWidthPt - ghost.width);
        const y0 = Math.min(Math.max(0, hover[1] - ghost.height / 2), pageHeightPt - ghost.height);
        return (
          <div
            data-testid="signature-ghost"
            className={`absolute border-2 border-dashed rounded-sm text-[11px] leading-tight px-1 pointer-events-none opacity-80 ${ghost.className || "border-blue-500 bg-blue-100/60 text-blue-900"}`}
            style={{ left: x0 * scale, top: y0 * scale, width: ghost.width * scale, height: ghost.height * scale, ...labelStyle }}
          >
            <span className="font-medium">{ghost.label}</span>
          </div>
        );
      })()}
      {boxes.map((box) => (
        <div
          key={box.id}
          data-testid="signature-box"
          className={`absolute border-2 rounded-sm text-[11px] leading-tight px-1 overflow-hidden ${box.className || "border-blue-500 bg-blue-100/60 text-blue-900"} ${box.editable ? "cursor-move" : ""}`}
          style={{
            left: box.rect.x0 * scale,
            top: box.rect.y0 * scale,
            width: (box.rect.x1 - box.rect.x0) * scale,
            height: (box.rect.y1 - box.rect.y0) * scale,
            ...labelStyle,
          }}
          onPointerDown={(e) => startDrag(e, box, "move")}
          onClick={(e) => e.stopPropagation()}
          title={box.label}
        >
          <span className="font-medium block [overflow-wrap:anywhere]">{box.label}</span>
          {box.editable && (
            <span
              className="absolute right-0 bottom-0 w-3 h-3 bg-blue-600 cursor-se-resize"
              onPointerDown={(e) => startDrag(e, box, "resize")}
            />
          )}
        </div>
      ))}
    </div>
  );
}
