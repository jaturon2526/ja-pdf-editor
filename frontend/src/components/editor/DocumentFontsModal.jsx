// รายการฟอนต์ทั้งเอกสาร (แบบ Acrobat › คุณสมบัติ › ฟอนต์) — ชนิด การฝัง และหน้าที่ใช้ (ตรวจฟอนต์ v1.38.0)
import { useEffect, useState } from "react";
import * as api from "../../api.js";
import { embedLabel, embedTone, pagesLabel } from "../../utils/fontInfo.js";

export default function DocumentFontsModal({ sessionId, onClose }) {
  const [fonts, setFonts] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.getDocumentFonts(sessionId)
      .then((list) => { if (!cancelled) setFonts(list); })
      .catch((e) => { if (!cancelled) { setFonts([]); setError(e.message || "อ่านรายการฟอนต์ไม่สำเร็จ"); } });
    return () => { cancelled = true; };
  }, [sessionId]);

  const notEmbedded = (fonts || []).filter((f) => embedTone(f) === "warn").length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40" role="presentation" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="doc-fonts-title" onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[85dvh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
          <h3 id="doc-fonts-title" className="text-lg font-bold text-slate-900">ฟอนต์ในเอกสาร</h3>
          <button type="button" onClick={onClose} aria-label="ปิด" className="icon-btn">✕</button>
        </div>
        <div className="px-5 py-4 overflow-y-auto">
          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          {fonts === null && <p className="text-sm text-slate-500">กำลังอ่าน...</p>}
          {fonts?.length === 0 && !error && <p className="text-sm text-slate-600">ไม่มีฟอนต์ในเอกสารนี้ (อาจเป็นภาพสแกนทั้งหมด)</p>}
          {fonts?.length > 0 && (
            <>
              <p className="text-sm text-slate-600 mb-3">
                {fonts.length} ฟอนต์{notEmbedded > 0 && <span className="text-amber-700"> · ไม่ได้ฝัง {notEmbedded} ฟอนต์ (เครื่องอื่นอาจแสดงต่างไป)</span>}
              </p>
              <ul className="divide-y divide-slate-100 border border-slate-200 rounded-lg" data-testid="document-fonts">
                {fonts.map((f) => (
                  <li key={`${f.name}-${f.type}`} className="px-3 py-2 text-sm">
                    <span className="block font-medium text-slate-900 break-all">{f.name}</span>
                    <span className="block text-xs text-slate-600">{f.type} · หน้า {pagesLabel(f.pages)}</span>
                    <span className={`block text-xs ${embedTone(f) === "warn" ? "text-amber-700" : "text-slate-500"}`}>{embedLabel(f)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
