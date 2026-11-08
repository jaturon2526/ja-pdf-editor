// ใส่ลายน้ำ — ใช้ทั้งใน Editor และเครื่องมือด่วนบน Dashboard
// มีตัวอย่างสดบนหน้ากระดาษจำลอง: ลายน้ำจริงจะ "ย่อให้พอดีหน้า" ถ้าข้อความยาว/หน้าเล็ก (ดู backend watermark.py: FIT = 0.9)
import { useEffect, useLayoutEffect, useRef, useState } from "react";

export const WATERMARK_MAX_LENGTH = 200;

const COLORS = [
  { key: "gray", label: "เทา", rgb: [0.6, 0.6, 0.6] },
  { key: "red", label: "แดง", rgb: [0.85, 0.1, 0.1] },
  { key: "blue", label: "น้ำเงิน", rgb: [0.1, 0.3, 0.8] },
  { key: "black", label: "ดำ", rgb: [0.15, 0.15, 0.15] },
];
const PRESETS = ["สำเนา", "สำเนาถูกต้อง", "ลับ", "ห้ามเผยแพร่", "CONFIDENTIAL", "DRAFT"];
const ANGLES = [
  { value: 45, label: "เฉียงขึ้น" },
  { value: 0, label: "แนวนอน" },
  { value: -45, label: "เฉียงลง" },
];

// หน้ากระดาษจำลอง A4 แนวตั้ง กว้าง PREVIEW_W px แทน 595 pt
const PREVIEW_W = 150;
const PAGE_PT = { w: 595, h: 842 };
const PT_TO_PX = PREVIEW_W / PAGE_PT.w;
const toCss = ([r, g, b]) => `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;

function Preview({ text, size, opacity, angle, rgb }) {
  const ref = useRef(null);
  const [fit, setFit] = useState(1);
  const W = PREVIEW_W;
  const H = PAGE_PT.h * PT_TO_PX;
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight * 0.75; // กรอบบรรทัดสูงกว่าตัวอักษรจริง
    const rad = (Math.abs(angle) * Math.PI) / 180;
    const bw = w * Math.cos(rad) + h * Math.sin(rad);
    const bh = w * Math.sin(rad) + h * Math.cos(rad);
    setFit(Math.min(1, (0.9 * W) / (bw || 1), (0.9 * H) / (bh || 1)));
  }, [text, size, angle, W, H]);
  return (
    <div
      aria-hidden="true"
      data-testid="watermark-preview"
      className="relative mx-auto overflow-hidden bg-white border border-gray-300 rounded shadow-sm"
      style={{ width: W, height: H }}
    >
      <div className="absolute inset-x-3 top-4 space-y-1.5">
        {Array.from({ length: 14 }, (_, i) => (
          <div key={i} className="h-1 rounded bg-gray-200" style={{ width: `${[100, 92, 97, 60][i % 4]}%` }} />
        ))}
      </div>
      <span
        ref={ref}
        className="absolute left-1/2 top-1/2 whitespace-nowrap leading-none font-[Sarabun,sans-serif]"
        style={{
          fontSize: size * PT_TO_PX,
          color: toCss(rgb),
          opacity,
          transform: `translate(-50%, -50%) rotate(${-angle}deg) scale(${fit})`,
        }}
      >
        {text || "ตัวอย่าง"}
      </span>
    </div>
  );
}

export default function WatermarkModal({ onClose, onSubmit, fileName = null, submitting = false }) {
  const [text, setText] = useState("");
  const [opacity, setOpacity] = useState(0.3);
  const [angle, setAngle] = useState(45);
  const [size, setSize] = useState(60);
  const [color, setColor] = useState("gray");
  const rgb = COLORS.find((c) => c.key === color).rgb;
  const clean = text.replace(/\s+/g, " ").trim();

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !submitting && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  function handleSubmit(e) {
    e?.preventDefault();
    if (!clean || submitting) return;
    onSubmit({ text: clean, opacity: Number(opacity), angle: Number(angle), font_size: Number(size), color: rgb });
  }

  const chip = (active) =>
    `px-2.5 py-1 min-h-[32px] text-xs rounded-full border ${active ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && onClose()}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="watermark-title"
        onSubmit={handleSubmit}
        className="bg-white w-full sm:max-w-xl rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92dvh]"
      >
        <div className="p-4 border-b border-gray-100">
          <h2 id="watermark-title" className="text-lg font-bold text-gray-900">ใส่ลายน้ำ</h2>
          {fileName && (
            <p className="mt-1 text-sm text-gray-500">
              ไฟล์: <strong className="text-gray-900 break-all">{fileName}</strong> — บันทึกเป็นไฟล์ใหม่ (ไฟล์เดิมไม่ถูกแก้)
            </p>
          )}
        </div>

        <div className="p-4 overflow-y-auto grid gap-4 sm:grid-cols-[1fr_auto]">
          <div className="space-y-4 min-w-0">
            <div>
              <label htmlFor="watermark-text" className="block text-sm font-medium text-gray-800">ข้อความลายน้ำ</label>
              <input
                id="watermark-text"
                type="text"
                autoFocus
                maxLength={WATERMARK_MAX_LENGTH}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="เช่น CONFIDENTIAL, สำเนาถูกต้อง"
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
              <div className="mt-2 flex flex-wrap gap-1.5">
                {PRESETS.map((p) => (
                  <button key={p} type="button" className={chip(clean === p)} onClick={() => setText(p)}>{p}</button>
                ))}
              </div>
            </div>

            <fieldset>
              <legend className="text-sm font-medium text-gray-800">สี</legend>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {COLORS.map((c) => (
                  <button key={c.key} type="button" aria-pressed={color === c.key} className={`${chip(color === c.key)} inline-flex items-center gap-1.5`} onClick={() => setColor(c.key)}>
                    <span className="inline-block w-3 h-3 rounded-full" style={{ background: toCss(c.rgb) }} />
                    {c.label}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="text-sm font-medium text-gray-800">มุมเอียง ({angle}°)</legend>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {ANGLES.map((a) => (
                  <button key={a.value} type="button" aria-pressed={Number(angle) === a.value} className={chip(Number(angle) === a.value)} onClick={() => setAngle(a.value)}>{a.label}</button>
                ))}
              </div>
              <input aria-label="มุมเอียง" type="range" min="-90" max="90" value={angle} onChange={(e) => setAngle(Number(e.target.value))} className="mt-2 w-full" />
            </fieldset>

            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm font-medium text-gray-800">
                ขนาด ({size})
                <input type="range" min="20" max="150" value={size} onChange={(e) => setSize(Number(e.target.value))} className="mt-2 w-full" />
              </label>
              <label className="block text-sm font-medium text-gray-800">
                ความทึบ ({Math.round(opacity * 100)}%)
                <input type="range" min="0.1" max="1" step="0.05" value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} className="mt-2 w-full" />
              </label>
            </div>
          </div>

          <div className="flex flex-col items-center gap-1">
            <Preview text={clean} size={size} opacity={opacity} angle={angle} rgb={rgb} />
            <p className="text-xs text-gray-500 text-center max-w-[150px]">ตัวอย่างบนกระดาษ A4 · ข้อความยาวจะย่อให้พอดีหน้า</p>
          </div>
        </div>

        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">ยกเลิก</button>
          <button type="submit" disabled={!clean || submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
            {submitting ? "กำลังใส่ลายน้ำ..." : "ใส่ลายน้ำ"}
          </button>
        </div>
      </form>
    </div>
  );
}
