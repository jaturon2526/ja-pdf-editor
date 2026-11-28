// กล่องโต้ตอบเล็กๆ ของหน้า Editor ที่เดิมเขียน inline อยู่ใน Editor.jsx (แยกออกมาให้ Editor.jsx สั้นลง)
import { useI18n } from "../i18n/I18nContext.jsx";

export const PDF_VERSION_OPTIONS = [
  { value: "", labelKey: "editor.modals.dialogs.pdfVersionUnchanged" },
  { value: "1.4", labelKey: "editor.modals.dialogs.pdfVersion14" },
  { value: "1.5", labelKey: "editor.modals.dialogs.pdfVersion15" },
  { value: "1.6", labelKey: "editor.modals.dialogs.pdfVersion16" },
  { value: "1.7", labelKey: "editor.modals.dialogs.pdfVersion17" },
  { value: "2.0", labelKey: "editor.modals.dialogs.pdfVersion20" },
];

// PDF/A (ISO 19005) — เก็บเอกสารระยะยาว
export const PDFA_OPTIONS = [
  { value: "pdfa-1b", labelKey: "editor.modals.dialogs.pdfa1b" },
  { value: "pdfa-2b", labelKey: "editor.modals.dialogs.pdfa2b" },
  { value: "pdfa-3b", labelKey: "editor.modals.dialogs.pdfa3b" },
];

export function SaveCopyModal({ filename, onFilenameChange, pdfVersion = "", onPdfVersionChange, currentVersion, encrypted, onCancel, onConfirm }) {
  const { t } = useI18n();
  const versionLabel = currentVersion
    ? t("editor.modals.dialogs.saveCopyPdfVersionCurrent", { version: currentVersion })
    : t("editor.modals.dialogs.saveCopyPdfVersionLabel");
  const encryptedWarning =
    pdfVersion === "1.6"
      ? t("editor.modals.dialogs.pdfVersionEncrypted16Warning")
      : t("editor.modals.dialogs.pdfVersionEncryptedLegacyWarning", { version: pdfVersion });

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">{t("editor.modals.dialogs.saveCopyTitle")}</h2>
        <div style={{ marginTop: 16 }}>
          <label htmlFor="editordialogs-f25" style={{ fontSize: 14, color: "#475569", marginBottom: 8, display: "block" }}>
            {t("editor.modals.dialogs.saveCopyFilenameLabel")}
          </label>
          <input
            id="editordialogs-f25"
            type="text"
            value={filename}
            onChange={(e) => onFilenameChange(e.target.value)}
            style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1" }}
          />
          <p style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
            {t("editor.modals.dialogs.saveCopyNote")}
          </p>
        </div>
        {onPdfVersionChange && (
          <div style={{ marginTop: 16 }}>
            <label htmlFor="save-copy-pdf-version" style={{ fontSize: 14, color: "#475569", marginBottom: 8, display: "block" }}>
              {versionLabel}
            </label>
            <select
              id="save-copy-pdf-version"
              value={pdfVersion}
              onChange={(e) => onPdfVersionChange(e.target.value)}
              style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff" }}
            >
              <optgroup label={t("editor.modals.dialogs.optgroupPdfVersion")}>
                {PDF_VERSION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{t(o.labelKey)}</option>)}
              </optgroup>
              <optgroup label={t("editor.modals.dialogs.optgroupPdfa")}>
                {PDFA_OPTIONS.map((o) => <option key={o.value} value={o.value}>{t(o.labelKey)}</option>)}
              </optgroup>
            </select>
            {pdfVersion.startsWith("pdfa-") && (
              <p style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
                {t("editor.modals.dialogs.pdfaHint")}
                {pdfVersion === "pdfa-1b" && t("editor.modals.dialogs.pdfa1bTransparencyNote")}
                {encrypted && (
                  <strong style={{ display: "block", color: "#b91c1c", marginTop: 4 }}>
                    {t("editor.modals.dialogs.pdfaEncryptedWarning")}
                  </strong>
                )}
              </p>
            )}
            {pdfVersion && !pdfVersion.startsWith("pdfa-") && (
              <p style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
                {t("editor.modals.dialogs.pdfVersionHint", { version: pdfVersion })}
                {encrypted && (pdfVersion === "1.4" || pdfVersion === "1.5" || pdfVersion === "1.6") && (
                  <strong style={{ display: "block", color: "#b45309", marginTop: 4 }}>
                    {encryptedWarning}
                  </strong>
                )}
              </p>
            )}
          </div>
        )}
        <div className="modal-actions" style={{ marginTop: 24 }}>
          <button type="button" className="secondary-btn" onClick={onCancel}>{t("editor.modals.dialogs.cancel")}</button>
          <button type="button" className="primary-btn" onClick={onConfirm} disabled={!filename || (encrypted && pdfVersion.startsWith("pdfa-"))}>
            {t("editor.modals.dialogs.save")}
          </button>
        </div>
      </div>
    </div>
  );
}

export function CompressModal({ profile, onProfileChange, onCancel, onConfirm }) {
  const { t } = useI18n();
  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">{t("editor.modals.dialogs.compressTitle")}</h2>
        <p className="modal-subtitle">{t("editor.modals.dialogs.compressSubtitle")}</p>
        <div style={{ margin: "20px 0", display: "flex", flexDirection: "column", gap: "10px" }}>
          <label>
            <input type="radio" name="profile" value="screen" checked={profile === "screen"} onChange={() => onProfileChange("screen")} />
            {" "}{t("editor.modals.dialogs.compressScreen")}
          </label>
          <label>
            <input type="radio" name="profile" value="ebook" checked={profile === "ebook"} onChange={() => onProfileChange("ebook")} />
            {" "}{t("editor.modals.dialogs.compressEbook")}
          </label>
          <label>
            <input type="radio" name="profile" value="printer" checked={profile === "printer"} onChange={() => onProfileChange("printer")} />
            {" "}{t("editor.modals.dialogs.compressPrinter")}
          </label>
        </div>
        <p className="modal-subtitle" style={{ fontSize: "0.85rem" }}>
          {t("editor.modals.dialogs.compressNote")}
        </p>
        <div className="modal-actions">
          <button type="button" className="secondary-btn" onClick={onCancel}>{t("editor.modals.dialogs.cancel")}</button>
          <button type="button" className="primary-btn" onClick={onConfirm}>{t("editor.modals.dialogs.confirm")}</button>
        </div>
      </div>
    </div>
  );
}

export function FlattenModal({ onCancel, onConfirm }) {
  const { t } = useI18n();
  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title" style={{ color: "var(--color-danger, #ef4444)" }}>{t("editor.modals.dialogs.flattenTitle")}</h2>
        <p className="modal-subtitle" style={{ marginTop: "10px", lineHeight: "1.5" }}>
          {t("editor.modals.dialogs.flattenBodyPrefix")}
          <strong>{t("editor.modals.dialogs.flattenBodyItems")}</strong>
          {t("editor.modals.dialogs.flattenBodySuffix")}
          <br /><br />
          <strong>{t("editor.modals.dialogs.flattenWarningLabel")}</strong>
          {t("editor.modals.dialogs.flattenWarningBody")}
          <br /><br />
          {t("editor.modals.dialogs.flattenConfirmQuestion")}
        </p>
        <div className="modal-actions" style={{ marginTop: "24px" }}>
          <button type="button" className="secondary-btn" onClick={onCancel}>{t("editor.modals.dialogs.cancel")}</button>
          <button type="button" className="primary-btn" style={{ backgroundColor: "var(--color-danger, #ef4444)" }} onClick={onConfirm}>
            {t("editor.modals.dialogs.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}

// เลือกรูปแบบการพิมพ์ เมื่อเอกสารมีหน้าแนวนอน (เช่น หน้าที่หมุน 90°)
export function PrintOptionsModal({ onChoose, onCancel }) {
  const { t } = useI18n();
  const options = [
    {
      key: "as_shown",
      title: t("editor.modals.dialogs.printAsShownTitle"),
      detail: t("editor.modals.dialogs.printAsShownDetail"),
    },
    {
      key: "auto",
      title: t("editor.modals.dialogs.printAutoTitle"),
      detail: t("editor.modals.dialogs.printAutoDetail"),
    },
  ];
  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">{t("editor.modals.dialogs.printTitle")}</h2>
        <p className="modal-subtitle">{t("editor.modals.dialogs.printSubtitle")}</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10, margin: "16px 0" }}>
          {options.map((o) => (
            <button
              key={o.key}
              type="button"
              className="secondary-btn"
              style={{ textAlign: "left", padding: "12px 14px", height: "auto", whiteSpace: "normal" }}
              onClick={() => onChoose(o.key)}
            >
              <div style={{ fontWeight: 600 }}>{o.title}</div>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{o.detail}</div>
            </button>
          ))}
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary-btn" onClick={onCancel}>{t("editor.modals.dialogs.cancel")}</button>
        </div>
      </div>
    </div>
  );
}
