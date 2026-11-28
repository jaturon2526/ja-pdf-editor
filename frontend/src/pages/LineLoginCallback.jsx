// หน้ารับผลจาก LINE Login (/auth/line/callback) — backend: /auth/line/* (ดู services/line_login_service.py)
// ?code&state  กลับจากหน้าอนุญาตของ LINE → เข้าสู่ระบบ / เชื่อมบัญชี / ขออีเมล (บัญชี LINE ไม่มีอีเมล)
// ?error       ผู้ใช้กดยกเลิกที่ LINE
// ?confirm     กดลิงก์ยืนยันอีเมลที่ส่งไป (ต้องเปิดในเบราว์เซอร์เดียวกับที่เริ่ม)
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  completeLineLogin,
  confirmLineLoginEmail,
  requestLineLoginEmail,
  takeLineLoginState,
} from "../api";
import LineIcon from "../components/LineIcon.jsx";
import { useI18n } from "../i18n/I18nContext.jsx";

function finishLogin() {
  window.location.href = "/dashboard"; // token อยู่ใน HttpOnly cookie แล้ว
}

function Card({ children }) {
  const { t } = useI18n();
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto w-full sm:max-w-md bg-white py-8 px-5 shadow-xl rounded-xl sm:px-10 border border-gray-100">
        <div className="flex items-center justify-center gap-2 text-[#06C755] mb-4">
          <LineIcon className="w-8 h-8" />
          <span className="font-semibold text-gray-900">{t("authExtra.lineCallback.title")}</span>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function LineLoginCallback() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const started = useRef(false);
  const [view, setView] = useState({ kind: "working" });
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (started.current) return; // StrictMode เรียก effect ซ้ำ — code/state ใช้ได้ครั้งเดียว
    started.current = true;
    const confirm = params.get("confirm");
    const code = params.get("code");
    const fail = (e, back = "/login") => setView({ kind: "error", message: e?.message || String(e), back });

    if (confirm) {
      confirmLineLoginEmail(confirm).then(finishLogin).catch((e) => fail(e));
      return;
    }
    const saved = takeLineLoginState();
    const back = saved.mode === "link" ? "/security" : "/login";
    if (params.get("error")) {
      setView({ kind: "cancelled", back });
      return;
    }
    if (!code || !saved.state || saved.state !== params.get("state")) {
      fail(t("authExtra.lineCallback.invalidState"), back);
      return;
    }
    completeLineLogin(code, params.get("state"))
      .then((r) => {
        if (r.status === "login") finishLogin();
        else if (r.status === "linked") void navigate("/security?line_login=linked", { replace: true });
        else setView({ kind: "email", name: r.name });
      })
      .catch((e) => fail(e, back));
  }, [params, navigate, t]);

  async function submitEmail(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await requestLineLoginEmail(email.trim());
      setView({ kind: "sent", email: r.email, name: view.name });
    } catch (err) {
      setView({ ...view, error: err.message || t("authExtra.lineCallback.sendEmailFailed") });
    } finally {
      setBusy(false);
    }
  }

  if (view.kind === "working") {
    return (
      <Card>
        <p className="text-center text-gray-600" role="status">{t("authExtra.lineCallback.signingIn")}</p>
      </Card>
    );
  }

  if (view.kind === "cancelled" || view.kind === "error") {
    return (
      <Card>
        <p className={`text-sm mb-6 ${view.kind === "error" ? "text-red-700" : "text-gray-700"}`} role="alert" data-testid="line-login-message">
          {view.kind === "error" ? view.message : t("authExtra.lineCallback.cancelled")}
        </p>
        <Link to={view.back} className="block w-full text-center py-2 px-4 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium">
          {view.back === "/security" ? t("authExtra.lineCallback.backToSecurity") : t("authExtra.lineCallback.backToLogin")}
        </Link>
      </Card>
    );
  }

  if (view.kind === "sent") {
    return (
      <Card>
        <div data-testid="line-login-sent" className="space-y-3 text-sm text-gray-700">
          <p>
            {t("authExtra.lineCallback.sentBefore")} <strong className="break-all">{view.email}</strong>{t("authExtra.lineCallback.sentAfter")}
          </p>
          <p>
            {t("authExtra.lineCallback.sentHintBefore")}<strong>{t("authExtra.lineCallback.sentHintStrong")}</strong>{t("authExtra.lineCallback.sentHintAfter")}
          </p>
          <button type="button" onClick={() => setView({ kind: "email", name: view.name })} className="text-blue-600 hover:underline">
            {t("authExtra.lineCallback.changeOrResend")}
          </button>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <form onSubmit={(e) => void submitEmail(e)} className="space-y-4" data-testid="line-login-email">
        <p className="text-sm text-gray-700">
          {view.name ? <>{t("authExtra.lineCallback.greetingPrefix")} <strong>{view.name}</strong> — </> : null}
          {t("authExtra.lineCallback.emailPrompt")}
        </p>
        {view.error && <div className="p-3 rounded bg-red-50 text-red-700 text-sm" role="alert">{view.error}</div>}
        <div>
          <label htmlFor="line-email" className="block text-sm font-medium text-gray-700 mb-1">{t("authExtra.lineCallback.emailLabel")}</label>
          <input
            id="line-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border border-gray-300 rounded-md px-3 py-2"
            placeholder="you@example.com"
          />
        </div>
        <button type="submit" disabled={busy || !email.trim()} className="w-full py-2 px-4 rounded-md bg-[#06C755] hover:bg-[#05b34c] text-white font-medium disabled:opacity-50">
          {busy ? t("authExtra.lineCallback.sending") : t("authExtra.lineCallback.sendLink")}
        </button>
        <Link to="/login" className="block text-center text-sm text-gray-500 hover:underline">{t("authExtra.lineCallback.cancel")}</Link>
      </form>
    </Card>
  );
}
