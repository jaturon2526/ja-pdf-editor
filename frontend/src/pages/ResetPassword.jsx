import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api";
import { useI18n } from "../i18n/I18nContext.jsx";
import { validatePassword } from "../utils/password";

export default function ResetPassword() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  if (!token) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white rounded-lg shadow-md p-8 text-center text-red-600">
          {t("auth.resetPasswordMissingToken")}
        </div>
      </div>
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (newPassword !== confirmPassword) {
      setError(t("auth.resetPasswordMismatch"));
      return;
    }
    const pwdError = validatePassword(newPassword);
    if (pwdError) {
      setError(pwdError);
      return;
    }

    setLoading(true);
    try {
      await resetPassword(token, newPassword);
      setSuccess(true);
    } catch (err) {
      setError(err.message || t("auth.resetPasswordFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-lg shadow-md p-8">
        <h2 className="text-2xl font-bold text-center mb-6">{t("auth.resetPasswordTitle")}</h2>

        {success ? (
          <div className="text-center">
            <div className="mb-4 text-green-600 bg-green-50 p-4 rounded">
              {t("auth.resetPasswordSuccess")}
            </div>
            <Link to="/login" className="inline-block bg-blue-600 text-white font-semibold py-2 px-4 rounded hover:bg-blue-700">
              {t("auth.goToLogin")}
            </Link>
          </div>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
            {error && <div className="text-red-500 text-sm bg-red-50 p-2 rounded">{error}</div>}

            <div>
              <label htmlFor="resetpassword-f70" className="block text-sm font-medium text-gray-700 mb-1">
                {t("auth.resetPasswordNew")}
              </label>
              <input id="resetpassword-f70"
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label htmlFor="resetpassword-f83" className="block text-sm font-medium text-gray-700 mb-1">
                {t("auth.resetPasswordConfirm")}
              </label>
              <input id="resetpassword-f83"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="mt-2 text-xs text-rose-500">
                {t("auth.resetPasswordRule")}
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 text-white font-semibold py-2 rounded hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? t("common.processing") : t("auth.resetPasswordSave")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
