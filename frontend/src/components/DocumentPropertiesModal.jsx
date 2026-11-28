import React from "react";
import { useI18n } from "../i18n/I18nContext.jsx";

// ค่าที่ backend คืนมาเป็น null/undefined หมายถึง "ไม่มีข้อมูลนี้ในไฟล์ PDF" (หลายฟิลด์ไม่บังคับ เช่น
// title/author, หรือตรวจไม่ได้ในบางไฟล์ เช่น tagged_pdf/fast_web_view) แสดงเป็น "-" แทนที่จะปล่อยว่าง
// ให้ดูเหมือนโหลดไม่สำเร็จ
function displayText(value) {
  if (value === null || value === undefined || value === "") return "-";
  return value;
}

function displayBool(value, t) {
  if (value === null || value === undefined) return t("editor.modals.docProps.unknown");
  return value ? t("editor.modals.docProps.yes") : t("editor.modals.docProps.no");
}

// วันที่ของ cert มาจาก backend เป็น ISO-8601 (มี timezone) — แสดงเป็น dd/mm/yyyy HH:MM ตามเวลาเครื่องผู้ใช้
// รูปแบบเดียวกับวันที่อื่นในกล่องนี้ (ดู backend _parse_pdf_date)
function formatCertDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const CERT_EXPIRY_WARN_DAYS = 30;

// สถานะวันหมดอายุของ cert ณ ปัจจุบัน (null = backend อ่านวันหมดอายุไม่ได้ ไม่แสดงแถวนี้)
function certExpiry(sig, t) {
  if (sig.cert_expired === null || sig.cert_expired === undefined) return null;
  if (sig.cert_expired) return { level: "bad", text: t("editor.modals.docProps.certExpired") };
  if (sig.cert_days_remaining <= CERT_EXPIRY_WARN_DAYS) {
    return { level: "warn", text: t("editor.modals.docProps.certExpiringSoon", { days: sig.cert_days_remaining }) };
  }
  return { level: "ok", text: t("editor.modals.docProps.certValidDays", { days: sig.cert_days_remaining }) };
}

// ความน่าเชื่อถือ: cert ที่ออกเอง (self-signed) เช่นจากไฟล์ .p12 ที่สร้างเอง ลายเซ็นยังถูกต้องทางเทคนิค
// แต่ไม่ได้ออกโดย CA ที่ระบบเชื่อถือ — แยกอธิบายให้ผู้ใช้ไม่เข้าใจผิดว่า "ผิดพลาด"
function certTrust(sig, t) {
  if (sig.is_trusted === null || sig.is_trusted === undefined) return null;
  if (sig.is_trusted) return { level: "ok", text: t("editor.modals.docProps.certTrusted") };
  if (sig.cert_self_signed) {
    return { level: "warn", text: t("editor.modals.docProps.certSelfSigned") };
  }
  return { level: "warn", text: t("editor.modals.docProps.certUntrusted") };
}

function PropRow({ label, value }) {
  return (
    <div className="docprops-row">
      <span className="docprops-row-label">{label}</span>
      <span className="docprops-row-value">{value}</span>
    </div>
  );
}

/**
 * DocumentPropertiesModal — กล่อง "คุณสมบัติเอกสาร" แบบเดียวกับ Document Properties ของ Acrobat Reader
 * (ผู้ใช้แจ้งขอ — เปิดได้ทั้งจากเมนู File > คุณสมบัติเอกสาร... และปุ่มบน toolbar ดู App.jsx
 * handleOpenDocProps) แยกจาก PropertiesPanel.jsx โดยเจตนา — ตัวนั้นเป็นแผงปรับฟอนต์/สี/ขนาดตอนแก้ไข
 * ข้อความ คนละเรื่องกันโดยสิ้นเชิง
 *
 * รับข้อมูลจาก backend GET /pdf/{session_id}/properties (รูปแบบ DocumentPropertiesResponse) — บางฟิลด์
 * เป็น None ได้ตามข้อจำกัดของแต่ละไฟล์ (ผู้ใช้บอกให้ทำเท่าที่ทำได้) จึงแสดง "-"/"ไม่ทราบ" แทนการ error
 */
export default function DocumentPropertiesModal({ fileName, properties, loading, errorMessage, onClose, onShowFontDetails }) {
  const { t } = useI18n();

  return (
    <div role="presentation" className="modal-overlay" onClick={onClose}>
      <div role="presentation" className="modal-card docprops-modal-card" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">{t("editor.modals.docProps.title")}</h2>
        <p className="modal-subtitle">{fileName || ""}</p>

        {loading && <p className="docprops-loading">{t("editor.modals.docProps.loading")}</p>}
        {!loading && errorMessage && (
          <p className="modal-error">{t("editor.modals.docProps.loadError", { error: errorMessage })}</p>
        )}

        {!loading && !errorMessage && properties && (
          <div className="docprops-body">
            <div className="docprops-section">
              <h3 className="docprops-section-title">{t("editor.modals.docProps.sectionDescription")}</h3>
              <PropRow label={t("editor.modals.docProps.fieldTitle")} value={displayText(properties.title)} />
              <PropRow label={t("editor.modals.docProps.fieldAuthor")} value={displayText(properties.author)} />
              <PropRow label={t("editor.modals.docProps.fieldSubject")} value={displayText(properties.subject)} />
              <PropRow label={t("editor.modals.docProps.fieldKeywords")} value={displayText(properties.keywords)} />
              <PropRow label={t("editor.modals.docProps.fieldApplication")} value={displayText(properties.creator)} />
              <PropRow label={t("editor.modals.docProps.fieldProducer")} value={displayText(properties.producer)} />
              <PropRow label={t("editor.modals.docProps.fieldCreated")} value={displayText(properties.creation_date)} />
              <PropRow label={t("editor.modals.docProps.fieldModified")} value={displayText(properties.mod_date)} />
            </div>

            {properties.fonts && properties.fonts.length > 0 && (
              <div className="docprops-section">
                <h3 className="docprops-section-title">{t("editor.modals.docProps.sectionFonts")}</h3>
                <PropRow label={t("editor.modals.docProps.fieldFontList")} value={properties.fonts.join(", ")} />
                {onShowFontDetails && (
                  <button type="button" className="text-sm text-blue-700 hover:underline mt-1" onClick={onShowFontDetails}>
                    {t("editor.modals.docProps.showFontDetails")}
                  </button>
                )}
              </div>
            )}

            <div className="docprops-section">
              <h3 className="docprops-section-title">{t("editor.modals.docProps.sectionAdvanced")}</h3>
              <PropRow label={t("editor.modals.docProps.fieldPdfVersion")} value={displayText(properties.pdf_version)} />
              <PropRow label={t("editor.modals.docProps.fieldFileSize")} value={displayText(properties.file_size_display)} />
              <PropRow label={t("editor.modals.docProps.fieldPageCount")} value={displayText(properties.page_count)} />
              <PropRow
                label={t("editor.modals.docProps.fieldPageSize")}
                value={
                  properties.page_size_display
                    ? `${properties.page_size_display} (${properties.page_width_pt.toFixed(0)} × ${properties.page_height_pt.toFixed(0)} pt)`
                    : `${properties.page_width_pt.toFixed(0)} × ${properties.page_height_pt.toFixed(0)} pt`
                }
              />
              <PropRow label={t("editor.modals.docProps.fieldTaggedPdf")} value={displayBool(properties.tagged_pdf, t)} />
              <PropRow label={t("editor.modals.docProps.fieldFastWebView")} value={displayBool(properties.fast_web_view, t)} />
              <PropRow label={t("editor.modals.docProps.fieldEncrypted")} value={displayBool(properties.is_encrypted, t)} />
            </div>

            {properties.signatures && properties.signatures.length > 0 && (
              <div className="docprops-section">
                <h3 className="docprops-section-title">{t("editor.modals.docProps.sectionSignatures")}</h3>
                {properties.signatures.map((sig, i) => {
                  const expiry = certExpiry(sig, t);
                  const trust = certTrust(sig, t);
                  return (
                    <div key={i} className="docprops-sig-box">
                      <PropRow label={t("editor.modals.docProps.fieldSigName")} value={displayText(sig.name)} />
                      <PropRow label={t("editor.modals.docProps.fieldSigDate")} value={displayText(sig.date)} />
                      <PropRow label={t("editor.modals.docProps.fieldSigLocation")} value={displayText(sig.location)} />
                      <PropRow label={t("editor.modals.docProps.fieldSigReason")} value={displayText(sig.reason)} />
                      <PropRow label={t("editor.modals.docProps.fieldSigContact")} value={displayText(sig.contact_info)} />
                      <PropRow
                        label={t("editor.modals.docProps.fieldSigStatus")}
                        value={sig.is_valid ? t("editor.modals.docProps.sigValid") : t("editor.modals.docProps.sigInvalid")}
                      />

                      {(sig.cert_subject || sig.cert_serial) && (
                        <div className="docprops-cert-box">
                          <h4 className="docprops-cert-title">{t("editor.modals.docProps.certDetailsTitle")}</h4>
                          <PropRow label={t("editor.modals.docProps.fieldCertSubject")} value={displayText(sig.cert_subject_cn || sig.cert_subject)} />
                          <PropRow label={t("editor.modals.docProps.fieldCertOrg")} value={displayText(sig.cert_subject_org)} />
                          <PropRow label={t("editor.modals.docProps.fieldCertEmail")} value={displayText(sig.cert_subject_email)} />
                          <PropRow label={t("editor.modals.docProps.fieldCertIssuer")} value={displayText(sig.cert_issuer_cn || sig.cert_issuer)} />
                          <PropRow label={t("editor.modals.docProps.fieldCertValidFrom")} value={formatCertDate(sig.cert_valid_from)} />
                          <PropRow label={t("editor.modals.docProps.fieldCertValidTo")} value={formatCertDate(sig.cert_valid_to)} />
                          {expiry && (
                            <PropRow
                              label={t("editor.modals.docProps.fieldCertStatus")}
                              value={<span className={`docprops-badge ${expiry.level}`}>{expiry.text}</span>}
                            />
                          )}
                          {trust && (
                            <PropRow
                              label={t("editor.modals.docProps.fieldCertTrust")}
                              value={<span className={`docprops-badge ${trust.level}`}>{trust.text}</span>}
                            />
                          )}

                          <details className="docprops-cert-advanced">
                            <summary>{t("editor.modals.docProps.certAdvancedSummary")}</summary>
                            <PropRow label={t("editor.modals.docProps.fieldCertSerial")} value={<span className="docprops-mono">{displayText(sig.cert_serial)}</span>} />
                            <PropRow label={t("editor.modals.docProps.fieldCertSigAlg")} value={displayText(sig.cert_signature_algorithm)} />
                            <PropRow label={t("editor.modals.docProps.fieldCertPubKey")} value={displayText(sig.cert_key_info)} />
                            <PropRow label={t("editor.modals.docProps.fieldCertSubjectFull")} value={displayText(sig.cert_subject)} />
                            <PropRow label={t("editor.modals.docProps.fieldCertIssuerFull")} value={displayText(sig.cert_issuer)} />
                            <PropRow label={t("editor.modals.docProps.fieldCertSha256")} value={<span className="docprops-mono">{displayText(sig.cert_sha256)}</span>} />
                            <PropRow label={t("editor.modals.docProps.fieldCertSha1")} value={<span className="docprops-mono">{displayText(sig.cert_sha1)}</span>} />
                          </details>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="primary-btn" onClick={onClose}>
            {t("editor.modals.docProps.close")}
          </button>
        </div>
      </div>
    </div>
  );
}
