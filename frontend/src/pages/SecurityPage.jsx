import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { changePassword } from "../api";
import { useI18n } from "../i18n/I18nContext.jsx";
import { validatePassword } from "../utils/password";
import PasskeySection from "../components/security/PasskeySection.jsx";
import CertificatesSection from "../components/security/CertificatesSection.jsx";
import SavedSignaturesSection from "../components/security/SavedSignaturesSection.jsx";
import LineSection from "../components/security/LineSection.jsx";
import LineLoginSection from "../components/security/LineLoginSection.jsx";

export default function SecurityPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [passkeyVersion, setPasskeyVersion] = useState(0);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (newPassword !== confirmPassword) {
      setError(t("security.password.mismatch"));
      return;
    }
    const pwdError = validatePassword(newPassword);
    if (pwdError) {
      setError(pwdError);
      return;
    }

    setSaving(true);
    try {
      await changePassword(oldPassword, newPassword);
      setSuccess(t("security.password.success"));
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err.message || t("security.password.error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-6">
      <div className="max-w-2xl mx-auto bg-white rounded-lg shadow-sm border border-gray-200 p-5 sm:p-8">
        <div className="flex items-center gap-4 mb-8 border-b pb-4">
          <button type="button" onClick={() => void navigate("/dashboard")} className="text-gray-500 hover:text-gray-800">
            {t("profile.backToDashboard")}
          </button>
          <h1 className="text-2xl font-bold">{t("pages.securityTitle")}</h1>
        </div>

        <PasskeySection onChanged={() => setPasskeyVersion((v) => v + 1)} />

        <CertificatesSection />

        <SavedSignaturesSection passkeyVersion={passkeyVersion} />

        <LineLoginSection />

        <LineSection />

        <h2 className="text-lg font-semibold text-gray-900 mt-10 mb-4 pt-6 border-t border-gray-200">{t("pages.changePasswordTitle")}</h2>
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-5">
          {error && <div className="p-3 bg-red-100 text-red-700 rounded text-sm">{error}</div>}
          {success && <div className="p-3 bg-green-100 text-green-700 rounded text-sm">{success}</div>}

          <div>
            <label htmlFor="securitypage-f69" className="block text-sm font-medium text-gray-700 mb-1">{t("security.password.oldLabel")}</label>
            <input id="securitypage-f69"
              type="password"
              required
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label htmlFor="securitypage-f80" className="block text-sm font-medium text-gray-700 mb-1">{t("security.password.newLabel")}</label>
            <input id="securitypage-f80"
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label htmlFor="securitypage-f91" className="block text-sm font-medium text-gray-700 mb-1">{t("security.password.confirmLabel")}</label>
            <input id="securitypage-f91"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="mt-2 text-xs text-rose-500">
              {t("security.password.hint")}
            </p>
          </div>

          <div className="pt-4 border-t flex justify-end">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:opacity-50"
            >
              {saving ? t("common.saving") : t("security.password.submitBtn")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
