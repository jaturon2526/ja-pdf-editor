// ปรับมุมเอกสาร 4 จุดบนภาพที่ถ่าย — ลากด้วยนิ้ว/เมาส์ มีแว่นขยายตรงจุดที่ลากให้วางมุมได้แม่น
// corners: [{x,y} x4] สัดส่วน 0..1 ของภาพ เรียง บนซ้าย บนขวา ล่างขวา ล่างซ้าย
// v1.41.2: เว้นระยะขอบภาพ (IMAGE_PAD) ไม่ให้จุดมุมชิดขอบจอมือถือ + ขยายพื้นที่จับมุม (HANDLE 88px / รัศมี 140px)
// และลากแบบสัมพัทธ์ (shiftCorner) ให้วางนิ้วถัดเข้ามาในจอแล้วลากได้เลย ไม่ไปโดน gesture ปัดขอบซ้ายย้อนกลับของมือถือ
import { useCallback, useEffect, useRef, useState } from "react";
import { nearestCornerIndex, shiftCorner } from "../../scan/geometry.js";

const IMAGE_PAD = 28; // เว้นระยะจากขอบกล่อง (px) กันจุดมุมชิดขอบซ้าย/ขวาของจอมือถือ
const HANDLE = 88; // พื้นที่แตะรอบจุดมุม (px)
const MAX_GRAB_RADIUS = 140; // รัศมีสูงสุด (px) ที่แตะข้างจุดมุมแล้วดึงมุมที่ใกล้ที่สุดได้ทันที
const LOUPE = 112;
const LOUPE_ZOOM = 2.5;

export default function CornerEditor({ src, corners, onChange }) {
  const boxRef = useRef(null);
  const imgRef = useRef(null);
  const loupeRef = useRef(null);
  const dragSessionRef = useRef(null); // { index, startX, startY, origCorner }
  const [layout, setLayout] = useState(null); // {ox, oy, w, h} กรอบภาพที่แสดงจริงในกล่อง
  const [drag, setDrag] = useState(null); // index ที่กำลังลาก

  const measure = useCallback(() => {
    const box = boxRef.current;
    const img = imgRef.current;
    if (!box || !img || !img.naturalWidth) return;
    const bw = box.clientWidth;
    const bh = box.clientHeight;
    const availW = Math.max(1, bw - IMAGE_PAD * 2);
    const availH = Math.max(1, bh - IMAGE_PAD * 2);
    const s = Math.min(availW / img.naturalWidth, availH / img.naturalHeight);
    const w = img.naturalWidth * s;
    const h = img.naturalHeight * s;
    setLayout({ ox: (bw - w) / 2, oy: (bh - h) / 2, w, h });
  }, []);

  useEffect(() => {
    window.addEventListener("resize", measure);
    window.addEventListener("orientationchange", measure);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("orientationchange", measure);
    };
  }, [measure]);

  // กันเบราว์เซอร์มือถือ (iOS Safari / Android Chrome) ตีความการลากในพื้นที่ปรับมุมเป็นการปัดย้อนกลับหน้าก่อนหน้า
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return undefined;
    const preventEdgeSwipe = (e) => {
      if (e.cancelable) e.preventDefault();
    };
    el.addEventListener("touchstart", preventEdgeSwipe, { passive: false });
    el.addEventListener("touchmove", preventEdgeSwipe, { passive: false });
    return () => {
      el.removeEventListener("touchstart", preventEdgeSwipe);
      el.removeEventListener("touchmove", preventEdgeSwipe);
    };
  }, []);

  const toPx = (c) => ({ x: layout.ox + c.x * layout.w, y: layout.oy + c.y * layout.h });

  function drawLoupe(c) {
    const canvas = loupeRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !layout) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = LOUPE * dpr;
    canvas.height = LOUPE * dpr;
    const ctx = canvas.getContext("2d");
    const srcSize = (LOUPE / LOUPE_ZOOM) * (img.naturalWidth / layout.w);
    ctx.fillStyle = "#111";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, c.x * img.naturalWidth - srcSize / 2, c.y * img.naturalHeight - srcSize / 2, srcSize, srcSize, 0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#22c55e";
    ctx.lineWidth = 2 * dpr;
    const m = canvas.width / 2;
    ctx.beginPath();
    ctx.moveTo(m - 12 * dpr, m); ctx.lineTo(m + 12 * dpr, m);
    ctx.moveTo(m, m - 12 * dpr); ctx.lineTo(m, m + 12 * dpr);
    ctx.stroke();
  }

  function beginDrag(i, e) {
    e.preventDefault();
    e.stopPropagation();
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    dragSessionRef.current = {
      index: i,
      startX: e.clientX,
      startY: e.clientY,
      origCorner: { x: corners[i].x, y: corners[i].y },
    };
    setDrag(i);
    requestAnimationFrame(() => drawLoupe(corners[i]));
  }

  function onBoardPointerDown(e) {
    if (!layout || !boxRef.current) return;
    const rect = boxRef.current.getBoundingClientRect();
    const pointPx = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const ptsPx = corners.map(toPx);
    const nearest = nearestCornerIndex(ptsPx, pointPx, MAX_GRAB_RADIUS);
    if (nearest !== -1) {
      beginDrag(nearest, e);
    }
  }

  function onPointerMove(e) {
    const session = dragSessionRef.current;
    if (!session || !layout) return;
    const i = session.index;
    const moved = shiftCorner(
      session.origCorner,
      { dx: e.clientX - session.startX, dy: e.clientY - session.startY },
      layout,
    );
    const next = corners.map((c, k) => (k === i ? moved : c));
    onChange(next);
    drawLoupe(moved);
  }

  function onPointerUp(e) {
    if (!dragSessionRef.current) return;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
    dragSessionRef.current = null;
    setDrag(null);
  }

  const pts = layout ? corners.map(toPx) : [];
  // แว่นขยายอยู่มุมบนฝั่งตรงข้ามนิ้ว ไม่ให้นิ้วบัง
  const loupeLeft = drag !== null && pts[drag] && pts[drag].x < (boxRef.current?.clientWidth || 0) / 2;

  return (
    <div
      ref={boxRef}
      className="relative w-full h-full select-none touch-none overscroll-none overflow-hidden"
      data-testid="corner-editor"
      onPointerDown={onBoardPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <img ref={imgRef} src={src} alt="ภาพที่ถ่าย" onLoad={measure} draggable={false}
        className="absolute pointer-events-none"
        style={layout ? { left: layout.ox, top: layout.oy, width: layout.w, height: layout.h } : { opacity: 0 }} />
      {layout && (
        <>
          <svg className="absolute inset-0 w-full h-full pointer-events-none">
            <defs>
              <mask id="corner-mask">
                <rect width="100%" height="100%" fill="white" />
                <polygon points={pts.map((p) => `${p.x},${p.y}`).join(" ")} fill="black" />
              </mask>
            </defs>
            <rect width="100%" height="100%" fill="rgba(0,0,0,0.45)" mask="url(#corner-mask)" />
            <polygon points={pts.map((p) => `${p.x},${p.y}`).join(" ")} fill="rgba(34,197,94,0.12)" stroke="#22c55e" strokeWidth="2.5" />
          </svg>
          {pts.map((p, i) => (
            <div
              key={i}
              role="slider"
              aria-label={["มุมบนซ้าย", "มุมบนขวา", "มุมล่างขวา", "มุมล่างซ้าย"][i]}
              aria-valuetext={`${Math.round(corners[i].x * 100)}%, ${Math.round(corners[i].y * 100)}%`}
              tabIndex={0}
              className="absolute flex items-center justify-center"
              style={{ left: p.x - HANDLE / 2, top: p.y - HANDLE / 2, width: HANDLE, height: HANDLE, touchAction: "none", cursor: "grab" }}
              onPointerDown={(e) => beginDrag(i, e)}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              <span className={`flex items-center justify-center rounded-full transition-transform ${drag === i ? "w-14 h-14 bg-emerald-500/25 border border-emerald-300/70 scale-105" : "w-11 h-11 bg-emerald-500/15 border border-emerald-400/40"}`}>
                <span className={`block rounded-full border-[3px] border-white shadow ${drag === i ? "w-6 h-6 bg-emerald-500" : "w-5 h-5 bg-emerald-500/95"}`} />
              </span>
            </div>
          ))}
          {drag !== null && (
            <canvas ref={loupeRef} className="absolute top-3 rounded-full border-2 border-white shadow-lg pointer-events-none"
              style={{ width: LOUPE, height: LOUPE, [loupeLeft ? "right" : "left"]: 12 }} />
          )}
        </>
      )}
    </div>
  );
}
