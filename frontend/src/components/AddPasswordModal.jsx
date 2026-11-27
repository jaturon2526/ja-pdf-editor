// เข้ารหัส PDF — ใช้ทั้งเมนู ไฟล์ > เข้ารหัส PDF... ในหน้าแก้ไข และเครื่องมือด่วน/เมนู ☰ บน Dashboard
// กรอกรหัสผ่าน 2 ครั้ง (กันพิมพ์ผิดแล้วล็อกตัวเองออกจากไฟล์) + เลือกวิธีเข้ารหัส — ไฟล์ที่ได้เป็น PDF 1.7 เสมอ
// - AES-256 (แนะนำ): PDF 1.7 + Adobe Extension Level 8 — Acrobat/Reader ปี 2010 ขึ้นไป เบราว์เซอร์ และแอปมือถือปัจจุบัน
//   เปิดได้ · รองรับรหัสผ่านภาษาไทย · ต้านการเดารหัสได้ดีกว่า
// - AES-128: สำหรับโปรแกรมรุ่นเก่ามาก (Acrobat 7–9) — รหัสผ่านต้องเป็นตัวอังกฤษ/ตัวเลข/สัญลักษณ์ ไม่เกิน 32 ตัว
// pdfa: ไฟล์เป็น PDF/A (มาตรฐานเก็บถาวร ซึ่งห้ามเข้ารหัส) → เตือนว่าไฟล์ที่ได้จะไม่เป็น PDF/A แล้ว
import { useEffect, useState } from "react";
import { useI18n } from "../i18n/I18nContext.jsx";

export const ENCRYPTION_OPTIONS = [
  {
    value: "aes256",
    labelKey: "addPasswordModal.aes256Label",
    hintKey: "addPasswordModal.aes256Hint",
  },
  {
    value: "aes128",
    labelKey: "addPasswordModal.aes128Label",
    hintKey: "addPasswordModal.aes128Hint",
  },
];

// ตรงกับ backend check_password_for_mode — AES-128 รับเฉพาะอักษรละติน (Latin-1)
// eslint-disable-next-line no-control-regex
const LATIN1 = /^[\u0000-ÿ]*$/;
export function passwordProblem(password, encryption, t) {
  if (encryption !== "aes128" || !password) return null;
  if (!LATIN1.test(password)) return t ? t("addPasswordModal.errAes128NonLatin") : "AES-128 ใช้รหัสผ่านภาษาไทยไม่ได้ — ใช้ตัวอังกฤษ/ตัวเลข/สัญลักษณ์ หรือเลือก AES-256";
  if (password.length > 32) return t ? t("addPasswordModal.errAes128Len") : "AES-128 ใช้รหัสผ่านได้ไม่เกิน 32 ตัวอักษร — ตั้งให้สั้นลง หรือเลือก AES-256";
  return null;
}

function EyeIcon({ open }) {
  return open ? (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
  );
}

export default function AddPasswordModal({
  onSubmit,
  onCancel,
  error,
  submitting,
  pdfa = null,
  subtitle,
}) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [encryption, setEncryption] = useState("aes256");

  const resolvedSubtitle = subtitle ?? t("addPasswordModal.defaultSubtitle");
  const mismatch = confirmPassword.length > 0 && password !== confirmPassword;
  const problem = passwordProblem(password, encryption, t);
  const canSubmit = password.trim().length > 0 && password === confirmPassword && !problem && !submitting;

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !submitting && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, submitting]);

  function handleSubmit(e) {
    e.preventDefault();
    if (canSubmit) onSubmit(password, encryption);
  }

  const input = "block w-full pl-3 pr-11 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500";
  const toggleLabel = showPassword ? t("passwordModal.hide") : t("passwordModal.show");
  const eye = (
    <button type="button" onClick={() => setShowPassword((v) => !v)} title={toggleLabel}
      aria-label={toggleLabel}
      className="absolute right-1 top-1/2 -translate-y-1/2 w-9 h-9 flex items-center justify-center text-gray-500 hover:text-gray-700">
      <EyeIcon open={showPassword} />
    </button>
  );

  return (
    <div role="presentation" className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && onCancel()}>
      <form role="dialog" aria-modal="true" aria-labelledby="add-password-title" onSubmit={handleSubmit}
        className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92dvh]">
        <div className="p-4 border-b border-gray-100">
          <h2 id="add-password-title" className="text-lg font-bold text-gray-900">{t("addPasswordModal.title")}</h2>
          <p className="mt-1 text-sm text-gray-500 break-words">{resolvedSubtitle}</p>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto">
          {pdfa && (
            <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-900" role="alert" data-testid="pdfa-warning">
              <strong>{t("addPasswordModal.pdfaTitle", { pdfa })}</strong> {t("addPasswordModal.pdfaMid")} <strong>{t("addPasswordModal.pdfaStrong")}</strong>{" "}
              {t("addPasswordModal.pdfaAfter")}
              <span className="block mt-1 text-xs">{t("addPasswordModal.pdfaTip")}</span>
            </div>
          )}
          <div className="relative">
            <input type={showPassword ? "text" : "password"} autoFocus className={input} placeholder={t("addPasswordModal.newPasswordPh")}
              aria-label={t("addPasswordModal.newPasswordPh")} maxLength={128} autoComplete="new-password"
              value={password} onChange={(e) => setPassword(e.target.value)} />
            {eye}
          </div>
          <div className="relative">
            <input type={showPassword ? "text" : "password"} className={input} placeholder={t("addPasswordModal.confirmPasswordPh")}
              aria-label={t("addPasswordModal.confirmPasswordAria")} maxLength={128} autoComplete="new-password"
              value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            {eye}
          </div>
          {mismatch && <p className="text-sm text-red-600">{t("addPasswordModal.mismatch")}</p>}

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-gray-800 mb-1">{t("addPasswordModal.methodLegend")}</legend>
            {ENCRYPTION_OPTIONS.map((o) => (
              <label key={o.value}
                className={`grid grid-cols-[auto_1fr] gap-x-3 items-start p-3 rounded-lg border cursor-pointer ${encryption === o.value ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:bg-gray-50"}`}>
                <input type="radio" name="encryption" className="mt-1 row-span-2" value={o.value} checked={encryption === o.value}
                  onChange={() => setEncryption(o.value)} />
                <span className="block text-sm font-medium text-gray-900">{t(o.labelKey)}</span>
                <span className="block text-xs text-gray-500">{t(o.hintKey)}</span>
              </label>
            ))}
          </fieldset>
          {problem && <p className="text-sm text-red-600" role="alert">{problem}</p>}
          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          <p className="text-xs text-gray-500">{t("addPasswordModal.remember")}</p>
        </div>

        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onCancel} disabled={submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">{t("common.cancel")}</button>
          <button type="submit" disabled={!canSubmit}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-40">
            {submitting ? t("addPasswordModal.submitting") : t("addPasswordModal.submitBtn")}
          </button>
        </div>
      </form>
    </div>
  );
}
