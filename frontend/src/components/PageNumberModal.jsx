// ใส่เลขหน้า — ใช้ทั้งใน Editor (เมนูแทรก) และเครื่องมือด่วนบน Dashboard (ไม่ต้องเปิดไฟล์)
// ค่าเริ่มต้นตามที่ผู้ใช้กำหนด: หน้าแรกที่ใส่ขึ้นเลข 1 · จำนวนหน้าทั้งหมดนับเฉพาะหน้าที่ใส่ · หน้าคู่/คี่ตามลำดับหน้าจริง
// backend: POST /edit/{sid}/page-numbers และ quick-action page_numbers (ดู edit_service/page_numbers.py)
import { useEffect, useMemo, useState } from "react";

const THAI = "๐๑๒๓๔๕๖๗๘๙";
const toThai = (s) => String(s).replace(/[0-9]/g, (d) => THAI[Number(d)]);
const SEPARATORS = ["/", " / ", " จาก ", " of ", "-"];
const COLORS = [
  { key: "dark", label: "เทาเข้ม", rgb: [0.2, 0.2, 0.2] },
  { key: "black", label: "ดำ", rgb: [0, 0, 0] },
  { key: "gray", label: "เทา", rgb: [0.5, 0.5, 0.5] },
  { key: "blue", label: "น้ำเงิน", rgb: [0.1, 0.3, 0.8] },
];
const toCss = ([r, g, b]) => `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;

export function pageLabel(number, total, o) {
  const core = o.fmt === "n" ? String(number) : `${number}${o.separator}${total}`;
  const text = `${o.prefix}${core}${o.suffix}`;
  return o.thaiDigits ? toThai(text) : text;
}

/** [{ page (ลำดับจริง 1-based), label, side }] — ต้องตรงกับ backend page_plan() */
export function pagePlan(pageCount, o) {
  const first = Math.max(1, Number(o.startPage) || 1);
  const last = Math.min(pageCount, Number(o.endPage) || pageCount);
  if (!pageCount || first > last) return [];
  const total = o.startNumber + (last - first);
  const plan = [];
  for (let p = first; p <= last; p++) {
    let side = o.hpos;
    if (o.mirrorEven && side !== "center" && p % 2 === 0) side = side === "left" ? "right" : "left";
    plan.push({ page: p, label: pageLabel(o.startNumber + (p - first), total, o), side });
  }
  return plan;
}

function MiniPage({ item, vpos, rgb, faded }) {
  const justify = { left: "justify-start", center: "justify-center", right: "justify-end" }[item?.side || "center"];
  return (
    <div className={`relative bg-white border border-gray-300 rounded shadow-sm w-[92px] h-[130px] ${faded ? "opacity-60" : ""}`}>
      <div className="absolute inset-x-2.5 top-5 space-y-1.5">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="h-1 rounded bg-gray-200" style={{ width: `${[100, 92, 97, 60][i % 4]}%` }} />
        ))}
      </div>
      {item && (
        <div className={`absolute inset-x-1.5 flex ${justify} ${vpos === "top" ? "top-1" : "bottom-1"}`}>
          <span className="text-[9px] leading-none whitespace-nowrap font-[Sarabun,sans-serif]" style={{ color: toCss(rgb) }}>{item.label}</span>
        </div>
      )}
      <span className="absolute -bottom-4 inset-x-0 text-center text-[10px] text-gray-500">หน้า {item?.page ?? "–"}</span>
    </div>
  );
}

export default function PageNumberModal({ onClose, onSubmit, pageCount = null, fileName = null, submitting = false }) {
  const [o, setO] = useState({
    fmt: "n", separator: "/", prefix: "", suffix: "", thaiDigits: false,
    startPage: 1, endPage: "", startNumber: 1,
    vpos: "bottom", hpos: "center", mirrorEven: false, fontSize: 11, margin: 28, color: "dark",
  });
  const set = (k, v) => setO((s) => ({ ...s, [k]: v }));
  const rgb = COLORS.find((c) => c.key === o.color).rgb;
  const count = pageCount || 10; // ไม่รู้จำนวนหน้า (Dashboard) — พรีวิวสมมติ 10 หน้า
  const plan = useMemo(() => pagePlan(count, { ...o, startNumber: Number(o.startNumber) || 0 }), [count, o]);

  const errors = [];
  const sp = Number(o.startPage);
  if (!Number.isInteger(sp) || sp < 1) errors.push("หน้าเริ่มต้นต้องเป็นเลข 1 ขึ้นไป");
  else if (pageCount && sp > pageCount) errors.push(`เอกสารมี ${pageCount} หน้า — เริ่มที่หน้า ${sp} ไม่ได้`);
  if (o.endPage !== "") {
    const ep = Number(o.endPage);
    if (!Number.isInteger(ep) || ep < sp) errors.push("หน้าสุดท้ายต้องไม่น้อยกว่าหน้าเริ่มต้น");
  }
  if (!Number.isInteger(Number(o.startNumber)) || Number(o.startNumber) < 0) errors.push("เลขเริ่มนับต้องเป็นจำนวนเต็ม 0 ขึ้นไป");
  if (o.fmt === "n_total" && !o.separator) errors.push("กรุณาใส่ตัวคั่น");

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !submitting && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  function handleSubmit(e) {
    e?.preventDefault();
    if (errors.length || submitting) return;
    onSubmit({
      fmt: o.fmt, separator: o.separator, prefix: o.prefix, suffix: o.suffix, thai_digits: o.thaiDigits,
      start_page: sp, end_page: o.endPage === "" ? null : Number(o.endPage), start_number: Number(o.startNumber),
      vpos: o.vpos, hpos: o.hpos, mirror_even: o.mirrorEven && o.hpos !== "center",
      font_size: Number(o.fontSize), margin_pt: Number(o.margin), color: rgb,
    });
  }

  const chip = (active) =>
    `px-2.5 py-1 min-h-[32px] text-xs rounded-full border ${active ? "border-blue-500 bg-blue-50 text-blue-700" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`;
  const input = "mt-1 block w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500";
  // พรีวิว: หน้าที่ใส่เลขสองหน้าแรก (เห็นการสลับหน้าคู่/คี่)
  const previewItems = plan.slice(0, 2);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && onClose()}>
      <form role="dialog" aria-modal="true" aria-labelledby="pn-title" onSubmit={handleSubmit}
        className="bg-white w-full sm:max-w-2xl rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92dvh]">
        <div className="p-4 border-b border-gray-100">
          <h2 id="pn-title" className="text-lg font-bold text-gray-900">ใส่เลขหน้า</h2>
          {fileName && (
            <p className="mt-1 text-sm text-gray-500">
              ไฟล์: <strong className="text-gray-900 break-all">{fileName}</strong> — บันทึกเป็นไฟล์ใหม่ (ไฟล์เดิมไม่ถูกแก้)
            </p>
          )}
        </div>

        <div className="p-4 overflow-y-auto grid gap-5 sm:grid-cols-[1fr_auto]">
          <div className="space-y-4 min-w-0">
            <fieldset>
              <legend className="text-sm font-medium text-gray-800">รูปแบบ</legend>
              <div className="mt-1 flex flex-wrap gap-1.5">
                <button type="button" aria-pressed={o.fmt === "n"} className={chip(o.fmt === "n")} onClick={() => set("fmt", "n")}>1, 2, 3 …</button>
                <button type="button" aria-pressed={o.fmt === "n_total"} className={chip(o.fmt === "n_total")} onClick={() => set("fmt", "n_total")}>1/N (มีจำนวนหน้าทั้งหมด)</button>
                <button type="button" aria-pressed={o.thaiDigits} className={chip(o.thaiDigits)} onClick={() => set("thaiDigits", !o.thaiDigits)}>เลขไทย ๑ ๒ ๓</button>
              </div>
            </fieldset>

            {o.fmt === "n_total" && (
              <div>
                <label htmlFor="pn-sep" className="block text-sm font-medium text-gray-800">ตัวคั่น</label>
                <input id="pn-sep" className={input} maxLength={20} value={o.separator} onChange={(e) => set("separator", e.target.value)} />
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {SEPARATORS.map((s) => (
                    <button key={s} type="button" className={chip(o.separator === s)} onClick={() => set("separator", s)}>{`1${s}9`}</button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm font-medium text-gray-800">ข้อความหน้าเลข
                <input className={input} maxLength={40} value={o.prefix} placeholder='เช่น "หน้า "' onChange={(e) => set("prefix", e.target.value)} />
              </label>
              <label className="block text-sm font-medium text-gray-800">ข้อความหลังเลข
                <input className={input} maxLength={40} value={o.suffix} onChange={(e) => set("suffix", e.target.value)} />
              </label>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <label className="block text-sm font-medium text-gray-800">เริ่มใส่ที่หน้า
                <input type="number" min="1" max={pageCount || undefined} className={input} value={o.startPage} onChange={(e) => set("startPage", e.target.value)} aria-label="เริ่มใส่ที่หน้า" />
              </label>
              <label className="block text-sm font-medium text-gray-800">ถึงหน้า
                <input type="number" min="1" max={pageCount || undefined} className={input} value={o.endPage} placeholder="สุดท้าย" onChange={(e) => set("endPage", e.target.value)} aria-label="ถึงหน้า" />
              </label>
              <label className="block text-sm font-medium text-gray-800">เริ่มนับเลขที่
                <input type="number" min="0" className={input} value={o.startNumber} onChange={(e) => set("startNumber", e.target.value)} aria-label="เริ่มนับเลขที่" />
              </label>
            </div>

            <fieldset>
              <legend className="text-sm font-medium text-gray-800">ตำแหน่ง</legend>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {[["top", "ด้านบน"], ["bottom", "ด้านล่าง"]].map(([v, l]) => (
                  <button key={v} type="button" aria-pressed={o.vpos === v} className={chip(o.vpos === v)} onClick={() => set("vpos", v)}>{l}</button>
                ))}
                <span className="w-2" />
                {[["left", "ซ้าย"], ["center", "กลาง"], ["right", "ขวา"]].map(([v, l]) => (
                  <button key={v} type="button" aria-pressed={o.hpos === v} className={chip(o.hpos === v)} onClick={() => set("hpos", v)}>{l}</button>
                ))}
              </div>
              <label className={`mt-2 flex items-start gap-2 text-sm ${o.hpos === "center" ? "text-gray-400" : "text-gray-800"}`}>
                <input type="checkbox" className="mt-0.5" disabled={o.hpos === "center"} checked={o.mirrorEven && o.hpos !== "center"} onChange={(e) => set("mirrorEven", e.target.checked)} />
                <span>หน้าคู่วางฝั่งตรงข้าม (พิมพ์สองหน้า) — หน้าคี่อยู่ฝั่งที่เลือก หน้าคู่สลับข้าง นับตามลำดับหน้าจริงในไฟล์</span>
              </label>
            </fieldset>

            <div className="grid grid-cols-3 gap-3">
              <label className="block text-sm font-medium text-gray-800">ขนาด ({o.fontSize})
                <input type="range" min="7" max="24" value={o.fontSize} onChange={(e) => set("fontSize", Number(e.target.value))} className="mt-2 w-full" />
              </label>
              <label className="block text-sm font-medium text-gray-800">ระยะขอบ ({o.margin})
                <input type="range" min="10" max="72" value={o.margin} onChange={(e) => set("margin", Number(e.target.value))} className="mt-2 w-full" />
              </label>
              <label className="block text-sm font-medium text-gray-800">สี
                <select className={input} value={o.color} onChange={(e) => set("color", e.target.value)}>
                  {COLORS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                </select>
              </label>
            </div>
          </div>

          <div className="flex flex-col items-center gap-2" data-testid="page-number-preview">
            <div className="flex gap-2 pb-4">
              <MiniPage item={previewItems[0]} vpos={o.vpos} rgb={rgb} />
              <MiniPage item={previewItems[1]} vpos={o.vpos} rgb={rgb} faded={!previewItems[1]} />
            </div>
            <p className="text-xs text-gray-500 text-center max-w-[200px]">
              {plan.length
                ? <>ใส่ {pageCount ? "" : "≈"}{plan.length} หน้า: {plan[0].label} … {plan[plan.length - 1].label}{pageCount ? "" : " (ตัวอย่างสมมติ 10 หน้า)"}</>
                : "ไม่มีหน้าที่จะใส่เลข"}
            </p>
          </div>
        </div>

        {errors.length > 0 && (
          <ul className="mx-4 mb-2 text-sm text-red-700 bg-red-50 rounded p-2 list-disc list-inside" role="alert">
            {errors.map((e) => <li key={e}>{e}</li>)}
          </ul>
        )}
        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">ยกเลิก</button>
          <button type="submit" disabled={errors.length > 0 || submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
            {submitting ? "กำลังใส่เลขหน้า..." : "ใส่เลขหน้า"}
          </button>
        </div>
      </form>
    </div>
  );
}
