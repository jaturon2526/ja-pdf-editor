// ชั้นแก้ตารางบนหน้า (v1.40.0, ปรับปรุงมือจับบนมือถือ v1.41.4): กรอบตารางที่ตรวจเจอ → คลิกเลือก → ลากทั้งตาราง (ย้าย)
// · ลากเส้นด้านในหรือปุ่มจับสีฟ้าขอบบน/ขอบซ้าย (ความกว้างคอลัมน์/ความสูงแถว) · ลากขอบขวา/ล่าง/มุม (ย่อขยายทั้งตาราง)
// พรีวิว: ปิดตารางเดิมด้วยพื้นขาว แล้ววางภาพตัดของแต่ละเซลล์จากภาพหน้าปัจจุบันไว้ที่เซลล์ใหม่ (ชิดซ้ายบน) + เส้นตารางใหม่
// ผลจริง backend จัดตำแหน่งตามเดิมในเซลล์และตัดบรรทัดเซลล์ที่แคบลง (edit_service/tables.py)
// จุดลากเป็นของเมาส์/นิ้วเท่านั้น — คีย์บอร์ด/โปรแกรมอ่านหน้าจอใช้ช่องตัวเลข (มม.) ในแผง และปุ่มลูกศรย้ายตาราง
import { useRef, useState } from "react";
import { moveInnerLine, ptToMm, scaleTo, setSize, translate } from "../../utils/tableGeometry.js";
import { fontFamilyForKey } from "../../utils/textEditUtils.js";

const HIT = "[--hit:10px] [@media(pointer:coarse)]:[--hit:26px]";
const KNOB_HIT = 34; // พื้นที่นิ้วจับปุ่มสีฟ้านอกขอบตาราง (px) — ไม่ทับกันระหว่างคอลัมน์กับแถว

function useDrag(zoom, getStart, onMove, onDragState) {
  const ref = useRef(null);
  return {
    onPointerDown(e) {
      e.stopPropagation();
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      ref.current = { x: e.clientX, y: e.clientY, start: getStart(), shift: e.shiftKey };
      onDragState?.(true);
    },
    onPointerMove(e) {
      if (!ref.current) return;
      e.stopPropagation();
      onMove(ref.current.start, (e.clientX - ref.current.x) / zoom, (e.clientY - ref.current.y) / zoom, ref.current.shift);
    },
    onPointerUp(e) {
      if (!ref.current) return;
      e.stopPropagation();
      ref.current = null;
      onDragState?.(false);
    },
    onPointerCancel() {
      ref.current = null;
      onDragState?.(false);
    },
  };
}

function computeNextDraft(start, dx, dy, { axis, index, kind, expand }) {
  if (kind === "corner") {
    return { xs: scaleTo(start.xs, start.xs.at(-1) + dx), ys: scaleTo(start.ys, start.ys.at(-1) + dy) };
  }
  const lines = start[axis];
  const d = axis === "xs" ? dx : dy;
  let next;
  if (kind === "outer") {
    next = scaleTo(lines, lines.at(-1) + d);
  } else if (expand) {
    next = setSize(lines, index - 1, lines[index] - lines[index - 1] + d);
  } else {
    next = moveInnerLine(lines, index, lines[index] + d);
  }
  return { ...start, [axis]: next };
}

function Handle({ zoom, draft, expandMode, onUpdate, onActiveChange, axis, index, kind, label, style, cursor, className = "", children }) {
  const drag = useDrag(
    zoom,
    () => draft,
    (start, dx, dy, shift) => onUpdate(() => computeNextDraft(start, dx, dy, { axis, index, kind, expand: shift || expandMode })),
    (active) => onActiveChange?.(active ? { axis, index, kind } : null),
  );
  return (
    <div role="presentation" title={label} data-handle={label}
      className={`absolute z-20 touch-none ${HIT} ${className}`} style={{ ...style, cursor }} {...drag}>
      {children}
    </div>
  );
}

function activeSizeBadge(activeHandle, draft, zoom) {
  if (!activeHandle || !draft) return null;
  const { axis, index, kind } = activeHandle;
  const z = (v) => v * zoom;
  if (kind === "corner") {
    const w = ptToMm(draft.xs.at(-1) - draft.xs[0]);
    const h = ptToMm(draft.ys.at(-1) - draft.ys[0]);
    return { text: `${w} × ${h} มม.`, left: z(draft.xs.at(-1)), top: z(draft.ys.at(-1)) - 28 };
  }
  if (axis === "xs") {
    const mm = kind === "outer" ? ptToMm(draft.xs.at(-1) - draft.xs[0]) : ptToMm(draft.xs[index] - draft.xs[index - 1]);
    return { text: `${mm} มม.`, left: z(draft.xs[index]), top: z(draft.ys[0]) - 36 };
  }
  const mm = kind === "outer" ? ptToMm(draft.ys.at(-1) - draft.ys[0]) : ptToMm(draft.ys[index] - draft.ys[index - 1]);
  return { text: `${mm} มม.`, left: z(draft.xs[0]) + 14, top: z(draft.ys[index]) - 28 };
}

export default function TableEditLayer({
  tables,
  selected,
  draft,
  cellSelection = null,
  expandMode = false,
  zoom,
  pageSrc,
  pageWidthPt,
  pageHeightPt,
  onSelect,
  onCellClick,
  onUpdate,
  cellText = "",
  cellFontKey = "sarabun",
  cellFontSize = 11,
  cellColorHex = "#000000",
  cellTextAlign = "",
  cellUnderline = false,
  onCellTextChange,
  onSaveCellText,
  editingCellOnCanvas = false,
  onSetEditingCellOnCanvas,
}) {
  const [activeHandle, setActiveHandle] = useState(null);
  const moveRef = useRef(null);
  const moveDrag = {
    onPointerDown(e) {
      e.stopPropagation();
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      moveRef.current = { x: e.clientX, y: e.clientY, start: draft, moved: false, shift: e.shiftKey };
    },
    onPointerMove(e) {
      if (!moveRef.current) return;
      e.stopPropagation();
      const dxPx = e.clientX - moveRef.current.x;
      const dyPx = e.clientY - moveRef.current.y;
      if (!moveRef.current.moved && Math.hypot(dxPx, dyPx) < 4) return;
      moveRef.current.moved = true;
      onUpdate(() => ({
        xs: translate(moveRef.current.start.xs, dxPx / zoom),
        ys: translate(moveRef.current.start.ys, dyPx / zoom),
      }));
    },
    onPointerUp(e) {
      if (!moveRef.current) return;
      e.stopPropagation();
      const st = moveRef.current;
      moveRef.current = null;
      if (!st.moved && selected && draft && onCellClick) {
        const box = e.currentTarget.getBoundingClientRect();
        const xPt = draft.xs[0] + (e.clientX - box.left) / zoom;
        const yPt = draft.ys[0] + (e.clientY - box.top) / zoom;
        const hit = selected.cells.find((c) => (
          xPt >= draft.xs[c.c] && xPt <= draft.xs[c.c + c.colspan]
          && yPt >= draft.ys[c.r] && yPt <= draft.ys[c.r + c.rowspan]
        ));
        if (hit) onCellClick(hit, st.shift);
      }
    },
    onPointerCancel() {
      moveRef.current = null;
    },
  };
  if (!tables) return null;
  const z = (v) => v * zoom;

  return (
    <div className="absolute inset-0" data-testid="table-edit-layer">
      {tables.filter((t) => t.id !== selected?.id).map((t, i) => (
        <button key={t.id} type="button" aria-label={`เลือกตารางที่ ${i + 1} (${t.ys.length - 1} แถว × ${t.xs.length - 1} คอลัมน์)`}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => { e.stopPropagation(); onSelect(t.id); }}
          className="absolute border-2 border-dashed border-sky-500/70 bg-sky-400/5 hover:bg-sky-400/15 rounded-sm cursor-pointer"
          style={{ left: z(t.bbox.x0), top: z(t.bbox.y0), width: z(t.bbox.x1 - t.bbox.x0), height: z(t.bbox.y1 - t.bbox.y0) }} />
      ))}

      {selected && draft && (() => {
        const { xs, ys } = draft;
        const changed = xs.some((v, i) => v !== selected.xs[i]) || ys.some((v, i) => v !== selected.ys[i]);
        const badge = activeSizeBadge(activeHandle, draft, zoom);
        const topY = z(ys[0]);
        const botY = z(ys.at(-1));
        const leftX = z(xs[0]);
        const rightX = z(xs.at(-1));
        const midX = (leftX + rightX) / 2;
        const midY = (topY + botY) / 2;
        const isLineActive = (axis, i) => activeHandle && activeHandle.axis === axis && activeHandle.index === i;

        return (
          <>
            {changed && (
              <div className="absolute bg-white" aria-hidden="true"
                style={{ left: z(selected.bbox.x0 - 1.5), top: z(selected.bbox.y0 - 1.5),
                  width: z(selected.bbox.x1 - selected.bbox.x0 + 3), height: z(selected.bbox.y1 - selected.bbox.y0 + 3) }} />
            )}
            {changed && pageSrc && selected.cells.map((c) => {
              const ox0 = selected.xs[c.c], oy0 = selected.ys[c.r];
              const ow = selected.xs[c.c + c.colspan] - ox0, oh = selected.ys[c.r + c.rowspan] - oy0;
              const nx0 = xs[c.c], ny0 = ys[c.r];
              const nw = xs[c.c + c.colspan] - nx0, nh = ys[c.r + c.rowspan] - ny0;
              return (
                <div key={`${c.r}-${c.c}`} aria-hidden="true" className="absolute"
                  style={{
                    // ตัดขอบเซลล์เดิมออก 1 pt ไม่ให้เส้นตารางเก่าติดมาในพรีวิว
                    left: z(nx0 + 1), top: z(ny0 + 1), width: z(Math.max(0, Math.min(ow, nw) - 2)), height: z(Math.max(0, Math.min(oh, nh) - 2)),
                    backgroundImage: `url(${pageSrc})`, backgroundRepeat: "no-repeat",
                    backgroundSize: `${z(pageWidthPt)}px ${z(pageHeightPt)}px`,
                    backgroundPosition: `${-z(ox0 + 1)}px ${-z(oy0 + 1)}px`,
                  }} />
              );
            })}
            <svg className="absolute inset-0 pointer-events-none overflow-visible" width={z(pageWidthPt)} height={z(pageHeightPt)} aria-hidden="true">
              {xs.map((x, i) => {
                const hi = isLineActive("xs", i);
                const stroke = hi || !changed ? "#0284c7" : "#0f172a";
                let strokeWidth = 1.5;
                if (hi) strokeWidth = 2.5;
                else if (changed) strokeWidth = 1;
                return (
                  <line key={`x${i}`} x1={z(x)} x2={z(x)} y1={topY} y2={botY} stroke={stroke} strokeWidth={strokeWidth} />
                );
              })}
              {ys.map((y, i) => {
                const hi = isLineActive("ys", i);
                const stroke = hi || !changed ? "#0284c7" : "#0f172a";
                let strokeWidth = 1.5;
                if (hi) strokeWidth = 2.5;
                else if (changed) strokeWidth = 1;
                return (
                  <line key={`y${i}`} y1={z(y)} y2={z(y)} x1={leftX} x2={rightX} stroke={stroke} strokeWidth={strokeWidth} />
                );
              })}
              <rect x={leftX - 3} y={topY - 3} width={rightX - leftX + 6} height={botY - topY + 6}
                fill="none" stroke="#0284c7" strokeWidth="1.5" strokeDasharray="6 4" />
            </svg>
            {cellSelection && !changed && cellSelection.r1 + 1 < ys.length && cellSelection.c1 + 1 < xs.length && (
              <div
                aria-hidden="true"
                data-testid="table-cell-selection"
                className="absolute pointer-events-none bg-blue-500/20 border-2 border-blue-600 rounded-[2px] z-[12]"
                style={{
                  left: z(xs[cellSelection.c0]),
                  top: z(ys[cellSelection.r0]),
                  width: z(xs[cellSelection.c1 + 1] - xs[cellSelection.c0]),
                  height: z(ys[cellSelection.r1 + 1] - ys[cellSelection.r0]),
                }}
              />
            )}
            <div
              role="presentation"
              title="คลิกเพื่อเลือกเซลล์ · ดับเบิลคลิกเพื่อพิมพ์ข้อความในเซลล์ · ลากเพื่อย้ายตาราง"
              data-handle="ย้ายตาราง"
              className="absolute z-10 cursor-move touch-none"
              style={{ left: leftX, top: topY, width: rightX - leftX, height: botY - topY }}
              onDoubleClick={(e) => {
                if (!selected || !draft || !onCellClick) return;
                e.stopPropagation();
                const box = e.currentTarget.getBoundingClientRect();
                const xPt = draft.xs[0] + (e.clientX - box.left) / zoom;
                const yPt = draft.ys[0] + (e.clientY - box.top) / zoom;
                const hit = selected.cells.find((c) => (
                  xPt >= draft.xs[c.c] && xPt <= draft.xs[c.c + c.colspan]
                  && yPt >= draft.ys[c.r] && yPt <= draft.ys[c.r + c.rowspan]
                ));
                if (hit) onCellClick(hit, false, true);
              }}
              {...moveDrag}
            />

            {/* ช่องพิมพ์ข้อความลงในเซลล์บนหน้ากระดาษโดยตรง (เมื่อเพิ่มแถว/คอลัมน์ หรือดับเบิลคลิก/คลิกซ้ำที่เซลล์) */}
            {editingCellOnCanvas && cellSelection && !changed && cellSelection.r1 + 1 < ys.length && cellSelection.c1 + 1 < xs.length && (
              <input
                type="text"
                aria-label="พิมพ์ข้อความในเซลล์"
                data-testid="table-inline-cell-input"
                value={cellText || ""}
                placeholder="พิมพ์..."
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => onCellTextChange?.(e.target.value)}
                onKeyDown={(e) => {
                  e.stopPropagation();
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void onSaveCellText?.(cellText, { moveRow: 1 });
                  } else if (e.key === "Tab") {
                    e.preventDefault();
                    void onSaveCellText?.(cellText, { moveCol: e.shiftKey ? -1 : 1 });
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    onSetEditingCellOnCanvas?.(false);
                  }
                }}
                className="absolute z-30 bg-white/95 border-2 border-sky-600 rounded-[2px] px-1 shadow-sm focus:outline-none"
                style={{
                  left: z(xs[cellSelection.c0]),
                  top: z(ys[cellSelection.r0]),
                  width: Math.max(44, z(xs[cellSelection.c1 + 1] - xs[cellSelection.c0])),
                  height: Math.max(20, z(ys[cellSelection.r1 + 1] - ys[cellSelection.r0])),
                  fontFamily: fontFamilyForKey(cellFontKey || "sarabun"),
                  fontSize: `${Math.max(10, (Number(cellFontSize) || 11) * zoom)}px`,
                  color: cellColorHex || "#0f172a",
                  textAlign: cellTextAlign || "left",
                  textDecoration: cellUnderline ? "underline" : "none",
                }}
              />
            )}

            {/* เส้นแบ่งคอลัมน์ด้านใน + ปุ่มจับสีฟ้าด้านบนตาราง (ใช้นิ้วลากขยายคอลัมน์ได้ง่ายบนมือถือ) */}
            {xs.slice(1, -1).map((x, k) => {
              const i = k + 1;
              const gapX = Math.min(z(xs[i] - xs[i - 1]), z(xs[i + 1] - xs[i]));
              const knobW = Math.min(KNOB_HIT, Math.max(12, Math.floor(gapX - 2)));
              return (
                <div key={`hx${i}`}>
                  <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
                    axis="xs" index={i} kind="inner" label={`เส้นแบ่งคอลัมน์ที่ ${i}`} cursor="col-resize"
                    style={{ left: `calc(${z(x)}px - var(--hit) / 2)`, top: topY, width: "var(--hit)", height: botY - topY }} />
                  <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
                    axis="xs" index={i} kind="inner" label={`จับปรับคอลัมน์ที่ ${i}`} cursor="col-resize"
                    className="z-30 flex items-center justify-center"
                    style={{ left: z(x) - knobW / 2, top: topY - KNOB_HIT / 2 - 4, width: knobW, height: KNOB_HIT }}>
                    <span aria-hidden="true" className={`block rounded-full border-2 border-white shadow transition-transform ${isLineActive("xs", i) ? "w-2.5 h-5 bg-sky-700 scale-110" : "w-2 h-4 bg-sky-500"}`} />
                  </Handle>
                </div>
              );
            })}

            {/* เส้นแบ่งแถวด้านใน + ปุ่มจับสีฟ้าด้านซ้ายตาราง (ใช้นิ้วลากปรับความสูงแถวได้ง่ายบนมือถือ) */}
            {ys.slice(1, -1).map((y, k) => {
              const i = k + 1;
              const gapY = Math.min(z(ys[i] - ys[i - 1]), z(ys[i + 1] - ys[i]));
              const knobH = Math.min(KNOB_HIT, Math.max(12, Math.floor(gapY - 2)));
              return (
                <div key={`hy${i}`}>
                  <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
                    axis="ys" index={i} kind="inner" label={`เส้นแบ่งแถวที่ ${i}`} cursor="row-resize"
                    style={{ top: `calc(${z(y)}px - var(--hit) / 2)`, left: leftX, height: "var(--hit)", width: rightX - leftX }} />
                  <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
                    axis="ys" index={i} kind="inner" label={`จับปรับแถวที่ ${i}`} cursor="row-resize"
                    className="z-30 flex items-center justify-center"
                    style={{ left: leftX - KNOB_HIT / 2 - 4, top: z(y) - knobH / 2, width: KNOB_HIT, height: knobH }}>
                    <span aria-hidden="true" className={`block rounded-full border-2 border-white shadow transition-transform ${isLineActive("ys", i) ? "w-5 h-2.5 bg-sky-700 scale-110" : "w-4 h-2 bg-sky-500"}`} />
                  </Handle>
                </div>
              );
            })}

            {/* ขอบขวา + ปุ่มจับกึ่งกลางขอบขวา */}
            <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
              axis="xs" index={xs.length - 1} kind="outer" label="ขอบขวา (ย่อขยายความกว้างทั้งตาราง)" cursor="ew-resize"
              style={{ left: `calc(${rightX}px - var(--hit) / 2)`, top: topY, width: "var(--hit)", height: botY - topY }} />
            <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
              axis="xs" index={xs.length - 1} kind="outer" label="จับขยายความกว้างทั้งตาราง" cursor="ew-resize"
              className="z-30 flex items-center justify-center"
              style={{ left: rightX - KNOB_HIT / 2 + 4, top: midY - KNOB_HIT / 2, width: KNOB_HIT, height: KNOB_HIT }}>
              <span aria-hidden="true" className="block w-2 h-5 rounded-full bg-white border-2 border-sky-600 shadow" />
            </Handle>

            {/* ขอบล่าง + ปุ่มจับกึ่งกลางขอบล่าง */}
            <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
              axis="ys" index={ys.length - 1} kind="outer" label="ขอบล่าง (ย่อขยายความสูงทั้งตาราง)" cursor="ns-resize"
              style={{ top: `calc(${botY}px - var(--hit) / 2)`, left: leftX, height: "var(--hit)", width: rightX - leftX }} />
            <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
              axis="ys" index={ys.length - 1} kind="outer" label="จับขยายความสูงทั้งตาราง" cursor="ns-resize"
              className="z-30 flex items-center justify-center"
              style={{ left: midX - KNOB_HIT / 2, top: botY - KNOB_HIT / 2 + 4, width: KNOB_HIT, height: KNOB_HIT }}>
              <span aria-hidden="true" className="block w-5 h-2 rounded-full bg-white border-2 border-sky-600 shadow" />
            </Handle>

            {/* มุมขวาล่าง */}
            <Handle zoom={zoom} draft={draft} expandMode={expandMode} onUpdate={onUpdate} onActiveChange={setActiveHandle}
              axis="xs" index={xs.length - 1} kind="corner" label="มุมขวาล่าง (ย่อขยายทั้งตาราง)" cursor="nwse-resize"
              className="z-30 flex items-center justify-center"
              style={{ left: rightX - KNOB_HIT / 2, top: botY - KNOB_HIT / 2, width: KNOB_HIT, height: KNOB_HIT }}>
              <span aria-hidden="true" className="block w-4 h-4 bg-white border-2 border-sky-600 rounded-sm shadow" />
            </Handle>

            {/* ป้ายบอกขนาด มม. ระหว่างลาก (ไม่ให้นิ้วบังค่า) */}
            {badge && (
              <div aria-hidden="true"
                className="absolute z-40 px-2 py-0.5 rounded bg-slate-900/90 text-white text-[11px] font-medium whitespace-nowrap pointer-events-none shadow -translate-x-1/2"
                style={{ left: badge.left, top: Math.max(4, badge.top) }}>
                {badge.text}
              </div>
            )}
          </>
        );
      })()}
    </div>
  );
}
