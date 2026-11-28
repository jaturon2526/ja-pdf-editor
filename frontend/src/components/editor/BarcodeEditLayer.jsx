// ชั้นย้าย/ลบบาร์โค้ดบนหน้า (v1.41.0): กรอบบาร์โค้ด/QR ที่อ่านเจอ → คลิกเลือก → ลากย้าย
// พรีวิว: ปิดที่เดิมด้วยพื้นขาว + ครอปภาพหน้าส่วนบาร์โค้ดไปวางที่ใหม่ · ผลจริง backend ย้ายแบบเวกเตอร์ (edit_service/barcodes.py)
// จุดลากเป็นของเมาส์/นิ้ว — คีย์บอร์ดใช้ช่องตำแหน่ง (มม.) ในแผง และปุ่มลูกศร
import { useRef } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";

export function barcodeLabel(b) {
  const text = b.text.length > 40 ? `${b.text.slice(0, 40)}…` : b.text;
  return `${b.format} “${text}”`;
}

export default function BarcodeEditLayer({ barcodes, selected, draft, zoom, pageSrc, pageWidthPt, pageHeightPt, onSelect, onMoveTo }) {
  const { t } = useI18n();
  const drag = useRef(null);
  if (!barcodes) return null;
  const z = (v) => v * zoom;
  const box = (r) => ({ left: z(r.x0), top: z(r.y0), width: z(r.x1 - r.x0), height: z(r.y1 - r.y0) });

  const handlers = {
    onPointerDown(e) {
      e.stopPropagation();
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      drag.current = { x: e.clientX, y: e.clientY, x0: draft.x0, y0: draft.y0 };
    },
    onPointerMove(e) {
      const d = drag.current;
      if (!d) return;
      e.stopPropagation();
      onMoveTo(d.x0 + (e.clientX - d.x) / zoom, d.y0 + (e.clientY - d.y) / zoom);
    },
    onPointerUp(e) {
      if (!drag.current) return;
      e.stopPropagation();
      drag.current = null;
    },
    onPointerCancel() { drag.current = null; },
  };

  const changed = selected && draft && (draft.x0 !== selected.bbox.x0 || draft.y0 !== selected.bbox.y0);
  const old = selected?.bbox;
  return (
    <div className="absolute inset-0" data-testid="barcode-edit-layer">
      {barcodes.filter((b) => b.id !== selected?.id).map((b, i) => (
        <button key={b.id} type="button" aria-label={t("editor.panels.barcodeEdit.selectBarcodeAria", { index: i + 1, label: barcodeLabel(b) })}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => { e.stopPropagation(); onSelect(b.id); }}
          className="absolute border-2 border-dashed border-violet-500/80 bg-violet-400/5 hover:bg-violet-400/15 rounded-sm cursor-pointer"
          style={box(b.bbox)} />
      ))}
      {selected && draft && (
        <>
          {changed && <div className="absolute bg-white" aria-hidden="true" style={box(old)} />}
          {changed && pageSrc && (
            <div aria-hidden="true" className="absolute" style={{
              ...box(draft),
              backgroundImage: `url(${pageSrc})`, backgroundRepeat: "no-repeat",
              backgroundSize: `${z(pageWidthPt)}px ${z(pageHeightPt)}px`,
              backgroundPosition: `${-z(old.x0)}px ${-z(old.y0)}px`,
            }} />
          )}
          <div role="presentation" title={t("editor.panels.barcodeEdit.dragTitle")} data-handle={t("editor.panels.barcodeEdit.moveHandle")}
            className="absolute z-10 cursor-move touch-none outline-2 outline-dashed outline-violet-600 outline-offset-2 rounded-sm"
            style={box(draft)} {...handlers} />
        </>
      )}
    </div>
  );
}
