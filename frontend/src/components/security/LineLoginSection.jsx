// ส่วน "เข้าสู่ระบบด้วย LINE" ในหน้าความปลอดภัย — เชื่อม/ยกเลิก (backend: /auth/line/*, สถานะจาก GET /line/status → login)
// เชื่อม = ไปหน้าอนุญาตของ LINE แล้วกลับมาที่ /auth/line/callback → /security?line_login=linked
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getLineStatus, startLineLoginLink, unlinkLineLogin } from "../../api";
import { useI18n } from "../../i18n/I18nContext.jsx";
import LineIcon from "../LineIcon.jsx";

export default function LineLoginSection() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const [login, setLogin] = useState(null); // {enabled, linked}
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(params.get("line_login") === "linked" ? t("security.lineLogin.linkedSuccess") : "");
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);

  useEffect(() => {
    getLineStatus()
      .then((s) => setLogin(s.login || { enabled: false }))
      .catch(() => setLogin({ enabled: false }));
    if (params.get("line_login")) {
      params.delete("line_login");
      setParams(params, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!login || !login.enabled) return null;

  async function connect() {
    setError("");
    setBusy(true);
    try {
      await startLineLoginLink(); // ไปหน้า LINE
    } catch (e) {
      setError(e.message || t("security.lineLogin.connectError"));
      setBusy(false);
    }
  }

  async function unlink() {
    setBusy(true);
    setError("");
    try {
      setLogin(await unlinkLineLogin());
      setConfirmUnlink(false);
      setSuccess(t("security.lineLogin.unlinkSuccess"));
    } catch (e) {
      setError(e.message || t("security.lineLogin.unlinkError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-10 pt-6 border-t border-gray-200" aria-labelledby="line-login-title" data-testid="line-login-section">
      <div className="flex items-start gap-3 mb-3">
        <div className="p-2 rounded-lg bg-green-50 text-[#06C755] shrink-0"><LineIcon /></div>
        <div className="min-w-0">
          <h2 id="line-login-title" className="text-lg font-semibold text-gray-900">{t("security.lineLogin.title")}</h2>
          <p className="text-sm text-gray-600">{t("security.lineLogin.desc")}</p>
        </div>
      </div>
      {error && <div className="mb-3 p-3 bg-red-100 text-red-700 rounded text-sm" role="alert">{error}</div>}
      {success && <div className="mb-3 p-3 bg-green-100 text-green-700 rounded text-sm">{success}</div>}
      {login.linked ? (
        <div className="flex flex-wrap items-center gap-3 text-sm" data-testid="line-login-linked">
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-green-100 text-green-800 font-medium">
            <LineIcon className="w-4 h-4" /> {t("security.lineLogin.linkedBadge")}
          </span>
          {confirmUnlink ? (
            <>
              <span className="text-gray-700">{t("security.lineLogin.confirmUnlink")}</span>
              <button type="button" onClick={() => void unlink()} disabled={busy} className="px-3 py-1.5 rounded bg-red-600 text-white disabled:opacity-50">
                {t("common.cancel")}
              </button>
              <button type="button" onClick={() => setConfirmUnlink(false)} className="px-3 py-1.5 rounded text-gray-600 hover:bg-gray-100">
                {t("security.lineLogin.noBtn")}
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setConfirmUnlink(true)} className="text-red-600 hover:underline">
              {t("security.lineLogin.unlinkBtn")}
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => void connect()}
          disabled={busy}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#06C755] hover:bg-[#05b34c] text-white font-medium disabled:opacity-50"
        >
          <LineIcon /> {busy ? t("security.lineLogin.connectingBtn") : t("security.lineLogin.connectBtn")}
        </button>
      )}
    </section>
  );
}
