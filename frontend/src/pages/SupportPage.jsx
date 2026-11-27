// ☕ สนับสนุนผู้พัฒนา — QR พร้อมเพย์ + ระดับสิทธิ์ + แจ้งโอน + ประวัติ (แทนหน้า "อัปเกรดแพ็กเกจ" เดิม)
// เปิดดูได้โดยไม่ต้อง login · แจ้งโอนต้อง login (สิทธิ์ผูกกับบัญชี) · แอดมินตรวจยอดแล้วอนุมัติ
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AppBrand from "../components/AppBrand.jsx";
import { isLoggedIn } from "../api/client.js";
import { donationQrUrl, getDonationInfo, getMyDonations, reportDonation } from "../api/donations.js";
import { useI18n } from "../i18n/I18nContext.jsx";

const PRESETS = [49, 99, 299, 499];
const STATUS_CLS = {
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-700",
};
const STATUS_KEY = {
  pending: "support.statusPending",
  approved: "support.statusApproved",
  rejected: "support.statusRejected",
};

function formatStorage(mb, locale) {
  if (!mb) return "-";
  return mb >= 1024 ? `${(mb / 1024).toLocaleString(locale, { maximumFractionDigits: 1 })} GB` : `${mb} MB`;
}

function formatDays(days, t) {
  if (days % 365 === 0) return t("support.daysYears", { n: days / 365 });
  if (days % 30 === 0) return t("support.daysMonths", { n: days / 30 });
  return t("support.daysDays", { n: days });
}

function localNow() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default function SupportPage() {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const navigate = useNavigate();
  const loggedIn = isLoggedIn();
  const [info, setInfo] = useState(null);
  const [mine, setMine] = useState(null);
  const [amount, setAmount] = useState(99);
  const [custom, setCustom] = useState("");
  const [form, setForm] = useState({ when: localNow(), anonymous: false, showOnBoard: true, displayName: "", message: "" });
  const [slip, setSlip] = useState(null);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    getDonationInfo().then(setInfo).catch(() => setInfo({ enabled: false, tiers: [] }));
    if (loggedIn) getMyDonations().then(setMine).catch(() => {});
  }, [loggedIn]);

  const value = custom !== "" ? Number(custom) : amount;
  const validAmount = Number.isFinite(value) && value >= 1 && value <= 100000;
  const perk = useMemo(() => {
    if (!info?.tiers?.length || !validAmount) return null;
    return [...info.tiers].filter((tier) => value >= tier.min_amount).pop() || null;
  }, [info, value, validAmount]);

  async function submit(e) {
    e.preventDefault();
    setNotice(null);
    if (!validAmount) return setNotice({ error: true, text: t("support.invalidAmountError") });
    setSending(true);
    try {
      const result = await reportDonation({
        amount: value, transferredAt: new Date(form.when), anonymous: form.anonymous, showOnBoard: form.showOnBoard,
        displayName: form.displayName.trim(), message: form.message.trim(), slip,
      });
      const grantText = result?.granted_plan
        ? t("support.approvedGrant", { plan: result.granted_plan.toUpperCase(), duration: formatDays(result.granted_days, t) })
        : "";
      setNotice({
        text: result?.status === "approved"
          ? `${t("support.approvedNotice")}${grantText}`
          : t("support.pendingNotice"),
      });
      setSlip(null);
      setForm((f) => ({ ...f, message: "" }));
      getMyDonations().then(setMine).catch(() => {});
    } catch (err) {
      setNotice({ error: true, text: err.message || t("support.submitError") });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-amber-50 via-white to-white">
      <header className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
        <Link to={loggedIn ? "/dashboard" : "/login"} className="min-w-0"><AppBrand /></Link>
        <div className="flex items-center gap-3 sm:gap-4 text-sm whitespace-nowrap">
          <Link to="/supporters" className="text-amber-700 hover:underline font-medium">{t("support.supportersNav")}</Link>
          <button type="button" onClick={() => void navigate(loggedIn ? "/dashboard" : "/login")} className="text-blue-600 hover:underline">
            {loggedIn ? t("support.homeNav") : t("support.loginNav")}
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 pb-16">
        <section className="text-center py-8">
          <div className="text-5xl mb-3" aria-hidden="true">☕</div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">{t("pages.supportTitle")}</h1>
          <p className="mt-3 text-slate-600 max-w-2xl mx-auto leading-relaxed">
            {t("support.intro")}
            {info?.tiers?.length ? t("support.introTiers") : ""}
          </p>
        </section>

        {info === null ? (
          <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-600" /></div>
        ) : !info.enabled ? (
          <div className="max-w-xl mx-auto bg-white border border-slate-200 rounded-2xl p-8 text-center text-slate-600" data-testid="donation-disabled">
            {t("support.disabled")}
          </div>
        ) : (
          <div className="grid lg:grid-cols-5 gap-6">
            {/* QR */}
            <section className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
              <h2 className="font-bold text-slate-900 mb-3">{t("support.step1Title")}</h2>
              <div className="flex flex-wrap gap-2 mb-3">
                {PRESETS.map((p) => (
                  <button key={p} type="button" onClick={() => { setAmount(p); setCustom(""); }}
                    className={`px-4 py-2 rounded-xl border text-sm font-semibold ${custom === "" && amount === p ? "bg-amber-500 text-white border-amber-500" : "bg-white text-slate-700 border-slate-300 hover:border-amber-400"}`}>
                    ฿{p.toLocaleString(locale)}
                  </button>
                ))}
                <input type="number" min="1" max="100000" inputMode="decimal" placeholder={t("support.customPlaceholder")} value={custom}
                  onChange={(e) => setCustom(e.target.value)} aria-label={t("support.customAria")}
                  className="w-28 px-3 py-2 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400" />
              </div>
              <div className="bg-[#0e3e68] rounded-2xl p-4 text-center">
                <div className="text-white font-bold tracking-wide text-sm mb-2">PromptPay · พร้อมเพย์</div>
                <div className="bg-white rounded-xl p-3 inline-block">
                  {validAmount ? (
                    <img src={donationQrUrl(value)} alt={t("support.qrAlt", { amount: value })} className="w-56 h-56" data-testid="donation-qr" />
                  ) : (
                    <div className="w-56 h-56 flex items-center justify-center text-sm text-slate-400">{t("support.invalidAmountHint")}</div>
                  )}
                </div>
                <div className="text-white mt-3 text-lg font-bold">{validAmount ? `฿${value.toLocaleString(locale, { minimumFractionDigits: 2 })}` : ""}</div>
                <div className="text-sky-100 text-sm">{info.receiver_name}{info.receiver_name ? " · " : ""}{info.promptpay_masked}</div>
              </div>
              <p className="text-xs text-slate-500 mt-3 leading-relaxed">{t("support.qrNote")}</p>
              {perk && (
                <p className="mt-3 text-sm bg-emerald-50 text-emerald-800 rounded-xl px-3 py-2" data-testid="donation-perk">
                  {t("support.perkPrefix")} <b>{perk.plan.toUpperCase()}</b> {formatDays(perk.days, t)}{" "}
                  {t("support.perkDetails", { storage: formatStorage(perk.max_storage_mb, locale), sessions: perk.max_sessions })}
                </p>
              )}
            </section>

            <div className="lg:col-span-3 space-y-6">
              {/* ระดับสิทธิ์ */}
              {info.tiers.length > 0 && (
                <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                  <h2 className="font-bold text-slate-900 mb-1">{t("support.tiersTitle")}</h2>
                  <p className="text-sm text-slate-500 mb-4">
                    {t("support.tiersSubtitle", {
                      storage: formatStorage(info.free_plan?.max_storage_mb, locale),
                      sessions: info.free_plan?.max_sessions,
                    })}
                  </p>
                  <div className="grid sm:grid-cols-3 gap-3">
                    {info.tiers.map((tier) => (
                      <div key={`${tier.min_amount}-${tier.plan}-${tier.days}`} className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
                        <div className="text-xs text-amber-700 font-semibold">{t("support.tierFrom", { amount: tier.min_amount.toLocaleString(locale) })}</div>
                        <div className="text-lg font-extrabold text-slate-900 mt-1">{tier.plan.toUpperCase()} {formatDays(tier.days, t)}</div>
                        <ul className="text-sm text-slate-600 mt-2 space-y-0.5">
                          <li>{t("support.tierStorage", { storage: formatStorage(tier.max_storage_mb, locale) })}</li>
                          <li>{t("support.tierSessions", { sessions: tier.max_sessions })}</li>
                        </ul>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* แจ้งโอน */}
              <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                <h2 className="font-bold text-slate-900 mb-1">{info.tiers.length ? t("support.step2WithTiers") : t("support.step2NoTiers")}</h2>
                {!loggedIn ? (
                  <p className="text-sm text-slate-600 mt-2">
                    <Link to="/login" className="text-blue-600 underline">{t("support.loginNav")}</Link> {t("support.loginPromptTail")}
                  </p>
                ) : (
                  <form onSubmit={(e) => void submit(e)} className="mt-3 space-y-3" data-testid="donation-form">
                    <div className="grid sm:grid-cols-2 gap-3">
                      <label className="text-sm text-slate-700">{t("support.amountLabel")}
                        <input type="text" readOnly value={validAmount ? value.toLocaleString(locale, { minimumFractionDigits: 2 }) : "-"}
                          className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50" />
                      </label>
                      <label className="text-sm text-slate-700">{t("support.transferredAtLabel")}
                        <input type="datetime-local" required value={form.when} max={localNow()}
                          onChange={(e) => setForm({ ...form, when: e.target.value })}
                          className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300" />
                      </label>
                    </div>
                    <label className="block text-sm text-slate-700">{t("support.slipLabel")}
                      <input type="file" accept="image/*" onChange={(e) => setSlip(e.target.files?.[0] || null)}
                        className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100" />
                    </label>
                    <fieldset className="border border-slate-200 rounded-xl p-3">
                      <legend className="text-sm font-medium text-slate-700 px-1">{t("support.boardLegend")}</legend>
                      <label className="flex items-center gap-2 text-sm text-slate-700">
                        <input type="checkbox" checked={form.showOnBoard} onChange={(e) => setForm({ ...form, showOnBoard: e.target.checked })} />
                        {t("support.showOnBoard")}
                      </label>
                      {form.showOnBoard && (
                        <div className="mt-2 space-y-2 pl-6">
                          <div className="flex flex-wrap gap-4 text-sm text-slate-700">
                            <label className="flex items-center gap-1.5">
                              <input type="radio" name="namemode" checked={!form.anonymous} onChange={() => setForm({ ...form, anonymous: false })} /> {t("support.showName")}
                            </label>
                            <label className="flex items-center gap-1.5">
                              <input type="radio" name="namemode" checked={form.anonymous} onChange={() => setForm({ ...form, anonymous: true })} /> {t("support.anonymous")}
                            </label>
                          </div>
                          {!form.anonymous && (
                            <input type="text" maxLength={80} placeholder={t("support.displayNamePlaceholder")} value={form.displayName}
                              onChange={(e) => setForm({ ...form, displayName: e.target.value })} aria-label={t("support.displayNameAria")}
                              className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                          )}
                          <input type="text" maxLength={200} placeholder={t("support.messagePlaceholder")} value={form.message}
                            onChange={(e) => setForm({ ...form, message: e.target.value })} aria-label={t("support.messageAria")}
                            className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                        </div>
                      )}
                      <p className="text-xs text-slate-400 mt-2">{t("support.privacyNote")}</p>
                    </fieldset>
                    {notice && (
                      <p className={`text-sm rounded-lg px-3 py-2 ${notice.error ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-800"}`} data-testid="donation-notice">{notice.text}</p>
                    )}
                    <button type="submit" disabled={sending || !validAmount}
                      className="w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold">
                      {sending ? t("support.submitting") : t("support.submitBtn")}
                    </button>
                  </form>
                )}
              </section>

              {mine?.items?.length > 0 && (
                <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6" data-testid="donation-history">
                  <h2 className="font-bold text-slate-900 mb-3">{t("support.historyTitle")}</h2>
                  {mine.plan !== "free" && mine.expire_date && (
                    <p className="text-sm text-emerald-700 mb-3">
                      {t("support.planValidUntil", {
                        plan: mine.plan.toUpperCase(),
                        date: new Date(mine.expire_date).toLocaleDateString(locale, { dateStyle: "long" }),
                      })}
                    </p>
                  )}
                  <ul className="divide-y divide-slate-100 text-sm">
                    {mine.items.map((d) => (
                      <li key={d.id} className="py-2 flex flex-wrap items-center justify-between gap-2">
                        <span>฿{d.amount.toLocaleString(locale, { minimumFractionDigits: 2 })} · {new Date(d.transferred_at).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })}</span>
                        <span className="flex items-center gap-2">
                          {d.granted_plan && <span className="text-xs text-emerald-700">{d.granted_plan.toUpperCase()} {formatDays(d.granted_days, t)}</span>}
                          <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_CLS[d.status] || ""}`}>{STATUS_KEY[d.status] ? t(STATUS_KEY[d.status]) : d.status}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
