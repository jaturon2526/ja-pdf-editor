// กล่องโต้ตอบเล็กๆ ของหน้า Editor ที่เดิมเขียน inline อยู่ใน Editor.jsx (แยกออกมาให้ Editor.jsx สั้นลง)

export const PDF_VERSION_OPTIONS = [
  { value: "", label: "ไม่เปลี่ยน (ตามไฟล์ปัจจุบัน)" },
  { value: "1.4", label: "PDF 1.4 — โปรแกรมรุ่นเก่าเปิดได้" },
  { value: "1.5", label: "PDF 1.5 — เลเยอร์, JPEG 2000" },
  { value: "1.6", label: "PDF 1.6 — เข้ารหัส AES-128" },
  { value: "1.7", label: "PDF 1.7 — ISO 32000-1 ใช้ทั่วไป (แนะนำ เข้ารหัส AES-256 ได้)" },
  { value: "2.0", label: "PDF 2.0 — ISO 32000-2 ล่าสุด" },
];

// PDF/A (ISO 19005) — เก็บเอกสารระยะยาว
export const PDFA_OPTIONS = [
  { value: "pdfa-1b", label: "PDF/A-1b — เข้ากันได้กว้างสุด (PDF 1.4)" },
  { value: "pdfa-2b", label: "PDF/A-2b — แนะนำ (PDF 1.7)" },
  { value: "pdfa-3b", label: "PDF/A-3b — แบบ 2b ที่แนบไฟล์ได้" },
];

export function SaveCopyModal({ filename, onFilenameChange, pdfVersion = "", onPdfVersionChange, currentVersion, encrypted, onCancel, onConfirm }) {
  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">บันทึกเป็นไฟล์ใหม่</h2>
        <div style={{ marginTop: 16 }}>
          <label style={{ fontSize: 14, color: "#475569", marginBottom: 8, display: "block" }}>ตั้งชื่อไฟล์ใหม่:</label>
          <input 
            type="text" 
            value={filename} 
            onChange={(e) => onFilenameChange(e.target.value)} 
            style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1" }}
          />
          <p style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
            * ไฟล์เดิมในหน้าแรก (Dashboard) จะยังคงเป็นเวอร์ชันก่อนหน้านี้ไม่ถูกแก้ไข
          </p>
        </div>
        {onPdfVersionChange && (
          <div style={{ marginTop: 16 }}>
            <label htmlFor="save-copy-pdf-version" style={{ fontSize: 14, color: "#475569", marginBottom: 8, display: "block" }}>
              เวอร์ชัน PDF{currentVersion ? ` (ไฟล์ปัจจุบัน: ${currentVersion})` : ""}:
            </label>
            <select
              id="save-copy-pdf-version"
              value={pdfVersion}
              onChange={(e) => onPdfVersionChange(e.target.value)}
              style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff" }}
            >
              <optgroup label="เวอร์ชัน PDF">
                {PDF_VERSION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </optgroup>
              <optgroup label="PDF/A — เก็บเอกสารระยะยาว (ISO 19005)">
                {PDFA_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </optgroup>
            </select>
            {pdfVersion.startsWith("pdfa-") && (
              <p style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
                PDF/A สำหรับเก็บเอกสารระยะยาว — เปิดแล้วหน้าตาเหมือนเดิมทุกโปรแกรม: ฝังฟอนต์ทั้งหมด ใส่โปรไฟล์สี sRGB
                และไฮไลต์ กล่องข้อความ ช่องฟอร์มถูกรวมลงเนื้อหน้า (แก้ไขต่อไม่ได้) ข้อความยังค้นหาได้ ลิงก์และบุ๊กมาร์กยังใช้ได้
                {pdfVersion === "pdfa-1b" && " · PDF/A-1 ไม่รองรับความโปร่งใส รูปที่มีพื้นโปร่งใสจะถูกเติมพื้นขาว"}
                {encrypted && (
                  <strong style={{ display: "block", color: "#b91c1c", marginTop: 4 }}>
                    PDF/A ห้ามตั้งรหัสผ่าน — เอกสารนี้มีรหัสผ่านอยู่ ลบรหัสผ่านก่อนจึงจะบันทึกเป็น PDF/A ได้
                  </strong>
                )}
              </p>
            )}
            {pdfVersion && !pdfVersion.startsWith("pdfa-") && (
              <p style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
                ไฟล์ใหม่จะตรงมาตรฐาน PDF {pdfVersion} — ส่วนที่เวอร์ชันนี้ไม่รองรับจะถูกแปลง (เช่น เลเยอร์ถูกรวม รูป JPEG 2000
                ถูกแปลงโดยไม่ลดความคมชัด) ข้อความ ลิงก์ บุ๊กมาร์ก ไฮไลต์ และช่องฟอร์มยังอยู่ครบ
                {encrypted && (pdfVersion === "1.4" || pdfVersion === "1.5" || pdfVersion === "1.6") && (
                  <strong style={{ display: "block", color: "#b45309", marginTop: 4 }}>
                    {pdfVersion === "1.6" ? "PDF 1.6 เข้ารหัสได้แบบ AES-128" : `PDF ${pdfVersion} เข้ารหัสได้แค่แบบ RC4 128 บิต ซึ่งปลอดภัยน้อยกว่า AES`}
                    {" "}และใช้รหัสผ่านภาษาไทยไม่ได้ — ถ้าไม่จำเป็นแนะนำ PDF 1.7
                  </strong>
                )}
              </p>
            )}
          </div>
        )}
        <div className="modal-actions" style={{ marginTop: 24 }}>
          <button className="secondary-btn" onClick={onCancel}>ยกเลิก</button>
          <button className="primary-btn" onClick={onConfirm} disabled={!filename || (encrypted && pdfVersion.startsWith("pdfa-"))}>บันทึก</button>
        </div>
      </div>
    </div>
  );
}

export function CompressModal({ profile, onProfileChange, onCancel, onConfirm }) {
  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">ลดขนาดไฟล์ (Compress PDF)</h2>
        <p className="modal-subtitle">เลือกระดับการบีบอัดที่ต้องการ</p>
        <div style={{ margin: "20px 0", display: "flex", flexDirection: "column", gap: "10px" }}>
          <label>
            <input type="radio" name="profile" value="screen" checked={profile === "screen"} onChange={() => onProfileChange("screen")} />
            {" "}เล็กสุด (Screen - สำหรับดูบนจอ)
          </label>
          <label>
            <input type="radio" name="profile" value="ebook" checked={profile === "ebook"} onChange={() => onProfileChange("ebook")} />
            {" "}ปานกลาง (eBook - ภาพชัดปานกลาง)
          </label>
          <label>
            <input type="radio" name="profile" value="printer" checked={profile === "printer"} onChange={() => onProfileChange("printer")} />
            {" "}ใหญ่ (Printer - สำหรับพิมพ์)
          </label>
        </div>
        <p className="modal-subtitle" style={{ fontSize: "0.85rem" }}>
          ไฮไลต์ กล่องข้อความ และช่องฟอร์มยังอยู่และแก้ไขได้ตามเดิม · ถ้าบีบแล้วเล็กลงไม่ถึง 3% ระบบจะไม่เปลี่ยนไฟล์
        </p>
        <div className="modal-actions">
          <button className="secondary-btn" onClick={onCancel}>ยกเลิก</button>
          <button className="primary-btn" onClick={onConfirm}>ตกลง</button>
        </div>
      </div>
    </div>
  );
}

export function FlattenModal({ onCancel, onConfirm }) {
  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title" style={{ color: "var(--color-danger, #ef4444)" }}>รวมเลเยอร์ (Flatten PDF)</h2>
        <p className="modal-subtitle" style={{ marginTop: "10px", lineHeight: "1.5" }}>
          การทำ Flatten จะผสาน <strong>ลายเซ็น, กล่องข้อความ, ลายน้ำ, รูปภาพที่วางทับ, และฟอร์มที่กรอกไว้</strong> ให้กลายเป็นเนื้อเดียวกับหน้ากระดาษ (เหมือนสั่งพิมพ์ออกมาเป็นแผ่นใหม่)<br/><br/>
          <strong>คำเตือน:</strong> คุณจะไม่สามารถใช้เครื่องมือยางลบ หรือคลิกแก้ไขสิ่งที่วางทับไปแล้วได้อีก (แต่ตัวหนังสือดั้งเดิมจะยัง Select ได้ปกติ)<br/><br/>
          คุณแน่ใจหรือไม่ว่าต้องการรวมเลเยอร์?
        </p>
        <div className="modal-actions" style={{ marginTop: "24px" }}>
          <button className="secondary-btn" onClick={onCancel}>ยกเลิก</button>
          <button className="primary-btn" style={{ backgroundColor: "var(--color-danger, #ef4444)" }} onClick={onConfirm}>ตกลง</button>
        </div>
      </div>
    </div>
  );
}

// เลือกรูปแบบการพิมพ์ เมื่อเอกสารมีหน้าแนวนอน (เช่น หน้าที่หมุน 90°)
export function PrintOptionsModal({ onChoose, onCancel }) {
  const options = [
    {
      key: "as_shown",
      title: "พิมพ์ตามที่เห็นบนจอ (แนะนำ)",
      detail: "วางทุกหน้าบนกระดาษแนวตั้งในทิศเดียวกับที่เห็นบนจอ หน้าแนวนอนจะถูกย่อให้พอดี ไม่มีหน้ากลับหัว",
    },
    {
      key: "auto",
      title: "เต็มกระดาษ (ให้เครื่องพิมพ์หมุนหน้าเอง)",
      detail: "หน้าแนวนอนถูกหมุนให้เต็มแผ่น — ทิศที่ได้ขึ้นกับเครื่องพิมพ์ หน้าที่หมุนซ้ายอาจดูกลับหัวในตัวอย่างก่อนพิมพ์",
    },
  ];
  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">พิมพ์เอกสาร</h2>
        <p className="modal-subtitle">เอกสารนี้มีหน้าแนวนอน เลือกรูปแบบการพิมพ์</p>
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
          <button className="secondary-btn" onClick={onCancel}>ยกเลิก</button>
        </div>
      </div>
    </div>
  );
}
