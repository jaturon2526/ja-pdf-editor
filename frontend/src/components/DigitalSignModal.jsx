// ลายเซ็นดิจิทัล: ใบรับรอง .p12/.pfx + รายละเอียด + รูปลายเซ็น (ไม่บังคับ — เซ็นสด / พิมพ์ / รูปภาพ เหมือนลายเซ็นอิเล็กทรอนิกส์)
// onConfirm(pfxFile, password, reason, location, contact, name, imageFile, certInfo) — ตรวจใบรับรอง/รหัสผ่านก่อนเรียก
import React, { useRef, useState } from "react";
import SignModalShell from "./signature/SignModalShell.jsx";
import SignatureCreator from "./signature/SignatureCreator.jsx";
import * as api from "../api.js";

function dataUrlToFile(dataUrl, name) {
  const [meta, body] = dataUrl.split(",");
  const mime = /data:([^;]+)/.exec(meta)?.[1] || "image/png";
  const bin = atob(body);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) arr[i] = bin.charCodeAt(i);
  return new File([arr], name, { type: mime });
}

const INPUT = "w-full px-4 py-2.5 text-base sm:text-sm border border-slate-300 rounded-lg bg-white text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500";

export default function DigitalSignModal({ onConfirm, onCancel }) {
  const [file, setFile] = useState(null);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [reason, setReason] = useState("");
  const [location, setLocation] = useState("");
  const [contact, setContact] = useState("");
  const [name, setName] = useState("");
  const [imageReady, setImageReady] = useState(true);
  // ตรวจใบรับรอง/รหัสผ่านตอนกดตกลง (เดิมรู้ว่ารหัสผิด/ใบหมดอายุก็ตอนวางตำแหน่งเสร็จแล้ว ต้องเริ่มใหม่ทั้งหมด)
  const [checking, setChecking] = useState(false);
  const [certError, setCertError] = useState("");
  const [certInfo, setCertInfo] = useState(null);
  const fileInputRef = React.useRef(null);
  const creatorRef = useRef(null);

  const canConfirm = !!file && password.length > 0 && imageReady && !checking;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canConfirm) return;
    setChecking(true);
    setCertError("");
    let info;
    try {
      info = await api.checkCertificate(file, password);
      setCertInfo(info);
    } catch (err) {
      setCertError(err.message || "ตรวจใบรับรองไม่สำเร็จ");
      setChecking(false);
      return;
    }
    setChecking(false);
    const dataUrl = creatorRef.current?.getDataUrl();
    const imageFile = dataUrl ? dataUrlToFile(dataUrl, "signature.png") : null;
    onConfirm(file, password, reason || undefined, location || undefined, contact || undefined, name || undefined, imageFile, info);
  }

  return (
    <SignModalShell
      title="ลายเซ็นดิจิทัล (ใบรับรอง)"
      subtitle="เลือกไฟล์ใบรับรอง (.p12 / .pfx) และระบุข้อมูลผู้เซ็น"
      icon={
        <svg className="w-5 h-5 text-sky-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      }
      onCancel={onCancel}
      footer={
        <>
          <button type="button" className="px-5 py-2.5 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-100" onClick={onCancel}>
            ยกเลิก
          </button>
          <button type="submit" form="digital-sign-form" disabled={!canConfirm}
            className="px-6 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-600 hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm">
            {checking ? "กำลังตรวจใบรับรอง…" : "ตกลง"}
          </button>
        </>
      }
    >
        <form id="digital-sign-form" onSubmit={handleSubmit} className="space-y-6">
          
          {/* Certificate Selection Section */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-200 pb-2">1. ใบรับรองและรหัสผ่าน</h3>
            
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
              <input
                ref={fileInputRef}
                type="file"
                accept=".p12,.pfx,application/x-pkcs12"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) { setFile(f); setCertError(""); setCertInfo(null); }
                  e.target.value = "";
                }}
              />
              <button 
                type="button" 
                className="w-full mb-3 flex items-center justify-center gap-2 py-2.5 bg-white border border-slate-300 rounded-lg shadow-sm text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors focus:ring-2 focus:ring-sky-500" 
                onClick={() => fileInputRef.current?.click()}
              >
                <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
                เลือกไฟล์ .p12 / .pfx...
              </button>
              <div className="text-sm text-slate-600 flex items-center gap-2">
                {file ? (
                  <><svg className="w-4 h-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg> <span className="font-medium text-green-700 truncate">{file.name}</span></>
                ) : (
                  <><span className="w-2 h-2 rounded-full bg-amber-400"></span> ยังไม่ได้เลือกไฟล์</>
                )}
              </div>
            </div>

            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                className={`${INPUT} pr-12`}
                placeholder="รหัสผ่านสำหรับเปิดคีย์ (Passphrase) *"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setCertError(""); }}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 transition-colors rounded"
                onClick={() => setShowPassword(!showPassword)}
                title={showPassword ? "ซ่อนรหัสผ่าน" : "แสดงรหัสผ่าน"}
              >
                {showPassword ? (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                )}
              </button>
            </div>
            {certError && <p className="text-sm text-red-600" role="alert" data-testid="cert-error">{certError}</p>}
            {certInfo?.warnings?.length > 0 && (
              <ul className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2 list-disc pl-5">
                {certInfo.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            )}
          </div>

          {/* Additional Details Section */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-200 pb-2">2. รายละเอียดเพิ่มเติม (Optional)</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <input
                type="text"
                className={INPUT}
                placeholder="ชื่อผู้เซ็น (Name)"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                type="text"
                className={INPUT}
                placeholder="เหตุผลในการเซ็น (Reason)"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <input
                type="text"
                className={INPUT}
                placeholder="สถานที่เซ็น (Location)"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
              <input
                type="text"
                className={INPUT}
                placeholder="ข้อมูลติดต่อ (Contact Info)"
                value={contact}
                onChange={(e) => setContact(e.target.value)}
              />
            </div>
          </div>

          {/* รูปลายเซ็น (ไม่บังคับ) */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-200 pb-2">3. รูปลายเซ็น (ไม่บังคับ)</h3>
            <SignatureCreator ref={creatorRef} optional onReadyChange={setImageReady} />
          </div>
        </form>
    </SignModalShell>
  );
}
