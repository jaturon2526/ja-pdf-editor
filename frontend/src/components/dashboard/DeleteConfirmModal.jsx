// ยืนยันการลบเอกสาร (แยกมาจาก Dashboard.jsx) — รองรับทั้ง 1 ไฟล์และหลายไฟล์
import { useEffect } from "react";
import { useI18n } from "../../i18n/I18nContext.jsx";

const MAX_LISTED = 5;

export default function DeleteConfirmModal({ files, error, deleting, onCancel, onConfirm }) {
  const { t } = useI18n();
  const many = files.length > 1;
  const listed = files.slice(0, MAX_LISTED);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && !deleting) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [deleting, onCancel]);

  let confirmLabel;
  if (deleting) {
    confirmLabel = t("deleteAccount.deleting");
  } else if (many) {
    confirmLabel = t("deleteModal.confirmMany", { count: files.length });
  } else {
    confirmLabel = t("deleteModal.confirmOne");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm transition-opacity">
      <div role="dialog" aria-modal="true" aria-labelledby="delete-confirm-title" className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6 transform transition-all">
        <h3 id="delete-confirm-title" className="text-lg font-bold text-gray-900 mb-2">
          {many ? t("deleteModal.titleMany", { count: files.length }) : t("deleteModal.titleOne")}
        </h3>
        {many ? (
          <div className="text-sm text-gray-500 mb-4">
            <p>{t("deleteModal.promptMany")}</p>
            <ul className="my-2 max-h-40 overflow-y-auto rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 space-y-1">
              {listed.map(f => (
                <li key={f.id} className="truncate font-semibold text-gray-800" title={f.filename}>• {f.filename}</li>
              ))}
              {files.length > MAX_LISTED && (
                <li className="text-gray-500">{t("deleteModal.moreFiles", { count: files.length - MAX_LISTED })}</li>
              )}
            </ul>
            <p>{t("deleteModal.irreversible")}</p>
          </div>
        ) : (
          <p className="text-sm text-gray-500 mb-4">
            {t("deleteModal.promptOneBefore")} <span className="font-semibold text-gray-800 break-all">{files[0]?.filename}</span> ?<br/>
            {t("deleteModal.irreversible")}
          </p>
        )}
        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg border border-red-100 whitespace-pre-line break-words">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-3 mt-6">
          <button
            type="button"
            onClick={onCancel}
            disabled={deleting}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={() => void onConfirm()}
            disabled={deleting}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
