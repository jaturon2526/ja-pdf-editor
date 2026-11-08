// ปรับมุมเอกสาร 4 จุดบนภาพที่ถ่าย — ลากด้วยนิ้ว/เมาส์ มีแว่นขยายตรงจุดที่ลากให้วางมุมได้แม่น
// corners: [{x,y} x4] สัดส่วน 0..1 ของภาพ เรียง บนซ้าย บนขวา ล่างขวา ล่างซ้าย
import { useCallback, useEffect, useRef, useState } from "react";

const HANDLE = 44; // พื้นที่แตะ (px) — ตัวจุดที่เห็นเล็กกว่า
const LOUPE = 112;
const LOUPE_ZOOM = 2.5;

export default function CornerEditor({ src, corners, onChange }) {
  const boxRef = useRef(null);
  const imgRef = useRef(null);
  const loupeRef = useRef(null);
  const [layout, setLayout] = useState(null); // {ox, oy, w, h} กรอบภาพที่แสดงจริงในกล่อง
  const [drag, setDrag] = useState(null); // index ที่กำลังลาก

  const measure = useCallback(() => {
    const box = boxRef.current;
    const img = imgRef.current;
    if (!box || !img || !img.naturalWidth) return;
    const bw = box.clientWidth;
    const bh = box.clientHeight;
    const s = Math.min(bw / img.naturalWidth, bh / img.naturalHeight);
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

  const toPx = (c) => ({ x: layout.ox + c.x * layout.w, y: layout.oy + c.y * layout.h });

  function drawLoupe(c) {
    const canvas = loupeRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
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

  function onPointerDown(i, e) {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setDrag(i);
    requestAnimationFrame(() => drawLoupe(corners[i]));
  }

  function onPointerMove(i, e) {
    if (drag !== i || !layout) return;
    const rect = boxRef.current.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left - layout.ox) / layout.w));
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top - layout.oy) / layout.h));
    const next = corners.map((c, k) => (k === i ? { x, y } : c));
    onChange(next);
    drawLoupe(next[i]);
  }

  function onPointerUp(e) {
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
    setDrag(null);
  }

  const pts = layout ? corners.map(toPx) : [];
  // แว่นขยายอยู่มุมบนฝั่งตรงข้ามนิ้ว ไม่ให้นิ้วบัง
  const loupeLeft = drag !== null && pts[drag] && pts[drag].x < (boxRef.current?.clientWidth || 0) / 2;

  return (
    <div ref={boxRef} className="relative w-full h-full select-none touch-none overflow-hidden" data-testid="corner-editor">
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
              onPointerDown={(e) => onPointerDown(i, e)}
              onPointerMove={(e) => onPointerMove(i, e)}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              <span className={`block rounded-full border-[3px] border-white shadow ${drag === i ? "w-7 h-7 bg-emerald-500" : "w-5 h-5 bg-emerald-500/90"}`} />
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
