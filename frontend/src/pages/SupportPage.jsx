// ☕ สนับสนุนผู้พัฒนา — QR พร้อมเพย์ + ระดับสิทธิ์ + แจ้งโอน + ประวัติ (แทนหน้า "อัปเกรดแพ็กเกจ" เดิม)
// เปิดดูได้โดยไม่ต้อง login · แจ้งโอนต้อง login (สิทธิ์ผูกกับบัญชี) · แอดมินตรวจยอดแล้วอนุมัติ
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AppBrand from "../components/AppBrand.jsx";
import { getToken } from "../api/client.js";
import { donationQrUrl, getDonationInfo, getMyDonations, reportDonation } from "../api/donations.js";

const PRESETS = [49, 99, 299, 499];
const STATUS = {
  pending: { label: "รอตรวจสอบ", cls: "bg-amber-100 text-amber-800" },
  approved: { label: "ได้รับแล้ว", cls: "bg-emerald-100 text-emerald-800" },
  rejected: { label: "ไม่พบยอดโอน", cls: "bg-red-100 text-red-700" },
};

function formatStorage(mb) {
  if (!mb) return "-";
  return mb >= 1024 ? `${(mb / 1024).toLocaleString("th-TH", { maximumFractionDigits: 1 })} GB` : `${mb} MB`;
}

function formatDays(days) {
  if (days % 365 === 0) return `${days / 365} ปี`;
  if (days % 30 === 0) return `${days / 30} เดือน`;
  return `${days} วัน`;
}

function localNow() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default function SupportPage() {
  const navigate = useNavigate();
  const loggedIn = Boolean(getToken());
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
    return [...info.tiers].filter((t) => value >= t.min_amount).pop() || null;
  }, [info, value, validAmount]);

  async function submit(e) {
    e.preventDefault();
    setNotice(null);
    if (!validAmount) return setNotice({ error: true, text: "ยอดเงินต้องอยู่ระหว่าง 1–100,000 บาท" });
    setSending(true);
    try {
      const result = await reportDonation({
        amount: value, transferredAt: new Date(form.when), anonymous: form.anonymous, showOnBoard: form.showOnBoard,
        displayName: form.displayName.trim(), message: form.message.trim(), slip,
      });
      setNotice({ text: result?.status === "approved"
        ? `ตรวจสลิปกับธนาคารแล้ว ขอบคุณมากครับ 🙏${result.granted_plan ? ` ได้รับสิทธิ์ ${result.granted_plan.toUpperCase()} ${formatDays(result.granted_days)} แล้ว` : ""}`
        : "ส่งข้อมูลแล้ว ขอบคุณมากครับ 🙏 ผู้ดูแลจะตรวจยอดและแจ้งผลในกระดิ่งแจ้งเตือน" });
      setSlip(null);
      setForm((f) => ({ ...f, message: "" }));
      getMyDonations().then(setMine).catch(() => {});
    } catch (err) {
      setNotice({ error: true, text: err.message || "ส่งข้อมูลไม่สำเร็จ" });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-amber-50 via-white to-white">
      <header className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
        <Link to={loggedIn ? "/dashboard" : "/login"} className="min-w-0"><AppBrand /></Link>
        <div className="flex items-center gap-3 sm:gap-4 text-sm whitespace-nowrap">
          <Link to="/supporters" className="text-amber-700 hover:underline font-medium">ผู้สนับสนุน</Link>
          <button type="button" onClick={() => navigate(loggedIn ? "/dashboard" : "/login")} className="text-blue-600 hover:underline">
            {loggedIn ? "หน้าหลัก" : "เข้าสู่ระบบ"}
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 pb-16">
        <section className="text-center py-8">
          <div className="text-5xl mb-3" aria-hidden="true">☕</div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900">สนับสนุนผู้พัฒนา</h1>
          <p className="mt-3 text-slate-600 max-w-2xl mx-auto leading-relaxed">
            JA PDF Editor ใช้ฟรีและเป็นโอเพนซอร์ส (AGPL-3.0) — เงินสนับสนุนช่วยค่าเซิร์ฟเวอร์ ค่าโดเมน และเวลาพัฒนาฟีเจอร์ใหม่
            {info?.tiers?.length ? " · ผู้สนับสนุนได้พื้นที่เก็บไฟล์และจำนวนอุปกรณ์เพิ่มเป็นการขอบคุณ" : ""}
          </p>
        </section>

        {info === null ? (
          <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-600" /></div>
        ) : !info.enabled ? (
          <div className="max-w-xl mx-auto bg-white border border-slate-200 rounded-2xl p-8 text-center text-slate-600" data-testid="donation-disabled">
            ระบบนี้ยังไม่เปิดรับการสนับสนุน — ขอบคุณที่สนใจครับ
          </div>
        ) : (
          <div className="grid lg:grid-cols-5 gap-6">
            {/* QR */}
            <section className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
              <h2 className="font-bold text-slate-900 mb-3">1. เลือกยอดแล้วสแกนด้วยแอปธนาคาร</h2>
              <div className="flex flex-wrap gap-2 mb-3">
                {PRESETS.map((p) => (
                  <button key={p} type="button" onClick={() => { setAmount(p); setCustom(""); }}
                    className={`px-4 py-2 rounded-xl border text-sm font-semibold ${custom === "" && amount === p ? "bg-amber-500 text-white border-amber-500" : "bg-white text-slate-700 border-slate-300 hover:border-amber-400"}`}>
                    ฿{p.toLocaleString("th-TH")}
                  </button>
                ))}
                <input type="number" min="1" max="100000" inputMode="decimal" placeholder="ยอดอื่น" value={custom}
                  onChange={(e) => setCustom(e.target.value)} aria-label="ยอดเงินอื่น"
                  className="w-28 px-3 py-2 rounded-xl border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400" />
              </div>
              <div className="bg-[#0e3e68] rounded-2xl p-4 text-center">
                <div className="text-white font-bold tracking-wide text-sm mb-2">PromptPay · พร้อมเพย์</div>
                <div className="bg-white rounded-xl p-3 inline-block">
                  {validAmount ? (
                    <img src={donationQrUrl(value)} alt={`QR พร้อมเพย์ ${value} บาท`} className="w-56 h-56" data-testid="donation-qr" />
                  ) : (
                    <div className="w-56 h-56 flex items-center justify-center text-sm text-slate-400">ใส่ยอด 1–100,000 บาท</div>
                  )}
                </div>
                <div className="text-white mt-3 text-lg font-bold">{validAmount ? `฿${value.toLocaleString("th-TH", { minimumFractionDigits: 2 })}` : ""}</div>
                <div className="text-sky-100 text-sm">{info.receiver_name}{info.receiver_name ? " · " : ""}{info.promptpay_masked}</div>
              </div>
              <p className="text-xs text-slate-500 mt-3 leading-relaxed">ตรวจชื่อผู้รับในแอปธนาคารก่อนยืนยันทุกครั้ง · QR นี้สร้างจากเลขพร้อมเพย์ที่ผู้ดูแลระบบตั้งไว้</p>
              {perk && (
                <p className="mt-3 text-sm bg-emerald-50 text-emerald-800 rounded-xl px-3 py-2" data-testid="donation-perk">
                  ยอดนี้ได้สิทธิ์ <b>{perk.plan.toUpperCase()}</b> {formatDays(perk.days)} — พื้นที่ {formatStorage(perk.max_storage_mb)}, ใช้ได้ {perk.max_sessions} อุปกรณ์
                </p>
              )}
            </section>

            <div className="lg:col-span-3 space-y-6">
              {/* ระดับสิทธิ์ */}
              {info.tiers.length > 0 && (
                <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                  <h2 className="font-bold text-slate-900 mb-1">สิทธิ์ขอบคุณผู้สนับสนุน</h2>
                  <p className="text-sm text-slate-500 mb-4">
                    บัญชีทั่วไปใช้ทุกเครื่องมือได้ฟรี (พื้นที่ {formatStorage(info.free_plan?.max_storage_mb)}, {info.free_plan?.max_sessions} อุปกรณ์) · สิทธิ์คิดตามยอดต่อครั้ง ได้ระดับเดิมซ้ำจะต่อเวลาให้
                  </p>
                  <div className="grid sm:grid-cols-3 gap-3">
                    {info.tiers.map((t) => (
                      <div key={`${t.min_amount}-${t.plan}-${t.days}`} className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
                        <div className="text-xs text-amber-700 font-semibold">ตั้งแต่ ฿{t.min_amount.toLocaleString("th-TH")}</div>
                        <div className="text-lg font-extrabold text-slate-900 mt-1">{t.plan.toUpperCase()} {formatDays(t.days)}</div>
                        <ul className="text-sm text-slate-600 mt-2 space-y-0.5">
                          <li>พื้นที่ {formatStorage(t.max_storage_mb)}</li>
                          <li>ใช้พร้อมกัน {t.max_sessions} อุปกรณ์</li>
                        </ul>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* แจ้งโอน */}
              <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6">
                <h2 className="font-bold text-slate-900 mb-1">2. แจ้งโอน{info.tiers.length ? "เพื่อรับสิทธิ์และขึ้นรายชื่อ" : "เพื่อขึ้นรายชื่อผู้สนับสนุน"}</h2>
                {!loggedIn ? (
                  <p className="text-sm text-slate-600 mt-2">
                    <Link to="/login" className="text-blue-600 underline">เข้าสู่ระบบ</Link> เพื่อแจ้งโอน — ไม่แจ้งก็ได้ ขอบคุณทุกการสนับสนุนครับ
                  </p>
                ) : (
                  <form onSubmit={submit} className="mt-3 space-y-3" data-testid="donation-form">
                    <div className="grid sm:grid-cols-2 gap-3">
                      <label className="text-sm text-slate-700">ยอดที่โอน (บาท)
                        <input type="text" readOnly value={validAmount ? value.toLocaleString("th-TH", { minimumFractionDigits: 2 }) : "-"}
                          className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50" />
                      </label>
                      <label className="text-sm text-slate-700">วันเวลาที่โอน
                        <input type="datetime-local" required value={form.when} max={localNow()}
                          onChange={(e) => setForm({ ...form, when: e.target.value })}
                          className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300" />
                      </label>
                    </div>
                    <label className="block text-sm text-slate-700">สลิป (ไม่บังคับ แต่แนะนำ — ระบบอ่าน QR ในสลิปเพื่อตรวจยอด และลบรูปสลิปทันทีที่ตรวจเสร็จ)
                      <input type="file" accept="image/*" onChange={(e) => setSlip(e.target.files?.[0] || null)}
                        className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100" />
                    </label>
                    <fieldset className="border border-slate-200 rounded-xl p-3">
                      <legend className="text-sm font-medium text-slate-700 px-1">รายชื่อผู้สนับสนุน</legend>
                      <label className="flex items-center gap-2 text-sm text-slate-700">
                        <input type="checkbox" checked={form.showOnBoard} onChange={(e) => setForm({ ...form, showOnBoard: e.target.checked })} />
                        แสดงในหน้ารายชื่อผู้สนับสนุน
                      </label>
                      {form.showOnBoard && (
                        <div className="mt-2 space-y-2 pl-6">
                          <div className="flex flex-wrap gap-4 text-sm text-slate-700">
                            <label className="flex items-center gap-1.5">
                              <input type="radio" name="namemode" checked={!form.anonymous} onChange={() => setForm({ ...form, anonymous: false })} /> แสดงชื่อ
                            </label>
                            <label className="flex items-center gap-1.5">
                              <input type="radio" name="namemode" checked={form.anonymous} onChange={() => setForm({ ...form, anonymous: true })} /> ไม่ประสงค์ออกนาม
                            </label>
                          </div>
                          {!form.anonymous && (
                            <input type="text" maxLength={80} placeholder="ชื่อที่จะแสดง (เว้นว่าง = ชื่อในโปรไฟล์)" value={form.displayName}
                              onChange={(e) => setForm({ ...form, displayName: e.target.value })} aria-label="ชื่อที่จะแสดง"
                              className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                          )}
                          <input type="text" maxLength={200} placeholder="ข้อความถึงผู้พัฒนา (ไม่บังคับ)" value={form.message}
                            onChange={(e) => setForm({ ...form, message: e.target.value })} aria-label="ข้อความ"
                            className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm" />
                        </div>
                      )}
                      <p className="text-xs text-slate-400 mt-2">ไม่แสดงยอดเงินและอีเมลในหน้ารายชื่อ</p>
                    </fieldset>
                    {notice && (
                      <p className={`text-sm rounded-lg px-3 py-2 ${notice.error ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-800"}`} data-testid="donation-notice">{notice.text}</p>
                    )}
                    <button type="submit" disabled={sending || !validAmount}
                      className="w-full py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold">
                      {sending ? "กำลังส่ง…" : "แจ้งโอนแล้ว"}
                    </button>
                  </form>
                )}
              </section>

              {mine?.items?.length > 0 && (
                <section className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6" data-testid="donation-history">
                  <h2 className="font-bold text-slate-900 mb-3">การสนับสนุนของฉัน</h2>
                  {mine.plan !== "free" && mine.expire_date && (
                    <p className="text-sm text-emerald-700 mb-3">สิทธิ์ {mine.plan.toUpperCase()} ใช้ได้ถึง {new Date(mine.expire_date).toLocaleDateString("th-TH", { dateStyle: "long" })}</p>
                  )}
                  <ul className="divide-y divide-slate-100 text-sm">
                    {mine.items.map((d) => (
                      <li key={d.id} className="py-2 flex flex-wrap items-center justify-between gap-2">
                        <span>฿{d.amount.toLocaleString("th-TH", { minimumFractionDigits: 2 })} · {new Date(d.transferred_at).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" })}</span>
                        <span className="flex items-center gap-2">
                          {d.granted_plan && <span className="text-xs text-emerald-700">{d.granted_plan.toUpperCase()} {formatDays(d.granted_days)}</span>}
                          <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS[d.status]?.cls}`}>{STATUS[d.status]?.label}</span>
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
