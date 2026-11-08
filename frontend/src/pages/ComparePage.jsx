// หน้าเปรียบเทียบเอกสาร /compare/:taskId — รอผล (แถบความคืบหน้า) แล้วแสดง
// เคียงข้าง (A | B เลื่อนพร้อมกันตามคู่หน้า) หรือซ้อนทับ (ไฮไลต์พิกเซลที่ต่าง / ปรับความโปร่ง)
// แผงรายการจุดต่าง: กดแล้วเลื่อนไปที่ตำแหน่ง · ก่อนหน้า/ถัดไป (ปุ่ม หรือ j / k) · กรองตามชนิด · ดาวน์โหลดรายงาน PDF
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { comparePageUrl, downloadCompareReport, getCompare, saveBlob } from "../api";
import { PHONE_LAYOUT_QUERY } from "../utils/viewport.js";

export const KIND = {
  replace: { label: "แก้ไข", color: "#ea580c", bg: "bg-orange-100 text-orange-800" },
  insert: { label: "เพิ่ม", color: "#16a34a", bg: "bg-green-100 text-green-800" },
  delete: { label: "ลบ", color: "#dc2626", bg: "bg-red-100 text-red-800" },
  visual: { label: "ภาพต่าง", color: "#9333ea", bg: "bg-purple-100 text-purple-800" },
  page_insert: { label: "หน้าที่เพิ่ม", color: "#16a34a", bg: "bg-green-100 text-green-800" },
  page_delete: { label: "หน้าที่ลบ", color: "#dc2626", bg: "bg-red-100 text-red-800" },
  page_size: { label: "ขนาดหน้า", color: "#ea580c", bg: "bg-orange-100 text-orange-800" },
};

function useMedia(query) {
  const get = () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches;
  const [match, setMatch] = useState(get);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, [query]);
  return match;
}

/** ภาพหน้า (โหลดเมื่อใกล้เข้าจอ) — URL ต้องมี token จึงโหลดเป็น blob */
function PageImage({ taskId, side, page, zoom, className = "", style }) {
  const ref = useRef(null);
  const [src, setSrc] = useState(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") { setVisible(true); return undefined; }
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setVisible(true), { rootMargin: "800px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return undefined;
    let alive = true;
    let url = null;
    comparePageUrl(taskId, side, page, zoom).then((u) => {
      url = u;
      if (alive) setSrc(u); else URL.revokeObjectURL(u);
    }).catch(() => {});
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [visible, taskId, side, page, zoom]);
  return (
    <div ref={ref} className={`absolute inset-0 ${className}`} style={style}>
      {src ? <img src={src} alt="" draggable={false} className="w-full h-full select-none" />
        : <div className="w-full h-full bg-white flex items-center justify-center text-xs text-gray-400 whitespace-nowrap">กำลังโหลดหน้า...</div>}
    </div>
  );
}

function Marks({ marks, size, activeId, onPick }) {
  const [w, h] = size;
  return marks.map(({ change, rect, caret }, i) => {
    const k = KIND[change.kind];
    const active = change.id === activeId;
    const thin = rect.x1 - rect.x0 < 2;
    if (caret) {
      // ตำแหน่งที่ข้อความถูกลบ (ในไฟล์ใหม่) / ถูกเพิ่ม (ในไฟล์เดิม) — ลูกศรชี้ ไม่ใช่กรอบรอบคำ (กรอบดูเหมือนคำนั้นถูกแก้)
      const what = change.kind === "delete" ? "ข้อความถูกลบตรงนี้" : "ข้อความถูกเพิ่มตรงนี้";
      return (
        <button key={`${change.id}-${i}`} type="button" data-mark={change.id} aria-label={`จุดต่าง ${change.id}: ${what}`} title={what}
          onClick={() => onPick(change.id)} className={`absolute ${active ? "z-20 animate-pulse" : "z-10"}`}
          style={{ left: `${(rect.x0 / w) * 100}%`, top: `${(rect.y0 / h) * 100}%`, height: `${((rect.y1 - rect.y0) / h) * 100}%`,
            width: 0, borderLeft: `2px dashed ${k.color}`, marginLeft: -1 }}>
          <span className="absolute -top-2 -left-[6px] w-0 h-0 border-x-[5px] border-x-transparent border-t-[7px]" style={{ borderTopColor: k.color }} />
        </button>
      );
    }
    return (
      <button key={`${change.id}-${i}`} type="button" data-mark={change.id} aria-label={`จุดต่าง ${change.id}: ${k.label}`}
        onClick={() => onPick(change.id)}
        className={`absolute rounded-sm ${active ? "z-20 animate-pulse" : "z-10"}`}
        style={{
          left: `${(rect.x0 / w) * 100}%`, top: `${(rect.y0 / h) * 100}%`,
          width: thin ? 3 : `${((rect.x1 - rect.x0) / w) * 100}%`, height: `${((rect.y1 - rect.y0) / h) * 100}%`,
          background: `${k.color}${active ? "40" : "26"}`, outline: `${active ? 2 : 1}px solid ${k.color}`,
          marginLeft: thin ? -1 : 0,
        }} />
    );
  });
}

function Sheet({ size, width, children, label }) {
  const [w, h] = size;
  return (
    <div className="relative bg-white shadow-sm border border-gray-200 mx-auto" style={{ width, height: (width * h) / w }} aria-label={label}>
      {children}
    </div>
  );
}

function EmptySheet({ width, text }) {
  return (
    <div className="mx-auto border-2 border-dashed border-gray-300 rounded flex items-center justify-center text-sm text-gray-500 bg-gray-50"
      style={{ width, height: width * 1.3 }}>{text}</div>
  );
}

function ChangeItem({ change, active, onPick }) {
  const k = KIND[change.kind];
  const pages = (rects, anchor) => {
    const set = [...new Set(rects.map((r) => r.page + 1))];
    if (set.length) return set.join(", ");
    return anchor ? `${anchor.page + 1}` : "–";
  };
  return (
    <li>
      <button type="button" onClick={() => onPick(change.id)} data-change={change.id} aria-current={active ? "true" : undefined}
        className={`w-full text-left px-3 py-2 border-l-4 ${active ? "bg-blue-50" : "hover:bg-gray-50"}`} style={{ borderLeftColor: k.color }}>
        <div className="flex items-center gap-2 text-xs">
          <span className="font-mono text-gray-500">#{change.id}</span>
          <span className={`px-1.5 py-0.5 rounded ${k.bg}`}>{k.label}</span>
          <span className="ml-auto text-gray-500 whitespace-nowrap">หน้า {pages(change.a_rects, change.a_anchor)} → {pages(change.b_rects, change.b_anchor)}</span>
        </div>
        {(change.a_text || change.b_text) && (
          <p className="mt-1 text-sm break-words">
            {change.a_text && <span className="text-red-700 line-through decoration-red-400">{change.a_text}</span>}
            {change.a_text && change.b_text && <span className="text-gray-400"> → </span>}
            {change.b_text && <span className="text-green-700">{change.b_text}</span>}
          </p>
        )}
        {change.kind === "visual" && <p className="mt-1 text-sm text-gray-600">{change.note || "รูป เส้น ลายเซ็น หรือกราฟิกต่างกัน"}</p>}
      </button>
    </li>
  );
}

function Viewer({ taskId, data }) {
  const navigate = useNavigate();
  const result = data.result;
  const phone = useMedia(PHONE_LAYOUT_QUERY);
  const [mode, setMode] = useState("side");        // side | overlay
  const [phoneSide, setPhoneSide] = useState("b"); // มือถือแบบเคียงข้าง: แสดงทีละฝั่ง
  const [overlay, setOverlay] = useState("diff");  // diff | fade
  const [opacity, setOpacity] = useState(50);
  const [zoom, setZoom] = useState(1);
  const [activeId, setActiveId] = useState(null);
  const [hidden, setHidden] = useState(() => new Set());
  const [panel, setPanel] = useState(!phone);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mainRef = useRef(null);
  const [mainWidth, setMainWidth] = useState(800);

  useEffect(() => {
    const el = mainRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(([e]) => setMainWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const changes = useMemo(() => result.changes.filter((c) => !hidden.has(c.kind)), [result, hidden]);
  const marksBy = useMemo(() => {
    const m = { a: {}, b: {} };
    for (const c of changes) {
      for (const side of ["a", "b"]) {
        const real = c[`${side}_rects`];
        const rects = real.length ? real : (c[`${side}_anchor`] ? [c[`${side}_anchor`]] : []);
        for (const r of rects) (m[side][r.page] ||= []).push({ change: c, rect: r, caret: !real.length });
      }
    }
    return m;
  }, [changes]);

  const twoCols = mode === "side" && !phone;
  const gap = 16;
  const baseWidth = twoCols ? (mainWidth - 3 * gap) / 2 : Math.min(mainWidth - 2 * gap, 900);
  const width = Math.max(160, baseWidth * zoom);
  const pageZoom = useCallback((size) => {
    const z = (width / size[0]) * Math.min(window.devicePixelRatio || 1, 2);
    return Math.min(3, Math.max(0.5, Math.round(z * 4) / 4));
  }, [width]);

  const pick = useCallback((id) => {
    setActiveId(id);
    requestAnimationFrame(() => {
      document.querySelector(`[data-mark="${id}"]`)?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
      document.querySelector(`[data-change="${id}"]`)?.scrollIntoView({ block: "nearest" });
    });
    if (phone) setPanel(false);
  }, [phone]);

  const step = useCallback((dir) => {
    if (!changes.length) return;
    const idx = changes.findIndex((c) => c.id === activeId);
    const next = changes[(idx + dir + changes.length) % changes.length] || changes[0];
    if (phone && mode === "side") {
      const has = (s) => next[`${s}_rects`].length || next[`${s}_anchor`];
      if (!has(phoneSide)) setPhoneSide(phoneSide === "a" ? "b" : "a");
    }
    pick(next.id);
  }, [changes, activeId, pick, phone, mode, phoneSide]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest?.("input, textarea, select")) return;
      if (e.key === "j" || e.key === "ArrowDown" && e.altKey) { e.preventDefault(); step(1); }
      if (e.key === "k" || e.key === "ArrowUp" && e.altKey) { e.preventDefault(); step(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  async function download() {
    setBusy(true);
    setError("");
    try {
      const { blob, filename } = await downloadCompareReport(taskId);
      saveBlob(blob, filename);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const counts = result.summary;
  const kindsPresent = Object.keys(KIND).filter((k) => counts[k]);
  const btn = (on) => `px-2.5 py-1.5 text-sm rounded-md border ${on ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50"}`;

  const renderSide = (side, page, label) => {
    const size = result[side].page_sizes[page];
    return (
      <Sheet size={size} width={width} label={label}>
        <PageImage taskId={taskId} side={side} page={page} zoom={pageZoom(size)} />
        <Marks marks={marksBy[side][page] || []} size={size} activeId={activeId} onPick={pick} />
      </Sheet>
    );
  };

  const renderOverlay = (pa, pb) => {
    const size = result.b.page_sizes[pb];
    const marks = [...(marksBy.b[pb] || []), ...(marksBy.a[pa] || []).filter((m) => !m.change.b_rects.length)];
    return (
      <Sheet size={size} width={width} label={`ซ้อนทับหน้า ${pa + 1} กับ ${pb + 1}`}>
        <div className="absolute inset-0" style={overlay === "diff" ? { filter: "invert(1)" } : undefined}>
          <PageImage taskId={taskId} side="a" page={pa} zoom={pageZoom(size)} />
          <PageImage taskId={taskId} side="b" page={pb} zoom={pageZoom(size)}
            style={overlay === "diff" ? { mixBlendMode: "difference" } : { opacity: opacity / 100 }} />
        </div>
        <Marks marks={marks} size={size} activeId={activeId} onPick={pick} />
      </Sheet>
    );
  };

  return (
    <div className="h-dvh flex flex-col bg-gray-100" data-testid="compare-viewer">
      <header className="bg-white border-b border-gray-200 px-3 py-2 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => navigate(-1)} className="px-2 py-1.5 text-sm text-gray-700 rounded-md hover:bg-gray-100" aria-label="ย้อนกลับ">←</button>
        {/* มือถือ: ชื่อไฟล์เต็มแถว ปุ่มควบคุมขึ้นแถวถัดไป */}
        <div className="min-w-0 flex-1 phone:basis-[calc(100%-3rem)]">
          <h1 className="text-base font-bold text-gray-900 truncate">เปรียบเทียบเอกสาร</h1>
          <p className="text-xs text-gray-500 truncate" title={`${data.name_a} → ${data.name_b}`}>
            <span className="text-red-700">A: {data.name_a}</span> → <span className="text-green-700">B: {data.name_b}</span>
          </p>
        </div>
        <div className="flex items-center gap-1" role="group" aria-label="รูปแบบการแสดงผล">
          {phone && mode === "side" ? (
            <>
              <button type="button" className={btn(phoneSide === "a")} onClick={() => setPhoneSide("a")}>เดิม</button>
              <button type="button" className={btn(phoneSide === "b")} onClick={() => setPhoneSide("b")}>ใหม่</button>
            </>
          ) : (
            <button type="button" className={btn(mode === "side")} onClick={() => setMode("side")}>เคียงข้าง</button>
          )}
          <button type="button" className={btn(mode === "overlay")} onClick={() => setMode(mode === "overlay" && phone ? "side" : "overlay")}>ซ้อนทับ</button>
        </div>
        {mode === "overlay" && (
          <div className="flex items-center gap-1" role="group" aria-label="แบบซ้อนทับ">
            <button type="button" className={btn(overlay === "diff")} onClick={() => setOverlay("diff")} title="จุดที่ต่างเป็นสีเข้ม ที่เหมือนกันเป็นสีขาว">ไฮไลต์ต่าง</button>
            <button type="button" className={btn(overlay === "fade")} onClick={() => setOverlay("fade")}>โปร่งใส</button>
            {overlay === "fade" && <input type="range" min="0" max="100" value={opacity} aria-label="ความทึบของไฟล์ใหม่"
              onChange={(e) => setOpacity(Number(e.target.value))} className="w-24" />}
          </div>
        )}
        <div className="flex items-center gap-1" role="group" aria-label="ซูม">
          <button type="button" className={btn(false)} onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))} aria-label="ซูมออก">−</button>
          <span className="text-xs text-gray-600 w-10 text-center">{Math.round(zoom * 100)}%</span>
          <button type="button" className={btn(false)} onClick={() => setZoom((z) => Math.min(3, +(z + 0.25).toFixed(2)))} aria-label="ซูมเข้า">+</button>
        </div>
        <button type="button" onClick={download} disabled={busy} className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50">
          {busy ? "กำลังสร้าง..." : "ดาวน์โหลดรายงาน"}
        </button>
        {phone && (
          <button type="button" className={btn(panel)} onClick={() => setPanel((p) => !p)} aria-expanded={panel}>
            รายการ ({changes.length})
          </button>
        )}
      </header>
      {error && <p className="px-3 py-2 text-sm text-red-700 bg-red-50" role="alert">{error}</p>}

      <div className="flex-1 flex min-h-0 relative">
        <main ref={mainRef} className="flex-1 overflow-auto" aria-label="หน้าเอกสาร">
          {result.identical && (
            <div className="m-4 p-4 rounded-lg bg-green-50 border border-green-200 text-green-800 text-sm" role="status">
              ไม่พบจุดต่าง — ข้อความ{data.options?.visual ? "และภาพ" : ""}ของทั้งสองไฟล์ตรงกัน
            </div>
          )}
          {twoCols && (
            <div className="sticky top-0 z-30 grid grid-cols-2 gap-4 px-4 py-1 bg-gray-100/95 text-xs font-medium text-gray-600">
              <span className="truncate text-red-700">A · เดิม</span><span className="truncate text-green-700">B · ใหม่</span>
            </div>
          )}
          <div className="py-3 space-y-6" style={{ minWidth: twoCols ? 2 * width + 3 * gap : width + 2 * gap }}>
            {result.pairs.map(([pa, pb]) => (
              <section key={`${pa}-${pb}`} aria-label={`หน้า ${pa != null ? pa + 1 : "-"} เทียบกับ ${pb != null ? pb + 1 : "-"}`}>
                <p className="text-center text-xs text-gray-500 mb-1">
                  หน้า {pa != null ? pa + 1 : "—"} (A) · หน้า {pb != null ? pb + 1 : "—"} (B)
                  {pa == null && <span className="ml-1 text-green-700">หน้าที่เพิ่มใหม่</span>}
                  {pb == null && <span className="ml-1 text-red-700">หน้าที่ถูกลบ</span>}
                </p>
                {mode === "overlay" && pa != null && pb != null ? renderOverlay(pa, pb)
                  : twoCols ? (
                    <div className="grid gap-4 px-4" style={{ gridTemplateColumns: `${width}px ${width}px` }}>
                      {pa != null ? renderSide("a", pa, `ไฟล์เดิม หน้า ${pa + 1}`) : <EmptySheet width={width} text="ไม่มีหน้านี้ในไฟล์เดิม" />}
                      {pb != null ? renderSide("b", pb, `ไฟล์ใหม่ หน้า ${pb + 1}`) : <EmptySheet width={width} text="หน้านี้ถูกลบในไฟล์ใหม่" />}
                    </div>
                  ) : (
                    <div className="px-4">
                      {(() => {
                        const side = mode === "overlay" ? (pb != null ? "b" : "a") : phoneSide;
                        const page = side === "a" ? pa : pb;
                        return page != null ? renderSide(side, page, `${side === "a" ? "ไฟล์เดิม" : "ไฟล์ใหม่"} หน้า ${page + 1}`)
                          : <EmptySheet width={width} text={side === "a" ? "ไม่มีหน้านี้ในไฟล์เดิม" : "หน้านี้ถูกลบในไฟล์ใหม่"} />;
                      })()}
                    </div>
                  )}
              </section>
            ))}
          </div>
        </main>

        {panel && (
          <aside className={phone ? "absolute inset-x-0 bottom-0 z-40 max-h-[60%] bg-white border-t border-gray-200 shadow-2xl flex flex-col rounded-t-xl"
            : "w-80 shrink-0 bg-white border-l border-gray-200 flex flex-col"} aria-label="รายการจุดต่าง" data-testid="compare-list">
            <div className="p-3 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-gray-900">จุดต่าง {changes.length}{hidden.size ? ` จาก ${counts.total}` : ""} จุด</h2>
                <div className="ml-auto flex gap-1">
                  <button type="button" className={btn(false)} onClick={() => step(-1)} aria-label="จุดต่างก่อนหน้า" title="ก่อนหน้า (k)">↑</button>
                  <button type="button" className={btn(false)} onClick={() => step(1)} aria-label="จุดต่างถัดไป" title="ถัดไป (j)">↓</button>
                  {phone && <button type="button" className={btn(false)} onClick={() => setPanel(false)} aria-label="ปิดรายการ">✕</button>}
                </div>
              </div>
              {kindsPresent.length > 1 && (
                <div className="mt-2 flex flex-wrap gap-1" role="group" aria-label="กรองชนิดจุดต่าง">
                  {kindsPresent.map((k) => (
                    <button key={k} type="button" aria-pressed={!hidden.has(k)}
                      onClick={() => setHidden((h) => { const n = new Set(h); if (n.has(k)) n.delete(k); else n.add(k); return n; })}
                      className={`px-2 py-0.5 rounded text-xs ${hidden.has(k) ? "bg-gray-100 text-gray-400 line-through" : KIND[k].bg}`}>
                      {KIND[k].label} {counts[k]}
                    </button>
                  ))}
                </div>
              )}
              {[...(result.a.ocr_pages.length ? [`ไฟล์เดิมอ่านข้อความจากภาพ (OCR) หน้า ${result.a.ocr_pages.map((p) => p + 1).join(", ")}`] : []),
                ...(result.b.ocr_pages.length ? [`ไฟล์ใหม่อ่านข้อความจากภาพ (OCR) หน้า ${result.b.ocr_pages.map((p) => p + 1).join(", ")}`] : []),
                ...result.notes].map((n) => <p key={n} className="mt-2 text-xs text-gray-500">{n}</p>)}
            </div>
            <ul className="flex-1 overflow-y-auto divide-y divide-gray-100">
              {changes.map((c) => <ChangeItem key={c.id} change={c} active={c.id === activeId} onPick={pick} />)}
              {!changes.length && <li className="p-4 text-sm text-gray-500">{result.identical ? "ไม่พบจุดต่าง" : "ซ่อนทุกชนิดไว้ — กดชนิดด้านบนเพื่อแสดง"}</li>}
            </ul>
          </aside>
        )}
      </div>
    </div>
  );
}

export default function ComparePage() {
  const { taskId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    let timer;
    const poll = async () => {
      try {
        const d = await getCompare(taskId);
        if (!alive) return;
        setData(d);
        if (d.status === "pending" || d.status === "processing") timer = setTimeout(poll, 1000);
      } catch (e) {
        if (alive) setError(e.message);
      }
    };
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [taskId]);

  if (data?.status === "completed" && data.result) return <Viewer taskId={taskId} data={data} />;

  const failed = error || data?.status === "failed";
  return (
    <div className="min-h-dvh flex items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-sm border border-gray-200 p-6" data-testid="compare-progress">
        <h1 className="text-lg font-bold text-gray-900">เปรียบเทียบเอกสาร</h1>
        {data && <p className="mt-1 text-sm text-gray-500 break-words">{data.name_a} → {data.name_b}</p>}
        {failed ? (
          <>
            <p className="mt-4 text-sm text-red-700 bg-red-50 rounded p-3" role="alert">{error || data.error_message || "เปรียบเทียบไม่สำเร็จ"}</p>
            <button type="button" onClick={() => navigate("/dashboard")} className="mt-4 px-4 py-2 text-sm border border-gray-300 rounded-lg">กลับหน้าเอกสารของฉัน</button>
          </>
        ) : (
          <>
            <div className="mt-5 h-2 bg-gray-100 rounded-full overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={data?.progress || 0}>
              <div className="h-full bg-blue-600 transition-all" style={{ width: `${Math.max(3, data?.progress || 0)}%` }} />
            </div>
            <p className="mt-2 text-sm text-gray-600">{data?.stage || (data?.status === "pending" ? "รอคิว..." : "กำลังเริ่ม...")}</p>
            <p className="mt-1 text-xs text-gray-400">เอกสารยาวหรือไฟล์สแกนอาจใช้เวลาหลายนาที</p>
          </>
        )}
      </div>
    </div>
  );
}
