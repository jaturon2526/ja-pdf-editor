// หน้าแอดมิน › รับบริจาค: ตั้งเลขพร้อมเพย์/ระดับสิทธิ์ · ตรวจรายการแจ้งโอน (ดูสลิป → อนุมัติ/ปฏิเสธ) · ซ่อนจากรายชื่อ
// เลขพร้อมเพย์เก็บในฐานข้อมูลของเครื่องนี้ (ไม่อยู่ในซอร์ส/.env) · ปิดเป็นค่าเริ่มต้น
import React, { useCallback, useEffect, useState } from "react";
import {
  approveDonation, getAdminDonations, getDonationConfig, getDonationSlipUrl, rejectDonation,
  saveDonationConfig, setDonationOnBoard, verifyDonation,
} from "../../api/donations.js";
import { useI18n } from "../../i18n/I18nContext.jsx";

const VERIFY = {
  verified: { key: "admin.donations.verifyVerified", cls: "bg-emerald-100 text-emerald-800" },
  mismatch: { key: "admin.donations.verifyMismatch", cls: "bg-red-100 text-red-700" },
  retry: { key: "admin.donations.verifyRetry", cls: "bg-amber-100 text-amber-800" },
  error: { key: "admin.donations.verifyError", cls: "bg-gray-200 text-gray-700" },
  unreadable: { key: "admin.donations.verifyUnreadable", cls: "bg-gray-100 text-gray-600" },
};

const EMPTY_TIER = { min_amount: 100, plan: "pro", days: 30 };

function money(v, locale) {
  return `฿${Number(v).toLocaleString(locale, { minimumFractionDigits: 2 })}`;
}

export default function DonationsPanel() {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState(null);
  const [saved, setSaved] = useState("");
  const [status, setStatus] = useState("pending");
  const [data, setData] = useState({ items: [], pending: 0 });
  const [slip, setSlip] = useState(null);
  const [newKey, setNewKey] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    getAdminDonations(status).then(setData).catch((e) => setError(e.message));
  }, [status]);

  useEffect(() => {
    getDonationConfig().then(setConfig).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => () => { if (slip?.url) URL.revokeObjectURL(slip.url); }, [slip]);

  async function save() {
    setError(""); setSaved("");
    try {
      const body = { ...config };
      delete body.verify_key_set;
      if (newKey.trim()) body.verify_key = newKey.trim();
      setConfig(await saveDonationConfig(body));
      setNewKey("");
      setSaved(t("admin.donations.savedText"));
    } catch (e) { setError(e.message); }
  }

  async function act(fn) {
    setError("");
    try { await fn(); load(); } catch (e) { setError(e.message); }
  }

  async function showSlip(d) {
    try { setSlip({ id: d.id, url: await getDonationSlipUrl(d.id) }); } catch (e) { setError(e.message); }
  }

  function setTier(i, patch) {
    setConfig({ ...config, tiers: config.tiers.map((tier, k) => (k === i ? { ...tier, ...patch } : tier)) });
  }

  function boardLabel(d) {
    if (!d.show_on_board) return t("admin.donations.boardHidden");
    if (d.anonymous) return t("admin.donations.boardAnon");
    return d.display_name || t("admin.donations.boardNoName");
  }

  const filterTabs = [
    ["pending", t("admin.donations.filterPending")],
    ["approved", t("admin.donations.filterApproved")],
    ["rejected", t("admin.donations.filterRejected")],
    ["all", t("admin.donations.filterAll")],
  ];

  return (
    <section className="bg-white rounded-lg shadow-sm border border-gray-200 mb-8" data-testid="donations-panel">
      <button type="button" onClick={() => setOpen((v) => !v)} className="w-full flex items-center justify-between px-6 py-4 text-left">
        <span className="font-semibold text-gray-800">{t("admin.donations.panelTitle")}
          {config && <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${config.enabled ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>{config.enabled ? t("admin.donations.statusEnabled") : t("admin.donations.statusDisabled")}</span>}
          {data.pending > 0 && <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800" data-testid="donations-pending">{t("admin.donations.pendingBadge", { count: data.pending })}</span>}
        </span>
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && config && (
        <div className="px-6 pb-6 space-y-6">
          {error && <p className="text-sm bg-red-50 text-red-700 rounded px-3 py-2">{error}</p>}

          <div className="grid md:grid-cols-2 gap-4">
            <label className="text-sm text-gray-700">{t("admin.donations.promptpayLabel")}
              <input type="text" value={config.promptpay_id} onChange={(e) => setConfig({ ...config, promptpay_id: e.target.value })}
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label={t("admin.donations.promptpayAria")} autoComplete="off" />
            </label>
            <label className="text-sm text-gray-700">{t("admin.donations.receiverLabel")}
              <input type="text" maxLength={80} value={config.receiver_name} onChange={(e) => setConfig({ ...config, receiver_name: e.target.value })}
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label={t("admin.donations.receiverAria")} />
            </label>
          </div>
          <div>
            <div className="text-sm font-medium text-gray-700 mb-2">{t("admin.donations.tiersHeading")}</div>
            <div className="space-y-2">
              {config.tiers.map((tier, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                  {t("admin.donations.tierFrom")}<input type="number" min="1" value={tier.min_amount} onChange={(e) => setTier(i, { min_amount: Number(e.target.value) })} className="w-24 px-2 py-1 border rounded" aria-label={t("admin.donations.tierMinAria")} />
                  {t("admin.donations.tierGets")}
                  <select value={tier.plan} onChange={(e) => setTier(i, { plan: e.target.value })} className="px-2 py-1 border rounded">
                    <option value="pro">Pro</option><option value="premium">Premium</option>
                  </select>
                  <input type="number" min="1" max="3650" value={tier.days} onChange={(e) => setTier(i, { days: Number(e.target.value) })} className="w-20 px-2 py-1 border rounded" aria-label={t("admin.donations.tierDaysAria")} /> {t("admin.donations.tierDaysUnit")}
                  <button type="button" onClick={() => setConfig({ ...config, tiers: config.tiers.filter((_, k) => k !== i) })} className="text-red-600 hover:underline">{t("common.delete")}</button>
                </div>
              ))}
              <button type="button" onClick={() => setConfig({ ...config, tiers: [...config.tiers, EMPTY_TIER] })} className="text-sm text-blue-600 hover:underline">{t("admin.donations.addTierBtn")}</button>
              {config.tiers.length === 0 && <p className="text-xs text-gray-500">{t("admin.donations.noTiersHint")}</p>}
            </div>
          </div>
          <fieldset className="border border-gray-200 rounded-lg p-4" data-testid="verify-settings">
            <legend className="text-sm font-medium text-gray-700 px-1">{t("admin.donations.verifyLegend")}</legend>
            <p className="text-xs text-gray-500 mb-3">
              {t("admin.donations.verifyDesc")}
            </p>
            <div className="grid md:grid-cols-2 gap-3">
              <label className="text-sm text-gray-700">{t("admin.donations.verifyProviderLabel")}
                <select value={config.verify_provider} onChange={(e) => setConfig({ ...config, verify_provider: e.target.value })}
                  className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label={t("admin.donations.verifyProviderLabel")}>
                  <option value="none">{t("admin.donations.verifyProviderNone")}</option>
                  <option value="easyslip">EasySlip (easyslip.com)</option>
                </select>
              </label>
              {config.verify_provider !== "none" && (
                <label className="text-sm text-gray-700">API key {config.verify_key_set && <span className="text-emerald-700">{t("admin.donations.verifyKeySet")}</span>}
                  <input type="password" autoComplete="new-password" value={newKey} onChange={(e) => setNewKey(e.target.value)}
                    placeholder={config.verify_key_set ? "••••••••" : t("admin.donations.verifyKeyPh")} aria-label={t("admin.donations.verifyKeyAria")}
                    className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" />
                </label>
              )}
              {config.verify_provider !== "none" && (
                <label className="text-sm text-gray-700">{t("admin.donations.bankAccountLabel")}
                  <input type="text" value={config.verify_bank_account} onChange={(e) => setConfig({ ...config, verify_bank_account: e.target.value })}
                    className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label={t("admin.donations.bankAccountAria")} autoComplete="off" />
                </label>
              )}
              {config.verify_provider !== "none" && (
                <label className="flex items-center gap-2 text-sm text-gray-700 md:mt-6">
                  <input type="checkbox" checked={config.auto_approve} onChange={(e) => setConfig({ ...config, auto_approve: e.target.checked })} />
                  {t("admin.donations.autoApproveLabel")}
                </label>
              )}
            </div>
          </fieldset>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={config.enabled} onChange={(e) => setConfig({ ...config, enabled: e.target.checked })} data-testid="donations-enabled" />
              {t("admin.donations.enableCheckbox")}
            </label>
            <button type="button" onClick={() => void save()} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700">{t("common.saveShort")}</button>
            {saved && <span className="text-sm text-emerald-700">{saved}</span>}
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3">
              {filterTabs.map(([k, label]) => (
                <button key={k} type="button" onClick={() => setStatus(k)}
                  className={`px-3 py-1 rounded-full text-sm ${status === k ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-700"}`}>{label}</button>
              ))}
            </div>
            {data.items.length === 0 ? (
              <p className="text-sm text-gray-500">{t("admin.donations.emptyList")}</p>
            ) : (
              <ul className="divide-y divide-gray-100" data-testid="donations-list">
                {data.items.map((d) => (
                  <li key={d.id} className="py-3 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-semibold text-gray-900">{money(d.amount, locale)}
                        <span className="font-normal text-gray-500">
                          {t("admin.donations.transferredAt", { date: new Date(d.transferred_at).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }) })}
                        </span>
                      </span>
                      <span className="text-gray-500">{d.user ? `${d.user.display_name || ""} ${d.user.email}` : t("admin.donations.deletedAccount")}</span>
                    </div>
                    {(d.verify_status || d.slip_ref) && (
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        {d.verify_status && <span className={`px-2 py-0.5 rounded-full ${VERIFY[d.verify_status]?.cls}`} data-testid="verify-badge">{VERIFY[d.verify_status] ? t(VERIFY[d.verify_status].key) : d.verify_status}</span>}
                        {d.slip_ref && <span className="text-gray-500">{t("admin.donations.slipRef", { ref: d.slip_ref })}{d.slip_bank ? t("admin.donations.slipBank", { bank: d.slip_bank }) : ""}</span>}
                        {d.verify_detail?.amount != null && <span className="text-gray-500">{t("admin.donations.bankAmount", { amount: money(d.verify_detail.amount, locale) })}</span>}
                        {d.verify_detail?.sender && <span className="text-gray-500">{t("admin.donations.sender", { name: d.verify_detail.sender })}</span>}
                        {d.verify_detail?.problems?.map((p) => <span key={p} className="text-red-600">• {p}</span>)}
                      </div>
                    )}
                    <div className="text-gray-600 mt-1">
                      {t("admin.donations.boardLabel")} {boardLabel(d)}
                      {d.message && <> · “{d.message}”</>}
                      {d.granted_plan && t("admin.donations.grantedInfo", { plan: d.granted_plan, days: d.granted_days })}
                      {d.admin_note && t("admin.donations.adminNoteInfo", { note: d.admin_note })}
                    </div>
                    <div className="flex flex-wrap gap-3 mt-2">
                      {d.has_slip && <button type="button" onClick={() => void showSlip(d)} className="text-blue-600 hover:underline">{t("admin.donations.viewSlipBtn")}</button>}
                      {d.can_verify && config.verify_provider !== "none" && (
                        <button type="button" onClick={() => void act(() => verifyDonation(d.id))} className="text-blue-600 hover:underline" data-testid="donation-verify">{t("admin.donations.reverifyBtn")}</button>
                      )}
                      {d.status === "pending" && (
                        <>
                          <button type="button" onClick={() => void act(() => approveDonation(d.id))} className="text-emerald-700 font-medium hover:underline" data-testid="donation-approve">
                            {t("admin.donations.approveBtn")}{d.suggested ? t("admin.donations.approveSuggested", { plan: d.suggested.plan, days: d.suggested.days }) : ""}
                          </button>
                          {d.suggested && (
                            <button type="button" onClick={() => void act(() => approveDonation(d.id, { plan: "none" }))} className="text-gray-600 hover:underline">{t("admin.donations.approveNoPerkBtn")}</button>
                          )}
                          <button type="button" onClick={() => {
                            const note = window.prompt(t("admin.donations.rejectPrompt"), t("admin.donations.rejectDefault"));
                            if (note !== null) void act(() => rejectDonation(d.id, note));
                          }} className="text-red-600 hover:underline">{t("admin.donations.rejectBtn")}</button>
                        </>
                      )}
                      {d.status === "approved" && (
                        <button type="button" onClick={() => void act(() => setDonationOnBoard(d.id, !d.show_on_board))} className="text-gray-600 hover:underline">
                          {d.show_on_board ? t("admin.donations.hideFromBoardBtn") : t("admin.donations.showOnBoardBtn")}
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      {slip && (
        <div role="presentation" className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setSlip(null)}>
          <img src={slip.url} alt={t("admin.donations.slipAlt")} className="max-h-[90vh] max-w-full rounded-lg bg-white" />
        </div>
      )}
    </section>
  );
}
