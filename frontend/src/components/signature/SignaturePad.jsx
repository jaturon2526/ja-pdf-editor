// แผ่นวาดลายเซ็นด้วยนิ้ว/ปากกา/เมาส์ — ออกแบบให้แม่นบนมือถือและแท็บเล็ต
//
// ปัญหาเดิม: canvas ขนาดจริง 480×220 แต่บนมือถือถูกย่อด้วย CSS — พิกัดนิ้ว (px บนจอ) จึงไม่ตรงกับพิกัดใน canvas
// เส้นเลยเลื่อนออกจากปลายนิ้ว และบน iOS การลากนิ้วยังเลื่อนหน้าจอไปด้วย
//
// วิธีใหม่:
// - ขนาด canvas = ขนาดที่แสดงจริง × devicePixelRatio (คมบนจอ Retina) และวาดด้วยพิกัด CSS px ตรง ๆ
// - เก็บเส้นเป็นพิกัดสัดส่วนกับความกว้าง → หมุนจอ/ย่อขยายแล้ววาดใหม่ได้ไม่เพี้ยน
// - ใช้ getCoalescedEvents() เก็บทุกจุดที่นิ้วผ่าน (เส้นไม่หักเป็นมุม) · pointer capture · touch-action: none
// - ปากกา (Apple Pencil ฯลฯ) ใช้แรงกดกำหนดความหนา
// - ส่งออกเป็น PNG พื้นใส ครอปให้พอดีลายเซ็น ความละเอียดสูง
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from "react";

const BASE_WIDTH = 2.6; // ความหนาเส้น (CSS px) ที่ความกว้างแผ่น 480px — ปรับตามขนาดแผ่น

function strokeWidth(point, padWidth) {
  const scale = Math.max(0.8, Math.min(1.6, padWidth / 480));
  const pressure = point.pen && point.p > 0 ? 0.45 + point.p * 1.1 : 1;
  return BASE_WIDTH * scale * pressure;
}

function drawStroke(ctx, stroke, w) {
  const pts = stroke.points;
  if (!pts.length) return;
  ctx.strokeStyle = stroke.color;
  ctx.fillStyle = stroke.color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  if (pts.length === 1) {
    ctx.beginPath();
    ctx.arc(pts[0].x * w, pts[0].y * w, strokeWidth(pts[0], w) / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  for (let i = 1; i < pts.length; i += 1) {
    const a = pts[i - 1];
    const b = pts[i];
    ctx.lineWidth = strokeWidth(b, w);
    ctx.beginPath();
    ctx.moveTo(a.x * w, a.y * w);
    ctx.lineTo(b.x * w, b.y * w);
    ctx.stroke();
  }
}

const SignaturePad = forwardRef(function SignaturePad({ color, onChange, className = "" }, ref) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const strokesRef = useRef([]);
  const activeRef = useRef(null); // { id, stroke }
  const sizeRef = useRef({ w: 0, h: 0 });

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { w, h } = sizeRef.current;
    const dpr = window.devicePixelRatio || 1;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    strokesRef.current.forEach((s) => drawStroke(ctx, s, w));
  }, []);

  // ปรับขนาด canvas ตามพื้นที่ที่แสดงจริง (รวมตอนหมุนจอ)
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return undefined;
    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      sizeRef.current = { w: rect.width, h: rect.height };
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      redraw();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    return () => ro.disconnect();
  }, [redraw]);

  // iOS Safari: กันหน้าเลื่อน/ซูมระหว่างเซ็น (ต้องเป็น listener แบบ passive: false)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const stop = (e) => e.preventDefault();
    canvas.addEventListener("touchstart", stop, { passive: false });
    canvas.addEventListener("touchmove", stop, { passive: false });
    return () => {
      canvas.removeEventListener("touchstart", stop);
      canvas.removeEventListener("touchmove", stop);
    };
  }, []);

  const notify = () => onChange?.(strokesRef.current.length > 0);

  function toPoint(e, pointerType = e.pointerType) {
    const rect = canvasRef.current.getBoundingClientRect();
    const w = rect.width || 1;
    return {
      x: (e.clientX - rect.left) / w,
      y: (e.clientY - rect.top) / w,
      p: e.pressure,
      pen: pointerType === "pen",
    };
  }

  function handleDown(e) {
    if (e.button !== undefined && e.button !== 0 && e.pointerType === "mouse") return;
    if (activeRef.current) return; // นิ้วที่สอง (เช่น วางฝ่ามือ) ไม่นับ
    e.preventDefault();
    canvasRef.current.setPointerCapture?.(e.pointerId);
    const stroke = { color, points: [toPoint(e)] };
    activeRef.current = { id: e.pointerId, stroke };
    strokesRef.current.push(stroke);
    redraw();
    notify();
  }

  function handleMove(e) {
    const active = activeRef.current;
    if (!active || active.id !== e.pointerId) return;
    e.preventDefault();
    const events = e.nativeEvent.getCoalescedEvents?.() || [];
    const list = events.length ? events : [e.nativeEvent];
    const { w } = sizeRef.current;
    const dpr = window.devicePixelRatio || 1;
    const ctx = canvasRef.current.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.strokeStyle = active.stroke.color;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const ev of list) {
      const pt = toPoint(ev, e.pointerType);
      const last = active.stroke.points[active.stroke.points.length - 1];
      if (Math.abs(pt.x - last.x) * w < 0.4 && Math.abs(pt.y - last.y) * w < 0.4) continue;
      active.stroke.points.push(pt);
      ctx.lineWidth = strokeWidth(pt, w);
      ctx.beginPath();
      ctx.moveTo(last.x * w, last.y * w);
      ctx.lineTo(pt.x * w, pt.y * w);
      ctx.stroke();
    }
  }

  function handleUp(e) {
    const active = activeRef.current;
    if (!active || active.id !== e.pointerId) return;
    activeRef.current = null;
    canvasRef.current.releasePointerCapture?.(e.pointerId);
  }

  useImperativeHandle(ref, () => ({
    clear() {
      strokesRef.current = [];
      activeRef.current = null;
      redraw();
      notify();
    },
    undo() {
      strokesRef.current.pop();
      redraw();
      notify();
    },
    isEmpty: () => strokesRef.current.length === 0,
    setColor(next) {
      // เปลี่ยนสีทั้งลายเซ็น (ลายเซ็นหนึ่งอันควรเป็นสีเดียว)
      strokesRef.current.forEach((s) => { s.color = next; });
      redraw();
    },
    // PNG พื้นใส ครอปพอดีลายเซ็น + ขอบ 6% ความละเอียดสูงสุดกว้าง ~1200px
    toDataURL() {
      const strokes = strokesRef.current;
      if (!strokes.length) return null;
      const { w } = sizeRef.current;
      let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
      strokes.forEach((s) => s.points.forEach((p) => {
        const half = strokeWidth(p, w) / 2;
        minX = Math.min(minX, p.x * w - half); maxX = Math.max(maxX, p.x * w + half);
        minY = Math.min(minY, p.y * w - half); maxY = Math.max(maxY, p.y * w + half);
      }));
      const pad = Math.max(6, (maxX - minX) * 0.06);
      minX -= pad; minY -= pad; maxX += pad; maxY += pad;
      const bw = Math.max(1, maxX - minX);
      const bh = Math.max(1, maxY - minY);
      const k = Math.min(4, Math.max(2, 1200 / bw));
      const out = document.createElement("canvas");
      out.width = Math.round(bw * k);
      out.height = Math.round(bh * k);
      const ctx = out.getContext("2d");
      ctx.setTransform(k, 0, 0, k, -minX * k, -minY * k);
      strokes.forEach((s) => drawStroke(ctx, s, w));
      return out.toDataURL("image/png");
    },
  }));

  return (
    <div
      ref={wrapRef}
      className={`relative w-full rounded-xl border-2 border-dashed border-slate-300 bg-white overflow-hidden select-none ${className}`}
      style={{ touchAction: "none" }}
    >
      {/* เส้นบอกตำแหน่งเซ็น */}
      <div className="pointer-events-none absolute left-[6%] right-[6%] bottom-[24%] border-b border-slate-300" />
      <span className="pointer-events-none absolute left-[6%] bottom-[24%] mb-1 text-slate-300 text-xl leading-none">✕</span>
      <canvas
        ref={canvasRef}
        data-testid="signature-pad"
        aria-label="พื้นที่วาดลายเซ็น"
        className="absolute inset-0 w-full h-full cursor-crosshair"
        style={{ touchAction: "none" }}
        onPointerDown={handleDown}
        onPointerMove={handleMove}
        onPointerUp={handleUp}
        onPointerCancel={handleUp}
        onLostPointerCapture={handleUp}
      />
    </div>
  );
});

export default SignaturePad;
