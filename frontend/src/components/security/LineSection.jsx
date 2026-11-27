// ส่วน "แจ้งเตือนทาง LINE" ในหน้าความปลอดภัย — ผูกบัญชีด้วยรหัสที่ส่งในแชท LINE OA (backend: /line/*)
// มือถือ: กดปุ่มเปิด LINE (ข้อความรหัสถูกพิมพ์ไว้ให้แล้ว แค่กดส่ง) · คอมพิวเตอร์: สแกน QR ด้วยมือถือ
import { useEffect, useRef, useState } from "react";
import { createLineLinkCode, getLineStatus, setLineNotifications, unlinkLine } from "../../api";
import { useI18n } from "../../i18n/I18nContext.jsx";
import LineIcon from "../LineIcon.jsx";

const fmtDate = (iso, locale) =>
  iso ? new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" }) : null;

export default function LineSection() {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const fmt = (iso) => fmtDate(iso, locale);
  const [status, setStatus] = useState(null);
  const [link, setLink] = useState(null); // {code, chat_url, qr_svg, expiresAt}
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    getLineStatus()
      .then(setStatus)
      .catch(() => setStatus({ enabled: false }));
  }, []);

  // ระหว่างรอผู้ใช้ส่งรหัสใน LINE: เช็คสถานะทุก 3 วินาที จนผูกสำเร็จหรือรหัสหมดอายุ
  useEffect(() => {
    if (!link) return undefined;
    pollRef.current = setInterval(async () => {
      setNow(Date.now());
      if (Date.now() > link.expiresAt) return;
      try {
        const s = await getLineStatus();
        if (s.linked) {
          setStatus(s);
          setLink(null);
          setSuccess(t("security.lineNotify.linkedSuccess", { name: s.display_name ? ` "${s.display_name}"` : "" }));
        }
      } catch {
        /* ลองใหม่รอบถัดไป */
      }
    }, 3000);
    return () => clearInterval(pollRef.current);
  }, [link, t]);

  if (!status || !status.enabled) return null;

  async function startLink() {
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const r = await createLineLinkCode();
      setLink({ ...r, expiresAt: Date.now() + r.expires_in * 1000 });
      setNow(Date.now());
    } catch (e) {
      setError(e.message || t("security.lineNotify.codeError"));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(enabled) {
    const prev = status;
    setStatus({ ...status, notifications: enabled }); // แสดงผลทันที แล้วค่อยยืนยันจาก server
    setBusy(true);
    setError("");
    try {
      setStatus(await setLineNotifications(enabled));
    } catch (e) {
      setStatus(prev);
      setError(e.message || t("security.lineNotify.saveError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleUnlink() {
    setBusy(true);
    setError("");
    try {
      setStatus(await unlinkLine());
      setConfirmUnlink(false);
      setSuccess(t("security.lineNotify.unlinkSuccess"));
    } catch (e) {
      setError(e.message || t("security.lineNotify.unlinkError"));
    } finally {
      setBusy(false);
    }
  }

  const remaining = link ? Math.max(0, Math.round((link.expiresAt - now) / 1000)) : 0;
  const expired = link && remaining === 0;
  const remainingText = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`;

  return (
    <section className="mt-10 pt-6 border-t border-gray-200" aria-labelledby="line-title" data-testid="line-section">
      <div className="flex items-start gap-3 mb-3">
        <div className="p-2 rounded-lg bg-green-50 text-[#06C755] shrink-0"><LineIcon /></div>
        <div className="min-w-0">
          <h2 id="line-title" className="text-lg font-semibold text-gray-900">{t("security.lineNotify.title")}</h2>
          <p className="text-sm text-gray-600">
            {t("security.lineNotify.desc")}
          </p>
        </div>
      </div>

      {error && <div className="mb-3 p-3 bg-red-100 text-red-700 rounded text-sm" role="alert">{error}</div>}
      {success && <div className="mb-3 p-3 bg-green-100 text-green-700 rounded text-sm">{success}</div>}

      {status.linked ? (
        <div className="rounded-lg border border-gray-200 p-4 space-y-3" data-testid="line-linked">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-green-100 text-green-800 font-medium">
              <LineIcon className="w-4 h-4" /> {t("security.lineNotify.connectedBadge")}
            </span>
            {status.display_name && <span className="font-medium text-gray-900 break-all">{status.display_name}</span>}
            {status.linked_at && <span className="text-gray-500">{t("security.lineNotify.since", { date: fmt(status.linked_at) })}</span>}
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={!!status.notifications}
              disabled={busy}
              onChange={(e) => void toggle(e.target.checked)}
            />
            {t("security.lineNotify.toggleLabel")}
          </label>
          {confirmUnlink ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-gray-700">{t("security.lineNotify.confirmUnlink")}</span>
              <button type="button" onClick={() => void handleUnlink()} disabled={busy} className="px-3 py-1.5 rounded bg-red-600 text-white disabled:opacity-50">
                {t("security.lineNotify.confirmUnlinkBtn")}
              </button>
              <button type="button" onClick={() => setConfirmUnlink(false)} className="px-3 py-1.5 rounded text-gray-600 hover:bg-gray-100">
                {t("security.lineLogin.noBtn")}
              </button>
            </div>
          ) : (
            <button type="button" onClick={() => setConfirmUnlink(true)} className="text-sm text-red-600 hover:underline">
              {t("security.lineNotify.unlinkBtn")}
            </button>
          )}
        </div>
      ) : link && !expired ? (
        <div className="rounded-lg border border-green-200 bg-green-50/50 p-4" data-testid="line-link-pending">
          <p className="text-sm text-gray-700 mb-2">{t("security.lineNotify.sendCodeHint")}</p>
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <code className="text-2xl font-bold tracking-widest text-gray-900 bg-white border border-gray-200 rounded px-3 py-1" data-testid="line-code">
              {link.code}
            </code>
            <span className="text-xs text-gray-500">{t("security.lineNotify.expiresIn", { time: remainingText })}</span>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-start gap-4">
            <div className="flex-1 space-y-2">
              {link.chat_url && (
                <a
                  href={link.chat_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-4 py-2.5 rounded-lg bg-[#06C755] hover:bg-[#05b34c] text-white font-semibold"
                >
                  <LineIcon /> {t("security.lineNotify.openLineBtn")}
                </a>
              )}
              <ol className="text-sm text-gray-600 list-decimal pl-5 space-y-0.5">
                <li>{t("security.lineNotify.step1")}</li>
                <li>{t("security.lineNotify.step2")}</li>
                <li>{t("security.lineNotify.step3")}</li>
              </ol>
            </div>
            {link.qr_svg && (
              <img src={link.qr_svg} alt={t("security.lineNotify.qrAlt")} className="hidden sm:block w-40 h-40 rounded border border-gray-200 bg-white" />
            )}
          </div>
          <button type="button" onClick={() => setLink(null)} className="mt-3 text-sm text-gray-500 hover:underline">
            {t("common.cancel")}
          </button>
        </div>
      ) : (
        <div>
          {expired && <p className="mb-2 text-sm text-amber-700">{t("security.lineNotify.expiredHint")}</p>}
          <button
            type="button"
            onClick={() => void startLink()}
            disabled={busy}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#06C755] hover:bg-[#05b34c] text-white font-medium disabled:opacity-50"
          >
            <LineIcon /> {t("security.lineNotify.connectBtn")}
          </button>
        </div>
      )}

      {status.quota && (
        <p className="mt-3 text-xs text-gray-500" data-testid="line-quota">
          {t("security.lineNotify.adminQuota", { used: status.quota.used, limit: status.quota.limit })}
        </p>
      )}
    </section>
  );
}
