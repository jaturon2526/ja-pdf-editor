// รายชื่อผู้สนับสนุน (สาธารณะ) — แสดงชื่อเต็มหรือ "ไม่ประสงค์ออกนาม" ตามที่ผู้สนับสนุนเลือก · ไม่แสดงยอดเงิน/อีเมล
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppBrand from "../components/AppBrand.jsx";
import { isLoggedIn } from "../api/client.js";
import { getSupporters } from "../api/donations.js";
import { useI18n } from "../i18n/I18nContext.jsx";

export default function SupportersPage() {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const [items, setItems] = useState(null);

  useEffect(() => {
    getSupporters().then((d) => setItems(d.items || [])).catch(() => setItems([]));
  }, []);

  let body;
  if (items === null) {
    body = <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-600" /></div>;
  } else if (items.length === 0) {
    body = (
      <p className="text-center text-slate-500 py-10" data-testid="supporters-empty">
        {t("support.supportersEmptyBefore")} <Link to="/support" className="text-amber-700 underline">{t("support.supportersEmptyLink")}</Link>
      </p>
    );
  } else {
    body = (
      <ul className="grid sm:grid-cols-2 gap-3" data-testid="supporters-list">
        {items.map((s, i) => (
          <li key={i} className="bg-white rounded-xl border border-amber-100 shadow-sm p-4">
            <div className="flex items-baseline justify-between gap-2">
              <span className={`font-semibold ${s.anonymous ? "text-slate-500 italic" : "text-slate-900"}`}>{s.name}</span>
              {s.date && <span className="text-xs text-slate-400 shrink-0">{new Date(s.date).toLocaleDateString(locale, { month: "short", year: "numeric" })}</span>}
            </div>
            {s.message && <p className="text-sm text-slate-600 mt-1 break-words">“{s.message}”</p>}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-amber-50 via-white to-white">
      <header className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
        <Link to={isLoggedIn() ? "/dashboard" : "/login"} className="min-w-0"><AppBrand /></Link>
        <Link to="/support" className="text-sm font-semibold text-amber-700 hover:underline">{t("support.supportersJoinBtn")}</Link>
      </header>
      <main className="max-w-4xl mx-auto px-4 pb-16">
        <section className="text-center py-8">
          <div className="text-5xl mb-3" aria-hidden="true">💛</div>
          <h1 className="text-3xl font-extrabold text-slate-900">{t("support.supportersTitle")}</h1>
          <p className="mt-2 text-slate-600">{t("support.supportersSubtitle")}</p>
        </section>
        {body}
      </main>
    </div>
  );
}
