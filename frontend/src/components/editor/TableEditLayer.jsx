// ชั้นแก้ตารางบนหน้า (v1.40.0): กรอบตารางที่ตรวจเจอ → คลิกเลือก → ลากทั้งตาราง (ย้าย) · ลากเส้นด้านใน (ความกว้างคอลัมน์/
// ความสูงแถว) · ลากขอบขวา/ล่าง/มุม (ย่อขยายทั้งตาราง)
// พรีวิว: ปิดตารางเดิมด้วยพื้นขาว แล้ววางภาพตัดของแต่ละเซลล์จากภาพหน้าปัจจุบันไว้ที่เซลล์ใหม่ (ชิดซ้ายบน) + เส้นตารางใหม่
// ผลจริง backend จัดตำแหน่งตามเดิมในเซลล์และตัดบรรทัดเซลล์ที่แคบลง (edit_service/tables.py)
// จุดลากเป็นของเมาส์/นิ้วเท่านั้น — คีย์บอร์ด/โปรแกรมอ่านหน้าจอใช้ช่องตัวเลข (มม.) ในแผง และปุ่มลูกศรย้ายตาราง
import { useRef } from "react";
import { moveInnerLine, scaleTo, setSize, translate } from "../../utils/tableGeometry.js";

const HIT = "[--hit:10px] [@media(pointer:coarse)]:[--hit:22px]";

function useDrag(zoom, getStart, onMove) {
  const ref = useRef(null);
  return {
    onPointerDown(e) {
      e.stopPropagation();
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      ref.current = { x: e.clientX, y: e.clientY, start: getStart(), shift: e.shiftKey };
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
    },
    onPointerCancel() { ref.current = null; },
  };
}

function Handle({ zoom, draft, onUpdate, axis, index, kind, label, style, cursor }) {
  const drag = useDrag(zoom, () => draft, (start, dx, dy, shift) => onUpdate(() => {
    if (kind === "corner") return { xs: scaleTo(start.xs, start.xs.at(-1) + dx), ys: scaleTo(start.ys, start.ys.at(-1) + dy) };
    const lines = start[axis];
    const d = axis === "xs" ? dx : dy;
    // เส้นด้านใน: ปกติช่องสองข้างเปลี่ยน (ความกว้างรวมเท่าเดิม) · กด Shift ค้างตอนเริ่มลาก = ช่องถัดไปเลื่อนตาม (ตารางกว้าง/สูงขึ้น)
    const next = kind === "outer" ? scaleTo(lines, lines.at(-1) + d)
      : shift ? setSize(lines, index - 1, lines[index] - lines[index - 1] + d)
      : moveInnerLine(lines, index, lines[index] + d);
    return { ...start, [axis]: next };
  }));
  return (
    <div role="presentation" title={label} data-handle={label}
      className={`absolute z-20 touch-none ${HIT}`} style={{ ...style, cursor }} {...drag} />
  );
}

export default function TableEditLayer({ tables, selected, draft, zoom, pageSrc, pageWidthPt, pageHeightPt, onSelect, onUpdate }) {
  const moveDrag = useDrag(zoom, () => draft, (start, dx, dy) => onUpdate(() => ({ xs: translate(start.xs, dx), ys: translate(start.ys, dy) })));
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
              {xs.map((x, i) => <line key={`x${i}`} x1={z(x)} x2={z(x)} y1={z(ys[0])} y2={z(ys.at(-1))} stroke={changed ? "#0f172a" : "#0284c7"} strokeWidth={changed ? 1 : 1.5} />)}
              {ys.map((y, i) => <line key={`y${i}`} y1={z(y)} y2={z(y)} x1={z(xs[0])} x2={z(xs.at(-1))} stroke={changed ? "#0f172a" : "#0284c7"} strokeWidth={changed ? 1 : 1.5} />)}
              <rect x={z(xs[0]) - 3} y={z(ys[0]) - 3} width={z(xs.at(-1) - xs[0]) + 6} height={z(ys.at(-1) - ys[0]) + 6}
                fill="none" stroke="#0284c7" strokeWidth="1.5" strokeDasharray="6 4" />
            </svg>
            <div role="presentation" title="ลากเพื่อย้ายตาราง" data-handle="ย้ายตาราง" className="absolute z-10 cursor-move touch-none"
              style={{ left: z(xs[0]), top: z(ys[0]), width: z(xs.at(-1) - xs[0]), height: z(ys.at(-1) - ys[0]) }} {...moveDrag} />
            {xs.slice(1, -1).map((x, k) => (
              <Handle key={`hx${k + 1}`} zoom={zoom} draft={draft} onUpdate={onUpdate} axis="xs" index={k + 1} kind="inner"
                label={`เส้นแบ่งคอลัมน์ที่ ${k + 1}`} cursor="col-resize"
                style={{ left: `calc(${z(x)}px - var(--hit) / 2)`, top: z(ys[0]), width: "var(--hit)", height: z(ys.at(-1) - ys[0]) }} />
            ))}
            {ys.slice(1, -1).map((y, k) => (
              <Handle key={`hy${k + 1}`} zoom={zoom} draft={draft} onUpdate={onUpdate} axis="ys" index={k + 1} kind="inner"
                label={`เส้นแบ่งแถวที่ ${k + 1}`} cursor="row-resize"
                style={{ top: `calc(${z(y)}px - var(--hit) / 2)`, left: z(xs[0]), height: "var(--hit)", width: z(xs.at(-1) - xs[0]) }} />
            ))}
            <Handle zoom={zoom} draft={draft} onUpdate={onUpdate} axis="xs" index={xs.length - 1} kind="outer"
              label="ขอบขวา (ย่อขยายความกว้างทั้งตาราง)" cursor="ew-resize"
              style={{ left: `calc(${z(xs.at(-1))}px - var(--hit) / 2)`, top: z(ys[0]), width: "var(--hit)", height: z(ys.at(-1) - ys[0]) }} />
            <Handle zoom={zoom} draft={draft} onUpdate={onUpdate} axis="ys" index={ys.length - 1} kind="outer"
              label="ขอบล่าง (ย่อขยายความสูงทั้งตาราง)" cursor="ns-resize"
              style={{ top: `calc(${z(ys.at(-1))}px - var(--hit) / 2)`, left: z(xs[0]), height: "var(--hit)", width: z(xs.at(-1) - xs[0]) }} />
            <Handle zoom={zoom} draft={draft} onUpdate={onUpdate} axis="xs" index={xs.length - 1} kind="corner"
              label="มุมขวาล่าง (ย่อขยายทั้งตาราง)" cursor="nwse-resize"
              style={{ left: `calc(${z(xs.at(-1))}px - var(--hit))`, top: `calc(${z(ys.at(-1))}px - var(--hit))`,
                width: "calc(var(--hit) * 2)", height: "calc(var(--hit) * 2)" }} />
            <span aria-hidden="true" className="absolute z-30 w-3 h-3 bg-white border-2 border-sky-600 rounded-sm pointer-events-none"
              style={{ left: z(xs.at(-1)) - 6, top: z(ys.at(-1)) - 6 }} />
          </>
        );
      })()}
    </div>
  );
}
