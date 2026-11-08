// สร้างรูปลายเซ็น 3 วิธี (ใช้ร่วมกันทั้งลายเซ็นอิเล็กทรอนิกส์และลายเซ็นดิจิทัล):
// พิมพ์ข้อความ · ใส่รูปภาพ (ลบพื้นขาวให้อัตโนมัติ) · เซ็นสดด้วยนิ้ว/ปากกา/เมาส์
// optional=true: เพิ่มแท็บ "ไม่ใส่รูป" (ลายเซ็นดิจิทัลแสดงเป็นข้อความได้)
// ref.getDataUrl() → PNG data URL หรือ null · onReadyChange(boolean) บอกว่ากด "ตกลง" ได้หรือยัง
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import SignaturePad from "./SignaturePad.jsx";

export const SIGN_COLOR_PRESETS = [
  { key: "black", label: "ดำ", value: "#12172b" },
  { key: "blue", label: "น้ำเงิน", value: "#1a56db" },
  { key: "red", label: "แดง", value: "#d32f2f" },
];

const TEXT_FONTS = [
  { key: "script", label: "ลายมือ", css: 'italic {size}px "Segoe Script", "Brush Script MT", "Snell Roundhand", cursive, sans-serif' },
  { key: "thai", label: "ไทย", css: '{size}px "Sarabun", "Thonburi", "Leelawadee UI", sans-serif' },
  { key: "serif", label: "ทางการ", css: 'italic {size}px Georgia, "Times New Roman", serif' },
];

const isTouch = () => typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

// รูปถ่ายลายเซ็นบนกระดาษ: ทำพื้นสีขาว/เทาอ่อนให้โปร่งใส แล้วครอปให้พอดี
async function cleanSignatureImage(dataUrl, removeBackground) {
  const img = await new Promise((resolve, reject) => {
    const el = new Image();
    el.onload = () => resolve(el);
    el.onerror = reject;
    el.src = dataUrl;
  });
  const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
  const w = Math.max(1, Math.round(img.width * scale));
  const h = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, w, h);
  if (!removeBackground) return canvas.toDataURL("image/png");
  const data = ctx.getImageData(0, 0, w, h);
  const px = data.data;
  let minX = w; let minY = h; let maxX = -1; let maxY = -1;
  for (let i = 0; i < px.length; i += 4) {
    const lum = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
    if (lum > 200) {
      px[i + 3] = 0;
    } else if (lum > 150) {
      px[i + 3] = Math.round(px[i + 3] * ((200 - lum) / 50)); // ขอบนุ่ม
    }
    if (px[i + 3] > 40) {
      const p = i / 4;
      const x = p % w;
      const y = (p - x) / w;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  ctx.putImageData(data, 0, 0);
  if (maxX < 0) return canvas.toDataURL("image/png");
  const pad = Math.round(Math.max(maxX - minX, maxY - minY) * 0.04) + 4;
  const cx = Math.max(0, minX - pad);
  const cy = Math.max(0, minY - pad);
  const cw = Math.min(w, maxX + pad) - cx;
  const ch = Math.min(h, maxY + pad) - cy;
  const out = document.createElement("canvas");
  out.width = cw;
  out.height = ch;
  out.getContext("2d").drawImage(canvas, cx, cy, cw, ch, 0, 0, cw, ch);
  return out.toDataURL("image/png");
}

function ColorPicker({ value, onChange }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="text-sm font-medium text-slate-700">สีปากกา</span>
      <div className="flex items-center gap-2" role="radiogroup" aria-label="สีปากกา">
        {SIGN_COLOR_PRESETS.map((c) => (
          <button
            key={c.key}
            type="button"
            role="radio"
            aria-checked={value === c.value}
            aria-label={c.label}
            title={c.label}
            onClick={() => onChange(c.value)}
            className={`w-9 h-9 short:w-8 short:h-8 rounded-full border-2 transition ${value === c.value ? "border-sky-500 ring-2 ring-sky-200 scale-105" : "border-white shadow"}`}
            style={{ backgroundColor: c.value }}
          />
        ))}
        {(() => {
          const custom = !SIGN_COLOR_PRESETS.some((c) => c.value === value);
          return (
            <label
              className={`relative w-9 h-9 rounded-full overflow-hidden border-2 cursor-pointer flex items-center justify-center ${custom ? "border-sky-500 ring-2 ring-sky-200" : "border-white shadow"}`}
              style={{ background: custom ? value : "conic-gradient(#ef4444,#f59e0b,#22c55e,#06b6d4,#6366f1,#ec4899,#ef4444)" }}
              title="เลือกสีอื่น"
            >
              <span className="sr-only">เลือกสีอื่น</span>
              {!custom && <span className="w-5 h-5 rounded-full bg-white/90 text-slate-700 text-sm leading-5 text-center font-bold">+</span>}
              <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
            </label>
          );
        })()}
      </div>
    </div>
  );
}

const SignatureCreator = forwardRef(function SignatureCreator({ optional = false, onReadyChange }, ref) {
  const tabs = [
    ...(optional ? [{ key: "none", label: "ไม่ใส่รูป" }] : []),
    { key: "draw", label: "เซ็นสด" },
    { key: "text", label: "พิมพ์" },
    { key: "image", label: "รูปภาพ" },
  ];
  const [tab, setTab] = useState(() => (optional ? "none" : isTouch() ? "draw" : "text"));
  const [color, setColor] = useState(SIGN_COLOR_PRESETS[0].value);

  // พิมพ์ข้อความ
  const [text, setText] = useState("");
  const [font, setFont] = useState(TEXT_FONTS[0].key);
  const textCanvasRef = useRef(null);

  // รูปภาพ
  const [rawImage, setRawImage] = useState(null);
  const [removeBg, setRemoveBg] = useState(true);
  const [imageUrl, setImageUrl] = useState(null);
  const fileRef = useRef(null);

  // เซ็นสด
  const padRef = useRef(null);
  const [hasInk, setHasInk] = useState(false);

  const ready = tab === "none" || (tab === "text" && text.trim().length > 0) || (tab === "image" && !!imageUrl) || (tab === "draw" && hasInk);
  useEffect(() => {
    onReadyChange?.(ready);
  }, [ready, onReadyChange]);

  useEffect(() => {
    padRef.current?.setColor(color);
  }, [color]);

  useEffect(() => {
    if (!rawImage) {
      setImageUrl(null);
      return;
    }
    let cancelled = false;
    cleanSignatureImage(rawImage, removeBg).then((url) => !cancelled && setImageUrl(url)).catch(() => !cancelled && setImageUrl(rawImage));
    return () => { cancelled = true; };
  }, [rawImage, removeBg]);

  // วาดข้อความลง canvas (ความละเอียด 2 เท่า) — ปรับขนาดตัวอักษรให้พอดีกรอบ
  useEffect(() => {
    if (tab !== "text") return;
    const canvas = textCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!text.trim()) return;
    const spec = TEXT_FONTS.find((f) => f.key === font).css;
    let size = 112;
    ctx.font = spec.replace("{size}", size);
    let width = ctx.measureText(text).width;
    while (width > canvas.width - 48 && size > 28) {
      size -= 4;
      ctx.font = spec.replace("{size}", size);
      width = ctx.measureText(text).width;
    }
    ctx.fillStyle = color;
    ctx.textBaseline = "middle";
    ctx.textAlign = "left";
    ctx.fillText(text, (canvas.width - width) / 2, canvas.height / 2);
  }, [tab, text, font, color]);

  useImperativeHandle(ref, () => ({
    getDataUrl() {
      if (tab === "none") return null;
      if (tab === "text") return text.trim() ? textCanvasRef.current.toDataURL("image/png") : null;
      if (tab === "image") return imageUrl;
      return padRef.current?.toDataURL() || null;
    },
  }));

  const tabBtn = (t) => (
    <button
      key={t.key}
      type="button"
      role="tab"
      aria-selected={tab === t.key}
      onClick={() => setTab(t.key)}
      className={`flex-1 min-w-0 px-2 py-2.5 short:py-1.5 text-sm font-medium rounded-lg transition ${tab === t.key ? "bg-white text-sky-700 shadow" : "text-slate-600 hover:text-slate-900"}`}
    >
      {t.label}
    </button>
  );

  return (
    <div className="space-y-3 short:space-y-2">
      <div className="flex gap-1 p-1 rounded-xl bg-slate-100" role="tablist" aria-label="วิธีสร้างลายเซ็น">{tabs.map(tabBtn)}</div>


      {tab === "none" && (
        <p className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-sm text-slate-600">
          ไม่ใส่รูปลายเซ็น — ในเอกสารจะแสดงเป็นข้อความชื่อผู้ลงนามและเวลา
        </p>
      )}

      {tab === "draw" && (
        <div className="space-y-3 short:space-y-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <ColorPicker value={color} onChange={setColor} />
            <div className="flex items-center gap-2 ml-auto">
              <button type="button" onClick={() => padRef.current?.undo()} disabled={!hasInk}
                className="px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-700 disabled:opacity-40">
                ↶ เลิกทำ
              </button>
              <button type="button" onClick={() => padRef.current?.clear()} disabled={!hasInk}
                className="px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-700 disabled:opacity-40">
                ล้าง
              </button>
            </div>
          </div>
          <SignaturePad ref={padRef} color={color} onChange={setHasInk}
            className="h-[clamp(180px,42dvh,360px)] sm:h-[clamp(200px,34dvh,280px)] short:h-[max(140px,calc(100dvh-210px))]" />
          <p className="text-xs text-slate-500 short:hidden">
            เซ็นเหนือเส้น — ระบบตัดขอบว่างให้อัตโนมัติ
            {isTouch() && <span className="portrait:inline landscape:hidden"> · 💡 หมุนจอเป็นแนวนอนเพื่อให้มีพื้นที่เซ็นกว้างขึ้น</span>}
          </p>
        </div>
      )}

      {tab === "text" && (
        <div className="space-y-3">
          <input
            autoFocus={!isTouch()}
            type="text"
            maxLength={60}
            className="w-full px-4 py-3 text-base border border-slate-300 rounded-lg bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
            placeholder="พิมพ์ข้อความที่จะใช้เป็นลายเซ็น..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-700">แบบอักษร</span>
            {TEXT_FONTS.map((f) => (
              <button key={f.key} type="button" onClick={() => setFont(f.key)}
                className={`px-3 py-1.5 text-sm rounded-full border ${font === f.key ? "border-sky-500 bg-sky-50 text-sky-700" : "border-slate-300 bg-white text-slate-600"}`}>
                {f.label}
              </button>
            ))}
          </div>
          <ColorPicker value={color} onChange={setColor} />
          <canvas ref={textCanvasRef} width={960} height={300} className="w-full h-auto rounded-xl border-2 border-dashed border-slate-300 bg-white" />
        </div>
      )}

      {tab === "image" && (
        <div className="space-y-3">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            data-testid="signature-image-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              const reader = new FileReader();
              reader.onload = () => setRawImage(reader.result);
              reader.readAsDataURL(f);
            }}
          />
          <button type="button" onClick={() => fileRef.current?.click()}
            className="w-full py-3 rounded-lg border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50">
            {rawImage ? "เปลี่ยนรูป..." : "เลือกรูป หรือถ่ายรูปลายเซ็นบนกระดาษ..."}
          </button>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" className="h-4 w-4" checked={removeBg} onChange={(e) => setRemoveBg(e.target.checked)} />
            ลบพื้นหลังสีขาวและตัดขอบให้อัตโนมัติ
          </label>
          <div className="flex items-center justify-center min-h-[140px] rounded-xl border-2 border-dashed border-slate-300 bg-[repeating-conic-gradient(#f1f5f9_0%_25%,#fff_0%_50%)] bg-[length:16px_16px]">
            {imageUrl ? (
              <img src={imageUrl} alt="พรีวิวลายเซ็นที่อัปโหลด" className="max-h-56 max-w-full object-contain p-2" />
            ) : (
              <span className="text-sm text-slate-400">ยังไม่ได้เลือกรูปภาพ</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default SignatureCreator;
