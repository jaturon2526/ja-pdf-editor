// ลายเซ็นดิจิทัล: ใบรับรอง .p12/.pfx + รายละเอียด + รูปลายเซ็น (ไม่บังคับ — เซ็นสด / พิมพ์ / รูปภาพ เหมือนลายเซ็นอิเล็กทรอนิกส์)
// onConfirm(pfxFile, password, reason, location, contact, name, imageFile, certInfo) — ตรวจใบรับรอง/รหัสผ่านก่อนเรียก
// pfxFile = File ที่เลือก หรือ { certificateId } = ใบรับรองที่บันทึกไว้ (หน้าความปลอดภัย) — ระบบไม่เก็บรหัส ต้องกรอกทุกครั้ง
import React, { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n/I18nContext.jsx";
import { dateLocale } from "../i18n/index.js";
import SignModalShell from "./signature/SignModalShell.jsx";
import SignatureCreator from "./signature/SignatureCreator.jsx";
import * as api from "../api.js";
import { certPasskeyErrorMessage, supportsWebAuthn, unlockWithPasskey } from "../utils/certPasskey.js";

function dataUrlToFile(dataUrl, name) {
  const [meta, body] = dataUrl.split(",");
  const mime = /data:([^;]+)/.exec(meta)?.[1] || "image/png";
  const bin = atob(body);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) arr[i] = bin.charCodeAt(i);
  return new File([arr], name, { type: mime });
}

const fmtDate = (iso, locale) => new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });

// บรรทัดรองของใบที่บันทึกไว้ (ข้อความล้วนในป้ายของ radio — ไม่ซ้อน element)
function certSummary(c, t, locale) {
  const validity = c.expired
    ? t("editor.modals.digitalSign.expired")
    : t("editor.modals.digitalSign.validUntil", { date: fmtDate(c.valid_to, locale) });
  const parts = [
    c.subject_cn || "—",
    t("editor.modals.digitalSign.issuedBy", { issuer: c.issuer_cn || "—" }),
    validity,
  ];
  if (c.passkeys?.length) parts.push(t("editor.modals.digitalSign.passkeyAvailable"));
  return parts.join(" · ");
}

const INPUT = "w-full px-4 py-2.5 text-base sm:text-sm border border-slate-300 rounded-lg bg-white text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-500";

export default function DigitalSignModal({ onConfirm, onCancel }) {
  const { lang, t } = useI18n();
  const locale = dateLocale(lang);
  // ที่มาของใบรับรอง: "saved" = ที่บันทึกไว้บนระบบ · "file" = เลือกไฟล์จากเครื่อง (ไม่มีใบที่บันทึกไว้ → file)
  const [savedCerts, setSavedCerts] = useState(null);
  const [source, setSource] = useState("file");
  const [certId, setCertId] = useState(null);
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
  // ปลดล็อกด้วย passkey ที่ผูกไว้กับใบที่บันทึกไว้ (หน้าความปลอดภัย) — ได้รหัสมาเติมในช่องแทนการพิมพ์
  const [unlocking, setUnlocking] = useState(false);
  const [unlockedBy, setUnlockedBy] = useState(null);
  const fileInputRef = React.useRef(null);
  const creatorRef = useRef(null);

  useEffect(() => {
    let alive = true;
    api.listCertificates().then((list) => {
      if (!alive) return;
      setSavedCerts(list);
      const usable = list.find((c) => !c.expired);
      if (usable) { setSource("saved"); setCertId(usable.id); }
    }).catch(() => { if (alive) setSavedCerts([]); });
    return () => { alive = false; };
  }, []);

  let certificate = file;
  if (source === "saved") {
    certificate = certId ? { certificateId: certId } : null;
  }
  const selectedCert = source === "saved" ? savedCerts?.find((c) => c.id === certId) : null;
  const passkeyReady = !!selectedCert?.passkeys?.length && supportsWebAuthn();

  function changePassword(value) {
    setPassword(value);
    setCertError("");
    setUnlockedBy(null);
  }

  async function handlePasskeyUnlock() {
    if (!selectedCert || unlocking) return;
    setCertError("");
    setUnlocking(true);
    try {
      const pw = await unlockWithPasskey(selectedCert); // เรียก WebAuthn ทันทีจากการกด (Safari)
      setPassword(pw);
      setShowPassword(false);
      setUnlockedBy(selectedCert.id);
    } catch (err) {
      const msg = certPasskeyErrorMessage(err);
      if (msg) setCertError(msg);
    } finally {
      setUnlocking(false);
    }
  }
  const canConfirm = !!certificate && password.length > 0 && imageReady && !checking;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canConfirm) return;
    setChecking(true);
    setCertError("");
    let info;
    try {
      info = await api.checkCertificate(certificate, password);
      setCertInfo(info);
    } catch (err) {
      setCertError(err.message || t("editor.modals.digitalSign.checkFailed"));
      setChecking(false);
      return;
    }
    setChecking(false);
    const dataUrl = creatorRef.current?.getDataUrl();
    const imageFile = dataUrl ? dataUrlToFile(dataUrl, "signature.png") : null;
    onConfirm(certificate, password, reason || undefined, location || undefined, contact || undefined, name || undefined, imageFile, info);
  }

  let passkeyButtonLabel = t("editor.modals.digitalSign.unlockPasskey");
  if (unlocking) {
    passkeyButtonLabel = t("editor.modals.digitalSign.unlockingPasskey");
  } else if (unlockedBy === certId) {
    passkeyButtonLabel = t("editor.modals.digitalSign.unlockedPasskey");
  }

  const sourceOptions = [
    ["saved", t("editor.modals.digitalSign.sourceSaved")],
    ["file", t("editor.modals.digitalSign.sourceFile")],
  ];

  return (
    <SignModalShell
      title={t("editor.modals.digitalSign.title")}
      subtitle={t("editor.modals.digitalSign.subtitle")}
      icon={
        <svg className="w-5 h-5 text-sky-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      }
      onCancel={onCancel}
      footer={
        <>
          <button type="button" className="px-5 py-2.5 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-100" onClick={onCancel}>
            {t("editor.modals.digitalSign.cancel")}
          </button>
          <button type="submit" form="digital-sign-form" disabled={!canConfirm}
            className="px-6 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-600 hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm">
            {checking ? t("editor.modals.digitalSign.checking") : t("editor.modals.digitalSign.confirm")}
          </button>
        </>
      }
    >
        <form id="digital-sign-form" onSubmit={(e) => void handleSubmit(e)} className="space-y-6">
          
          {/* Certificate Selection Section */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-200 pb-2">{t("editor.modals.digitalSign.sectionCert")}</h3>
            
            {savedCerts?.length > 0 && (
              <div role="radiogroup" aria-label={t("editor.modals.digitalSign.sourceAria")} className="grid grid-cols-2 gap-2">
                {sourceOptions.map(([value, text]) => (
                  <button key={value} type="button" role="radio" aria-checked={source === value}
                    onClick={() => { setSource(value); setCertError(""); setCertInfo(null); }}
                    className={`py-2 text-sm rounded-lg border ${source === value ? "border-sky-600 bg-sky-50 text-sky-800 font-medium" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}>
                    {text}
                  </button>
                ))}
              </div>
            )}

            {source === "saved" && savedCerts?.length > 0 ? (
              <ul className="space-y-2" data-testid="saved-certificates">
                {savedCerts.map((c) => (
                  <li key={c.id}>
                    <label className={`grid grid-cols-[auto_1fr] gap-x-3 items-start p-3 rounded-lg border text-sm ${c.expired ? "opacity-60 cursor-not-allowed" : "cursor-pointer"} ${certId === c.id ? "border-sky-600 bg-sky-50" : "border-slate-200 bg-white"}`}>
                      <input type="radio" name="saved-cert" className="mt-1 row-span-2" disabled={c.expired} checked={certId === c.id}
                        onChange={() => { setCertId(c.id); setCertError(""); setCertInfo(null); if (unlockedBy) { setPassword(""); setUnlockedBy(null); } }} />
                      <span className="block min-w-0 font-medium text-slate-900 break-words">{c.label}</span>
                      <span className="block min-w-0 text-xs text-slate-600 break-words">{certSummary(c, t, locale)}</span>
                    </label>
                  </li>
                ))}
              </ul>
            ) : (
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
                {t("editor.modals.digitalSign.chooseFile")}
              </button>
              <div className="text-sm text-slate-600 flex items-center gap-2">
                {file ? (
                  <><svg className="w-4 h-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg> <span className="font-medium text-green-700 truncate">{file.name}</span></>
                ) : (
                  <><span className="w-2 h-2 rounded-full bg-amber-400"></span> {t("editor.modals.digitalSign.noFileSelected")}</>
                )}
              </div>
              {/* แสดงตั้งแต่เปิด (ไม่รอผลโหลดรายการ) — กันเนื้อหาด้านล่างเลื่อนลงหลังเปิดหน้าต่าง */}
              {!savedCerts?.length && (
                <p className="mt-2 text-xs text-slate-500">{t("editor.modals.digitalSign.saveCertHint")}</p>
              )}
            </div>
            )}

            {passkeyReady && (
              <button type="button" onClick={() => void handlePasskeyUnlock()} disabled={unlocking || unlockedBy === certId}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-sky-600 bg-white text-sm font-medium text-sky-700 hover:bg-sky-50 disabled:opacity-60">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true"><circle cx="7.5" cy="15.5" r="4.5" /><path d="M10.7 12.3L21 2M16 7l3 3M18.5 4.5l2 2" /></svg>
                {passkeyButtonLabel}
              </button>
            )}
            {unlockedBy === certId && (
              <p className="text-xs text-green-700" role="status">{t("editor.modals.digitalSign.unlockedHint")}</p>
            )}
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                className={`${INPUT} pr-12`}
                placeholder={t("editor.modals.digitalSign.passphrasePlaceholder")}
                value={password}
                onChange={(e) => changePassword(e.target.value)}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 transition-colors rounded"
                onClick={() => setShowPassword(!showPassword)}
                title={showPassword ? t("editor.modals.digitalSign.hidePassword") : t("editor.modals.digitalSign.showPassword")}
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
            <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-200 pb-2">{t("editor.modals.digitalSign.sectionDetails")}</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <input
                type="text"
                className={INPUT}
                placeholder={t("editor.modals.digitalSign.namePlaceholder")}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                type="text"
                className={INPUT}
                placeholder={t("editor.modals.digitalSign.reasonPlaceholder")}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <input
                type="text"
                className={INPUT}
                placeholder={t("editor.modals.digitalSign.locationPlaceholder")}
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
              <input
                type="text"
                className={INPUT}
                placeholder={t("editor.modals.digitalSign.contactPlaceholder")}
                value={contact}
                onChange={(e) => setContact(e.target.value)}
              />
            </div>
          </div>

          {/* รูปลายเซ็น (ไม่บังคับ) */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-200 pb-2">{t("editor.modals.digitalSign.sectionImage")}</h3>
            <SignatureCreator ref={creatorRef} optional onReadyChange={setImageReady} />
          </div>
        </form>
    </SignModalShell>
  );
}
