// หน้าแอดมิน › รับบริจาค: ตั้งเลขพร้อมเพย์/ระดับสิทธิ์ · ตรวจรายการแจ้งโอน (ดูสลิป → อนุมัติ/ปฏิเสธ) · ซ่อนจากรายชื่อ
// เลขพร้อมเพย์เก็บในฐานข้อมูลของเครื่องนี้ (ไม่อยู่ในซอร์ส/.env) · ปิดเป็นค่าเริ่มต้น
import React, { useCallback, useEffect, useState } from "react";
import {
  approveDonation, getAdminDonations, getDonationConfig, getDonationSlipUrl, rejectDonation,
  saveDonationConfig, setDonationOnBoard, verifyDonation,
} from "../../api/donations.js";

const VERIFY = {
  verified: { label: "ตรวจกับธนาคารแล้ว ✓", cls: "bg-emerald-100 text-emerald-800" },
  mismatch: { label: "ตรวจแล้วไม่ตรง", cls: "bg-red-100 text-red-700" },
  retry: { label: "กำลังลองตรวจใหม่อัตโนมัติ", cls: "bg-amber-100 text-amber-800" },
  error: { label: "ตรวจอัตโนมัติไม่ได้ — ตรวจเอง", cls: "bg-gray-200 text-gray-700" },
  unreadable: { label: "อ่าน QR ในสลิปไม่ได้", cls: "bg-gray-100 text-gray-600" },
};

const EMPTY_TIER = { min_amount: 100, plan: "pro", days: 30 };

function money(v) {
  return `฿${Number(v).toLocaleString("th-TH", { minimumFractionDigits: 2 })}`;
}

export default function DonationsPanel() {
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
      setSaved("บันทึกแล้ว");
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
    setConfig({ ...config, tiers: config.tiers.map((t, k) => (k === i ? { ...t, ...patch } : t)) });
  }

  return (
    <section className="bg-white rounded-lg shadow-sm border border-gray-200 mb-8" data-testid="donations-panel">
      <button type="button" onClick={() => setOpen((v) => !v)} className="w-full flex items-center justify-between px-6 py-4 text-left">
        <span className="font-semibold text-gray-800">☕ รับบริจาค (PromptPay)
          {config && <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${config.enabled ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-500"}`}>{config.enabled ? "เปิดอยู่" : "ปิด"}</span>}
          {data.pending > 0 && <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800" data-testid="donations-pending">รอตรวจ {data.pending}</span>}
        </span>
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && config && (
        <div className="px-6 pb-6 space-y-6">
          {error && <p className="text-sm bg-red-50 text-red-700 rounded px-3 py-2">{error}</p>}

          <div className="grid md:grid-cols-2 gap-4">
            <label className="text-sm text-gray-700">เลขพร้อมเพย์ (มือถือ 10 หลัก / บัตรประชาชน-ผู้เสียภาษี 13 หลัก / e-Wallet 15 หลัก)
              <input type="text" value={config.promptpay_id} onChange={(e) => setConfig({ ...config, promptpay_id: e.target.value })}
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label="เลขพร้อมเพย์" autoComplete="off" />
            </label>
            <label className="text-sm text-gray-700">ชื่อผู้รับที่แสดงใต้ QR (ให้ตรงกับชื่อที่แอปธนาคารแสดง)
              <input type="text" maxLength={80} value={config.receiver_name} onChange={(e) => setConfig({ ...config, receiver_name: e.target.value })}
                className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label="ชื่อผู้รับ" />
            </label>
          </div>
          <div>
            <div className="text-sm font-medium text-gray-700 mb-2">ระดับสิทธิ์ผู้สนับสนุน (ยอดต่อครั้ง → แพ็กเกจชั่วคราว · พื้นที่/อุปกรณ์ตั้งในตารางแพ็กเกจด้านล่าง)</div>
            <div className="space-y-2">
              {config.tiers.map((t, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                  ตั้งแต่ ฿<input type="number" min="1" value={t.min_amount} onChange={(e) => setTier(i, { min_amount: Number(e.target.value) })} className="w-24 px-2 py-1 border rounded" aria-label="ยอดขั้นต่ำ" />
                  ได้
                  <select value={t.plan} onChange={(e) => setTier(i, { plan: e.target.value })} className="px-2 py-1 border rounded">
                    <option value="pro">Pro</option><option value="premium">Premium</option>
                  </select>
                  <input type="number" min="1" max="3650" value={t.days} onChange={(e) => setTier(i, { days: Number(e.target.value) })} className="w-20 px-2 py-1 border rounded" aria-label="จำนวนวัน" /> วัน
                  <button type="button" onClick={() => setConfig({ ...config, tiers: config.tiers.filter((_, k) => k !== i) })} className="text-red-600 hover:underline">ลบ</button>
                </div>
              ))}
              <button type="button" onClick={() => setConfig({ ...config, tiers: [...config.tiers, EMPTY_TIER] })} className="text-sm text-blue-600 hover:underline">+ เพิ่มระดับ</button>
              {config.tiers.length === 0 && <p className="text-xs text-gray-500">ไม่มีระดับ = รับบริจาคอย่างเดียว ไม่ให้สิทธิ์</p>}
            </div>
          </div>
          <fieldset className="border border-gray-200 rounded-lg p-4" data-testid="verify-settings">
            <legend className="text-sm font-medium text-gray-700 px-1">ตรวจสลิปอัตโนมัติ</legend>
            <p className="text-xs text-gray-500 mb-3">
              ระบบอ่าน QR ในสลิปเองเสมอ (กันสลิปเดิมแจ้งซ้ำ + แสดงเลขอ้างอิงให้เทียบกับแอปธนาคาร) แต่ QR ไม่มียอดเงิน —
              ถ้าต้องการยืนยันยอด/ผู้รับกับธนาคารและอนุมัติอัตโนมัติ ให้ต่อบริการตรวจสลิป (เสียค่าบริการตามแพ็กเกจของผู้ให้บริการ · ส่งเฉพาะข้อความใน QR ไม่ส่งรูปสลิป)
            </p>
            <div className="grid md:grid-cols-2 gap-3">
              <label className="text-sm text-gray-700">บริการตรวจสลิป
                <select value={config.verify_provider} onChange={(e) => setConfig({ ...config, verify_provider: e.target.value })}
                  className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label="บริการตรวจสลิป">
                  <option value="none">ไม่ใช้ (แอดมินตรวจเอง)</option>
                  <option value="easyslip">EasySlip (easyslip.com)</option>
                </select>
              </label>
              {config.verify_provider !== "none" && (
                <label className="text-sm text-gray-700">API key {config.verify_key_set && <span className="text-emerald-700">(ตั้งไว้แล้ว — เว้นว่าง = ใช้ค่าเดิม)</span>}
                  <input type="password" autoComplete="new-password" value={newKey} onChange={(e) => setNewKey(e.target.value)}
                    placeholder={config.verify_key_set ? "••••••••" : "วาง API key"} aria-label="API key ตรวจสลิป"
                    className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" />
                </label>
              )}
              {config.verify_provider !== "none" && (
                <label className="text-sm text-gray-700">เลขบัญชีธนาคารที่ผูกพร้อมเพย์ (ไม่บังคับ — ใช้เทียบเมื่อสลิปแสดงเลขบัญชีแทนเบอร์)
                  <input type="text" value={config.verify_bank_account} onChange={(e) => setConfig({ ...config, verify_bank_account: e.target.value })}
                    className="mt-1 w-full px-3 py-2 border border-gray-300 rounded-lg" aria-label="เลขบัญชีธนาคาร" autoComplete="off" />
                </label>
              )}
              {config.verify_provider !== "none" && (
                <label className="flex items-center gap-2 text-sm text-gray-700 md:mt-6">
                  <input type="checkbox" checked={config.auto_approve} onChange={(e) => setConfig({ ...config, auto_approve: e.target.checked })} />
                  อนุมัติ + ให้สิทธิ์อัตโนมัติเมื่อตรวจผ่านทุกข้อ (ยอด ≥ ที่แจ้ง · ผู้รับเป็นบัญชีนี้ · วันที่ตรง · ไม่ซ้ำ)
                </label>
              )}
            </div>
          </fieldset>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={config.enabled} onChange={(e) => setConfig({ ...config, enabled: e.target.checked })} data-testid="donations-enabled" />
              เปิดรับบริจาค (แสดงเมนู ☕ และหน้า /support)
            </label>
            <button type="button" onClick={save} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700">บันทึก</button>
            {saved && <span className="text-sm text-emerald-700">{saved}</span>}
          </div>

          <div>
            <div className="flex items-center gap-2 mb-3">
              {[["pending", "รอตรวจ"], ["approved", "อนุมัติแล้ว"], ["rejected", "ปฏิเสธ"], ["all", "ทั้งหมด"]].map(([k, label]) => (
                <button key={k} type="button" onClick={() => setStatus(k)}
                  className={`px-3 py-1 rounded-full text-sm ${status === k ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-700"}`}>{label}</button>
              ))}
            </div>
            {data.items.length === 0 ? (
              <p className="text-sm text-gray-500">ไม่มีรายการ</p>
            ) : (
              <ul className="divide-y divide-gray-100" data-testid="donations-list">
                {data.items.map((d) => (
                  <li key={d.id} className="py-3 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-semibold text-gray-900">{money(d.amount)}
                        <span className="font-normal text-gray-500"> · โอน {new Date(d.transferred_at).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" })}</span>
                      </span>
                      <span className="text-gray-500">{d.user ? `${d.user.display_name || ""} ${d.user.email}` : "(ลบบัญชีแล้ว)"}</span>
                    </div>
                    {(d.verify_status || d.slip_ref) && (
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                        {d.verify_status && <span className={`px-2 py-0.5 rounded-full ${VERIFY[d.verify_status]?.cls}`} data-testid="verify-badge">{VERIFY[d.verify_status]?.label}</span>}
                        {d.slip_ref && <span className="text-gray-500">เลขอ้างอิง {d.slip_ref}{d.slip_bank ? ` · ธนาคาร ${d.slip_bank}` : ""}</span>}
                        {d.verify_detail?.amount != null && <span className="text-gray-500">ยอดจากธนาคาร {money(d.verify_detail.amount)}</span>}
                        {d.verify_detail?.sender && <span className="text-gray-500">ผู้โอน {d.verify_detail.sender}</span>}
                        {d.verify_detail?.problems?.map((p) => <span key={p} className="text-red-600">• {p}</span>)}
                      </div>
                    )}
                    <div className="text-gray-600 mt-1">
                      รายชื่อ: {d.show_on_board ? (d.anonymous ? "ไม่ประสงค์ออกนาม" : (d.display_name || "(ไม่มีชื่อ)")) : "ไม่แสดง"}
                      {d.message && <> · “{d.message}”</>}
                      {d.granted_plan && <> · ให้สิทธิ์ {d.granted_plan} {d.granted_days} วัน</>}
                      {d.admin_note && <> · หมายเหตุ: {d.admin_note}</>}
                    </div>
                    <div className="flex flex-wrap gap-3 mt-2">
                      {d.has_slip && <button type="button" onClick={() => showSlip(d)} className="text-blue-600 hover:underline">ดูสลิป</button>}
                      {d.can_verify && config.verify_provider !== "none" && (
                        <button type="button" onClick={() => act(() => verifyDonation(d.id))} className="text-blue-600 hover:underline" data-testid="donation-verify">ตรวจสลิปอีกครั้ง</button>
                      )}
                      {d.status === "pending" && (
                        <>
                          <button type="button" onClick={() => act(() => approveDonation(d.id))} className="text-emerald-700 font-medium hover:underline" data-testid="donation-approve">
                            อนุมัติ{d.suggested ? ` (${d.suggested.plan} ${d.suggested.days} วัน)` : ""}
                          </button>
                          {d.suggested && (
                            <button type="button" onClick={() => act(() => approveDonation(d.id, { plan: "none" }))} className="text-gray-600 hover:underline">อนุมัติโดยไม่ให้สิทธิ์</button>
                          )}
                          <button type="button" onClick={() => {
                            const note = window.prompt("เหตุผล (ผู้แจ้งจะเห็น) เช่น ไม่พบยอดเข้า", "ไม่พบยอดเข้าบัญชี");
                            if (note !== null) act(() => rejectDonation(d.id, note));
                          }} className="text-red-600 hover:underline">ปฏิเสธ</button>
                        </>
                      )}
                      {d.status === "approved" && (
                        <button type="button" onClick={() => act(() => setDonationOnBoard(d.id, !d.show_on_board))} className="text-gray-600 hover:underline">
                          {d.show_on_board ? "ซ่อนจากรายชื่อ" : "แสดงในรายชื่อ"}
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
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setSlip(null)}>
          <img src={slip.url} alt="สลิป" className="max-h-[90vh] max-w-full rounded-lg bg-white" />
        </div>
      )}
    </section>
  );
}
