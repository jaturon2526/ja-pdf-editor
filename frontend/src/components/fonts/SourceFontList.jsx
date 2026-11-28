// รายการฟอนต์จริงในไฟล์ของข้อความช่วงหนึ่ง: ชื่อ · ขนาด · สี · หนา/เอียง · การฝัง (ตรวจฟอนต์ v1.38.0)
import { useI18n } from "../../i18n/I18nContext.jsx";
import { embedLabel, embedTone, sizeLabel, styleLabel } from "../../utils/fontInfo.js";

export default function SourceFontList({ fonts, showChars = false }) {
  const { t } = useI18n();
  if (!fonts?.length) return null;
  return (
    <ul className="space-y-1.5" data-testid="source-fonts">
      {fonts.map((f) => (
        <li key={`${f.name}-${f.size}-${f.color}-${f.bold}-${f.italic}`} className="text-xs text-slate-700">
          <span className="block font-medium text-slate-900 break-all">{f.name}</span>
          <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-slate-600">
            <span>{sizeLabel(f.size)}</span>
            <span aria-hidden="true">·</span>
            <span>{styleLabel(f, t)}</span>
            <span aria-hidden="true">·</span>
            <span className="inline-flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-sm border border-slate-300" style={{ background: f.color }} aria-hidden="true" />
              {f.color}
            </span>
            {showChars && f.chars > 0 && (<><span aria-hidden="true">·</span><span>{t("fontInfo.charsCount", { count: f.chars })}</span></>)}
          </span>
          <span className={`block ${embedTone(f) === "warn" ? "text-amber-700" : "text-slate-500"}`}>
            {f.type ? `${f.type} · ` : ""}{embedLabel(f, t)}
          </span>
        </li>
      ))}
    </ul>
  );
}
