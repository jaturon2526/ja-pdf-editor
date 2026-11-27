import React, { useEffect, useState } from "react";
import { useI18n } from "../i18n/I18nContext.jsx";

export default function PasswordModal({ fileName, onSubmit, onCancel, error, submitting }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && !submitting) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, submitting]);

  function handleSubmit(e) {
    e.preventDefault();
    if (password) onSubmit(password);
  }

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h2 className="modal-title">{t("passwordModal.title")}</h2>
        <p className="modal-subtitle">
          {t("passwordModal.subtitleBefore")} <strong>{fileName}</strong>
        </p>
        <form onSubmit={handleSubmit}>
          <div style={{ position: "relative" }}>
            <input
              type={showPassword ? "text" : "password"}
              autoFocus
              className="modal-input"
              style={{ paddingRight: "40px" }}
              placeholder={t("passwordModal.placeholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              className="icon-btn"
              style={{ position: "absolute", right: "5px", top: "50%", transform: "translateY(-50%)", width: "32px", height: "32px", background: "none", border: "none", cursor: "var(--cursor-hand)", color: "var(--color-text-muted)" }}
              onClick={() => setShowPassword(!showPassword)}
              title={showPassword ? t("passwordModal.hide") : t("passwordModal.show")}
            >
              {showPassword ? <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg> : <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>}
            </button>
          </div>
          {error && <div className="modal-error">{error}</div>}
          <div className="modal-actions">
            <button type="button" className="secondary-btn" onClick={onCancel}>
              {t("common.cancel")}
            </button>
            <button type="submit" className="primary-btn" disabled={!password || submitting}>
              {submitting ? t("passwordModal.checking") : t("passwordModal.unlock")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
