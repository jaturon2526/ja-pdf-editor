import React from "react";

// ค่าที่ backend คืนมาเป็น null/undefined หมายถึง "ไม่มีข้อมูลนี้ในไฟล์ PDF" (หลายฟิลด์ไม่บังคับ เช่น
// title/author, หรือตรวจไม่ได้ในบางไฟล์ เช่น tagged_pdf/fast_web_view) แสดงเป็น "-" แทนที่จะปล่อยว่าง
// ให้ดูเหมือนโหลดไม่สำเร็จ
function displayText(value) {
  if (value === null || value === undefined || value === "") return "-";
  return value;
}

function displayBool(value) {
  if (value === null || value === undefined) return "ไม่ทราบ";
  return value ? "ใช่" : "ไม่ใช่";
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
function certExpiry(sig) {
  if (sig.cert_expired === null || sig.cert_expired === undefined) return null;
  if (sig.cert_expired) return { level: "bad", text: "❌ หมดอายุแล้ว" };
  if (sig.cert_days_remaining <= CERT_EXPIRY_WARN_DAYS) {
    return { level: "warn", text: `⚠️ ใกล้หมดอายุ (เหลือ ${sig.cert_days_remaining} วัน)` };
  }
  return { level: "ok", text: `✅ ยังไม่หมดอายุ (เหลือ ${sig.cert_days_remaining} วัน)` };
}

// ความน่าเชื่อถือ: cert ที่ออกเอง (self-signed) เช่นจากไฟล์ .p12 ที่สร้างเอง ลายเซ็นยังถูกต้องทางเทคนิค
// แต่ไม่ได้ออกโดย CA ที่ระบบเชื่อถือ — แยกอธิบายให้ผู้ใช้ไม่เข้าใจผิดว่า "ผิดพลาด"
function certTrust(sig) {
  if (sig.is_trusted === null || sig.is_trusted === undefined) return null;
  if (sig.is_trusted) return { level: "ok", text: "✅ ออกโดย CA ที่เชื่อถือได้" };
  if (sig.cert_self_signed) {
    return { level: "warn", text: "⚠️ ใบรับรองลงนามด้วยตนเอง (Self-signed) ไม่ได้ออกโดย CA" };
  }
  return { level: "warn", text: "⚠️ ไม่พบ CA ที่เชื่อถือได้ในระบบ" };
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
export default function DocumentPropertiesModal({ fileName, properties, loading, errorMessage, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card docprops-modal-card" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">คุณสมบัติเอกสาร</h2>
        <p className="modal-subtitle">{fileName || ""}</p>

        {loading && <p className="docprops-loading">กำลังโหลดคุณสมบัติเอกสาร…</p>}
        {!loading && errorMessage && (
          <p className="modal-error">โหลดคุณสมบัติเอกสารไม่สำเร็จ: {errorMessage}</p>
        )}

        {!loading && !errorMessage && properties && (
          <div className="docprops-body">
            <div className="docprops-section">
              <h3 className="docprops-section-title">คำอธิบาย (Description)</h3>
              <PropRow label="ชื่อเรื่อง (Title)" value={displayText(properties.title)} />
              <PropRow label="ผู้แต่ง (Author)" value={displayText(properties.author)} />
              <PropRow label="หัวเรื่อง (Subject)" value={displayText(properties.subject)} />
              <PropRow label="คำสำคัญ (Keywords)" value={displayText(properties.keywords)} />
              <PropRow label="แอปพลิเคชันที่สร้าง (Application)" value={displayText(properties.creator)} />
              <PropRow label="PDF Producer" value={displayText(properties.producer)} />
              <PropRow label="วันที่สร้าง (Created)" value={displayText(properties.creation_date)} />
              <PropRow label="แก้ไขล่าสุด (Modified)" value={displayText(properties.mod_date)} />
            </div>

            {properties.fonts && properties.fonts.length > 0 && (
              <div className="docprops-section">
                <h3 className="docprops-section-title">ฟอนต์ที่ใช้ในเอกสาร (Fonts)</h3>
                <PropRow label="รายชื่อฟอนต์" value={properties.fonts.join(", ")} />
              </div>
            )}

            <div className="docprops-section">
              <h3 className="docprops-section-title">ขั้นสูง (Advanced)</h3>
              <PropRow label="PDF Version" value={displayText(properties.pdf_version)} />
              <PropRow label="ขนาดไฟล์ (File Size)" value={displayText(properties.file_size_display)} />
              <PropRow label="จำนวนหน้า (Page Count)" value={displayText(properties.page_count)} />
              <PropRow
                label="ขนาดหน้า (Page Size)"
                value={
                  properties.page_size_display
                    ? `${properties.page_size_display} (${properties.page_width_pt.toFixed(0)} × ${properties.page_height_pt.toFixed(0)} pt)`
                    : `${properties.page_width_pt.toFixed(0)} × ${properties.page_height_pt.toFixed(0)} pt`
                }
              />
              <PropRow label="Tagged PDF" value={displayBool(properties.tagged_pdf)} />
              <PropRow label="Fast Web View" value={displayBool(properties.fast_web_view)} />
              <PropRow label="มีรหัสผ่านป้องกัน (Encrypted)" value={displayBool(properties.is_encrypted)} />
            </div>

            {properties.signatures && properties.signatures.length > 0 && (
              <div className="docprops-section">
                <h3 className="docprops-section-title">ลายเซ็นดิจิทัล (Digital Signatures)</h3>
                {properties.signatures.map((sig, i) => {
                  const expiry = certExpiry(sig);
                  const trust = certTrust(sig);
                  return (
                    <div key={i} className="docprops-sig-box">
                      <PropRow label="ชื่อผู้เซ็น (Name)" value={displayText(sig.name)} />
                      <PropRow label="วันที่เซ็น (Signed)" value={displayText(sig.date)} />
                      <PropRow label="สถานที่ (Location)" value={displayText(sig.location)} />
                      <PropRow label="เหตุผล (Reason)" value={displayText(sig.reason)} />
                      <PropRow label="ติดต่อ (Contact)" value={displayText(sig.contact_info)} />
                      <PropRow label="สถานะ (Status)" value={sig.is_valid ? "✅ ตรวจสอบแล้ว (Valid)" : "❌ ไม่สามารถตรวจสอบได้"} />

                      {(sig.cert_subject || sig.cert_serial) && (
                        <div className="docprops-cert-box">
                          <h4 className="docprops-cert-title">ใบรับรองอิเล็กทรอนิกส์ (Certificate Details)</h4>
                          <PropRow label="ออกให้แก่ (Subject)" value={displayText(sig.cert_subject_cn || sig.cert_subject)} />
                          <PropRow label="องค์กร (Organization)" value={displayText(sig.cert_subject_org)} />
                          <PropRow label="อีเมล (Email)" value={displayText(sig.cert_subject_email)} />
                          <PropRow label="ผู้ออกใบรับรอง (Issuer)" value={displayText(sig.cert_issuer_cn || sig.cert_issuer)} />
                          <PropRow label="วันที่สร้าง/เริ่มใช้ (Valid From)" value={formatCertDate(sig.cert_valid_from)} />
                          <PropRow label="วันหมดอายุ (Valid To)" value={formatCertDate(sig.cert_valid_to)} />
                          {expiry && (
                            <PropRow
                              label="สถานะใบรับรอง (Cert Status)"
                              value={<span className={`docprops-badge ${expiry.level}`}>{expiry.text}</span>}
                            />
                          )}
                          {trust && (
                            <PropRow
                              label="ความน่าเชื่อถือ (Trust)"
                              value={<span className={`docprops-badge ${trust.level}`}>{trust.text}</span>}
                            />
                          )}

                          <details className="docprops-cert-advanced">
                            <summary>รายละเอียดเพิ่มเติม (Advanced)</summary>
                            <PropRow label="Serial Number" value={<span className="docprops-mono">{displayText(sig.cert_serial)}</span>} />
                            <PropRow label="Signature Algorithm" value={displayText(sig.cert_signature_algorithm)} />
                            <PropRow label="Public Key" value={displayText(sig.cert_key_info)} />
                            <PropRow label="Subject (เต็ม)" value={displayText(sig.cert_subject)} />
                            <PropRow label="Issuer (เต็ม)" value={displayText(sig.cert_issuer)} />
                            <PropRow label="SHA-256 Fingerprint" value={<span className="docprops-mono">{displayText(sig.cert_sha256)}</span>} />
                            <PropRow label="SHA-1 Fingerprint" value={<span className="docprops-mono">{displayText(sig.cert_sha1)}</span>} />
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
          <button className="primary-btn" onClick={onClose}>
            ปิด
          </button>
        </div>
      </div>
    </div>
  );
}
