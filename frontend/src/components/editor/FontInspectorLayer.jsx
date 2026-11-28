// ชั้นกรอบข้อความบนหน้า สำหรับเครื่องมือ "ตรวจฟอนต์" — ชี้ดู (title) / คลิกหรือแตะเพื่อดูรายละเอียดในแผง
import { useI18n } from "../../i18n/I18nContext.jsx";
import { sizeLabel } from "../../utils/fontInfo.js";

export default function FontInspectorLayer({ spans, zoom, selected, onSelect }) {
  const { t } = useI18n();
  if (!spans?.length) return null;
  return (
    <div className="absolute inset-0" data-testid="font-inspector-layer">
      {spans.map((s, i) => {
        const isSel = selected === i;
        return (
          <button
            key={i}
            type="button"
            aria-label={t("editor.panels.fontInspector.spanAria", {
              text: s.text.slice(0, 40),
              name: s.name,
              size: sizeLabel(s.size),
            })}
            aria-pressed={isSel}
            title={`${s.name} · ${sizeLabel(s.size)}`}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); onSelect(isSel ? null : i); }}
            className={`absolute p-0 border rounded-[2px] cursor-help ${isSel
              ? "border-fuchsia-600 bg-fuchsia-500/20"
              : "border-transparent hover:border-fuchsia-500 hover:bg-fuchsia-400/10 focus-visible:border-fuchsia-500"}`}
            style={{
              left: s.bbox.x0 * zoom,
              top: s.bbox.y0 * zoom,
              width: Math.max(4, (s.bbox.x1 - s.bbox.x0) * zoom),
              height: Math.max(4, (s.bbox.y1 - s.bbox.y0) * zoom),
            }}
          />
        );
      })}
    </div>
  );
}
