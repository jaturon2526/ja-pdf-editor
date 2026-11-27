// แปลง PDF เป็น Word — เลือกรูปแบบ แล้วแสดงความคืบหน้า/ผลลัพธ์ (แยกมาจาก Dashboard.jsx)
//
// โหมด:
// - editable : ข้อความไหลเป็นย่อหน้า/ตาราง แก้ไขต่อได้สะดวก (AI ช่วยแก้คำไทย ใช้โควต้า AI)
// - layout   : หน้าตาเหมือนต้นฉบับ (ภาพพื้นหลัง + กล่องข้อความวางตำแหน่งเดิม) เหมาะกับไฟล์ที่ออกแบบสวยๆ
//              หรือฟอร์มที่แค่จะกรอก/แก้คำ — ไม่ใช้โควต้า AI
// - scan     : ไฟล์สแกน (ตรวจอัตโนมัติ) — อ่านข้อความด้วย OCR บนเซิร์ฟเวอร์ ลายเซ็น/โลโก้/บาร์โค้ดเป็นรูป
//              AI แก้คำไทยเป็นตัวเลือก (ปิดเป็นค่าเริ่มต้น)
import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";

export const CONVERSION_MODES = [
  {
    key: "editable",
    titleKey: "wordConv.editableTitle",
    detailAiKey: "wordConv.editableDetailAi",
    detailNoAiKey: "wordConv.editableDetailNoAi",
    hintKey: "wordConv.editableHint",
  },
  {
    key: "layout",
    titleKey: "wordConv.layoutTitle",
    detailAiKey: "wordConv.layoutDetailAi",
    detailNoAiKey: "wordConv.layoutDetailNoAi",
    hintKey: "wordConv.layoutHint",
  },
];

function ModalShell({ title, children, onEscape }) {
  useEffect(() => {
    if (!onEscape) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onEscape(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onEscape]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm transition-opacity">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 transform transition-all text-center">
        <h3 className="text-lg font-bold text-gray-900 mb-2">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function ScanChooser({ filename, scan, onChoose, onCancel, aiAvailable = true }) {
  const { t } = useI18n();
  const [useAi, setUseAi] = useState(false);
  const tooMany = scan.max_pages && scan.pages > scan.max_pages;
  return (
    <ModalShell title={t("wordConv.scanTitle")} onEscape={onCancel}>
      <p className="text-sm text-gray-500 mb-4 truncate" title={filename}>{filename}</p>
      <div className="text-left space-y-3" data-testid="scan-convert">
        <div className="p-3 rounded-lg bg-teal-50 border border-teal-100 text-sm text-teal-900">
          {t("wordConv.scanDesc")}
        </div>
        {aiAvailable && (
        <label className="flex items-start gap-2 p-3 rounded-lg border border-gray-200 cursor-pointer">
          <input type="checkbox" className="mt-1" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} data-testid="scan-convert-ai" />
          <span className="text-sm text-gray-700">
            {t("wordConv.scanUseAi")}
            <span className="block text-xs text-gray-400">{t("wordConv.scanUseAiHint")}</span>
          </span>
        </label>
        )}
        <p className="text-xs text-gray-400">
          {t("wordConv.scanTimeHint", { pages: scan.pages })}
        </p>
        {tooMany && (
          <p className="text-sm text-red-600">{t("wordConv.scanTooMany", { max: scan.max_pages })}</p>
        )}
      </div>
      <div className="mt-5 flex justify-center gap-2">
        <button type="button" onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">
          {t("common.cancel")}
        </button>
        <button type="button" disabled={tooMany} onClick={() => onChoose("scan", { useAi: aiAvailable && useAi })}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
          {t("wordConv.convertBtn")}
        </button>
      </div>
    </ModalShell>
  );
}

export function ConversionModeChooser({ filename, onChoose, onCancel, inspecting = false, scan = null, aiAvailable = true }) {
  const { t } = useI18n();
  if (inspecting) {
    return (
      <ModalShell title={t("wordConv.modalTitle")} onEscape={onCancel}>
        <p className="text-sm text-gray-500 py-6">{t("wordConv.inspecting")}</p>
      </ModalShell>
    );
  }
  if (scan) return <ScanChooser filename={filename} scan={scan} onChoose={onChoose} onCancel={onCancel} aiAvailable={aiAvailable} />;
  return (
    <ModalShell title={t("wordConv.modalTitle")} onEscape={onCancel}>
      <p className="text-sm text-gray-500 mb-4 truncate" title={filename}>{filename}</p>
      <div className="space-y-3 text-left">
        {CONVERSION_MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => onChoose(m.key)}
            className="w-full p-4 rounded-xl border border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition-colors text-left"
          >
            <div className="font-semibold text-gray-900">{t(m.titleKey)}</div>
            <div className="text-sm text-gray-600 mt-1">
              {aiAvailable ? t(m.detailAiKey) : t(m.detailNoAiKey)}
            </div>
            <div className="text-xs text-gray-400 mt-1">{t(m.hintKey)}</div>
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={onCancel}
        className="mt-4 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
      >
        {t("common.cancel")}
      </button>
    </ModalShell>
  );
}

export default function ConversionModal({ task, mode, onClose, aiAvailable = true }) {
  const { t } = useI18n();
  let title;
  if (mode === "layout") {
    title = t("wordConv.titleLayout");
  } else if (mode === "scan") {
    title = t("wordConv.titleScan");
  } else if (aiAvailable) {
    title = t("wordConv.titleAi");
  } else {
    title = t("wordConv.modalTitle");
  }
  if (task.status === "failed") {
    return (
      <ModalShell title={title} onEscape={onClose}>
        <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-100">
          {t("wordConv.failed", { message: task.error_message || t("wordConv.unknownError") })}
        </div>
        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-lg hover:bg-red-700">
          {t("common.close")}
        </button>
      </ModalShell>
    );
  }
  if (task.status === "completed") {
    return (
      <ModalShell title={title} onEscape={onClose}>
        <div className="mb-4 p-3 bg-green-50 text-green-700 text-sm rounded-lg border border-green-100">
          {t("wordConv.completed")}
        </div>
        <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-lg hover:bg-blue-700">
          {t("common.close")}
        </button>
      </ModalShell>
    );
  }
  return (
    <ModalShell title={title}>
      <p className="text-sm text-gray-500 mb-4">
        {mode === "scan" ? t("wordConv.readingPages") : t("common.processing")} {t("wordConv.dontClose", { progress: task.progress })}
      </p>
      <div className="w-full bg-gray-100 rounded-full h-3 mb-4">
        <div className="bg-blue-600 h-3 rounded-full transition-all duration-500" style={{ width: `${task.progress}%` }}></div>
      </div>
    </ModalShell>
  );
}
