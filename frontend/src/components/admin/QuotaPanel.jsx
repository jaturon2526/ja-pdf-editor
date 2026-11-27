// โควต้า/เครดิตของบริการภายนอก (LINE, อีเมล Brevo, Gemini, ดิสก์, ฐานข้อมูล) + กราฟการใช้ 30 วัน — หน้า Admin
// backend: GET /admin/quotas (ดู services/quota_service.py)
import { useEffect, useMemo, useState } from "react";
import { getAdminQuotas } from "../../api";
import { useI18n } from "../../i18n/I18nContext.jsx";

function fmt(value, unit, locale) {
  if (value === null || value === undefined) return "-";
  if (unit === "bytes") {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = value;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return `${i === 0 ? v : v.toFixed(1)} ${units[i]}`;
  }
  return `${Number(value).toLocaleString(locale)} ${unit}`;
}

const fmtDate = (iso, locale) =>
  iso ? new Date(iso).toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : null;

const STATUS = {
  ok: { bar: "bg-emerald-500", badge: "bg-emerald-100 text-emerald-800", key: "admin.quota.statusOk" },
  warn: { bar: "bg-amber-500", badge: "bg-amber-100 text-amber-800", key: "admin.quota.statusWarn" },
  full: { bar: "bg-red-500", badge: "bg-red-100 text-red-800", key: "admin.quota.statusFull" },
  error: { bar: "bg-gray-400", badge: "bg-red-100 text-red-800", key: "admin.quota.statusError" },
  info: { bar: "bg-blue-400", badge: "bg-slate-100 text-slate-700", key: "admin.quota.statusInfo" },
};

const SOURCE_KEY = { api: "admin.quota.sourceApi", internal: "admin.quota.sourceInternal", system: "admin.quota.sourceSystem" };
const PERIOD_KEY = { day: "admin.quota.periodDay", month: "admin.quota.periodMonth", plan: "admin.quota.periodPlan" };

function QuotaCard({ item }) {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const st = STATUS[item.status] || STATUS.info;
  const pct = item.percent ?? null;
  const periodLabel = PERIOD_KEY[item.period] ? t(PERIOD_KEY[item.period]) : "";
  const sourceLabel = SOURCE_KEY[item.source] ? t(SOURCE_KEY[item.source]) : "";
  return (
    <div className="bg-white p-5 rounded-lg shadow-sm border border-gray-200 flex flex-col" data-testid={`quota-${item.key}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <div className="font-semibold text-gray-900">{item.name}</div>
          <div className="text-xs text-gray-500">
            {[periodLabel, sourceLabel].filter(Boolean).join(" · ")}
          </div>
        </div>
        <span className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${st.badge}`}>{item.status_label || t(st.key)}</span>
      </div>

      {item.limit ? (
        <>
          <div className="flex items-end justify-between gap-2 mt-1">
            <span className="text-2xl font-bold text-gray-900">{fmt(item.used, item.unit, locale)}</span>
            <span className="text-sm text-gray-500 mb-0.5">{t("admin.quota.ofLimit", { limit: fmt(item.limit, item.unit, locale) })}</span>
          </div>
          <div
            className="mt-2 h-2.5 rounded-full bg-gray-100 overflow-hidden"
            role="progressbar"
            aria-label={t("admin.quota.usedAria", { name: item.name, pct: pct ?? 0 })}
            aria-valuenow={Math.min(100, pct ?? 0)}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className={`h-full ${st.bar}`} style={{ width: `${Math.min(100, pct ?? 0)}%` }} />
          </div>
          <div className="mt-1.5 flex justify-between text-xs text-gray-600">
            <span>{t("admin.quota.usedPercent", { pct: pct ?? 0 })}</span>
            <span>{t("admin.quota.remaining", { val: fmt(item.remaining, item.unit, locale) })}</span>
          </div>
        </>
      ) : (
        <div className="mt-1">
          <span className="text-2xl font-bold text-gray-900">
            {item.used !== null && item.used !== undefined ? fmt(item.used, item.unit, locale) : fmt(item.remaining, item.unit, locale)}
          </span>
          {item.remaining !== null && item.remaining !== undefined && item.used !== null && item.used !== undefined && (
            <span className="ml-2 text-sm text-gray-500">{t("admin.quota.remaining", { val: fmt(item.remaining, item.unit, locale) })}</span>
          )}
        </div>
      )}

      {item.error && <p className="mt-2 text-xs text-red-700 bg-red-50 rounded p-2">{item.error}</p>}
      {item.note && <p className="mt-2 text-xs text-gray-500">{item.note}</p>}
      <div className="mt-auto pt-3 flex items-center justify-between text-xs text-gray-500">
        <span>{item.resets_at ? t("admin.quota.resetsAt", { date: fmtDate(item.resets_at, locale) }) : ""}</span>
        {item.link && (
          <a href={item.link} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
            {t("admin.quota.openConsole")}
          </a>
        )}
      </div>
    </div>
  );
}

// available: แท็บที่ backend บอกว่าเปิดใช้ (ไม่ได้ตั้ง SMTP / ปิด LINE = ไม่แสดงแท็บนั้น)
function UsageChart({ history, available }) {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const [series, setSeries] = useState("ai");
  const allSeries = [
    { key: "ai", label: "AI", unit: t("admin.quota.seriesAiUnit"), color: "#16a34a" },
    { key: "email", label: t("admin.quota.seriesEmailLabel"), unit: t("admin.quota.seriesEmailUnit"), color: "#2563eb" },
    { key: "line", label: "LINE", unit: t("admin.quota.seriesLineUnit"), color: "#06C755" },
  ];
  const tabs = available?.length ? allSeries.filter((x) => available.includes(x.key)) : allSeries;
  const s = tabs.find((x) => x.key === series) || tabs[0];
  const values = history.map((d) => d[s.key] || 0);
  const peak = Math.max(0, ...values);
  const max = Math.max(1, peak);
  const total = values.reduce((a, b) => a + b, 0);
  const W = 600;
  const H = 140;
  const gap = 2;
  const bw = W / Math.max(1, history.length) - gap;
  const short = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(locale, { day: "numeric", month: "short" });

  return (
    <div className="bg-white p-5 rounded-lg shadow-sm border border-gray-200" data-testid="quota-chart">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div>
          <div className="font-semibold text-gray-900">{t("admin.quota.chartTitle")}</div>
          <div className="text-xs text-gray-500">
            {t("admin.quota.chartSummary", { total: total.toLocaleString(locale), peak: peak.toLocaleString(locale), unit: s.unit })}
          </div>
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1" role="tablist" aria-label={t("admin.quota.chartSelectAria")}>
          {tabs.map((x) => (
            <button
              key={x.key}
              type="button"
              role="tab"
              aria-selected={s.key === x.key}
              onClick={() => setSeries(x.key)}
              className={`px-3 py-1 rounded-md text-sm ${s.key === x.key ? "bg-white shadow-sm font-medium text-gray-900" : "text-gray-600"}`}
            >
              {x.label}
            </button>
          ))}
        </div>
      </div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="w-full h-36"
          role="img"
          aria-label={t("admin.quota.chartAria", { label: s.label, total, unit: s.unit })}
        >
          <line x1="0" y1={H - 0.5} x2={W} y2={H - 0.5} stroke="#e5e7eb" />
          {history.map((d, i) => {
            const v = d[s.key] || 0;
            const h = v ? Math.max(2, (v / max) * (H - 6)) : 0;
            return (
              <rect key={d.date} x={i * (bw + gap)} y={H - h} width={bw} height={h} rx="1.5" fill={s.color}>
                <title>{`${short(d.date)}: ${v.toLocaleString(locale)} ${s.unit}`}</title>
              </rect>
            );
          })}
        </svg>
        {total === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-400">
            {t("admin.quota.chartEmpty")}
          </div>
        )}
      </div>
      {history.length > 0 && (
        <div className="mt-1 flex justify-between text-xs text-gray-500">
          <span>{short(history[0].date)}</span>
          <span>{short(history[history.length - 1].date)}</span>
        </div>
      )}
    </div>
  );
}

export default function QuotaPanel() {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(refresh = false) {
    setBusy(true);
    setError("");
    try {
      setData(await getAdminQuotas(refresh));
    } catch (e) {
      setError(e.message || t("admin.quota.loadError"));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const warnings = useMemo(
    () => (data?.items || []).filter((i) => ["warn", "full", "error"].includes(i.status)).length,
    [data],
  );

  return (
    <section className="mb-8" aria-labelledby="quota-title" data-testid="quota-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 id="quota-title" className="text-lg font-bold text-gray-900">{t("admin.quota.title")}</h2>
          <p className="text-sm text-gray-500">
            {t("admin.quota.subtitle", { percent: data?.alert_percent ?? 80 })}
            {data?.checked_at && t("admin.quota.updatedAt", { date: fmtDate(data.checked_at, locale) })}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {warnings > 0 && (
            <span className="text-sm font-medium text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full">{t("admin.quota.warningsCount", { count: warnings })}</span>
          )}
          <button
            type="button"
            onClick={() => void load(true)}
            disabled={busy}
            className="px-3 py-1.5 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            {busy ? t("admin.quota.refreshing") : t("admin.quota.refreshBtn")}
          </button>
        </div>
      </div>
      {error && <div className="mb-4 p-3 rounded bg-red-50 text-red-700 text-sm">{error}</div>}
      {!data && !error && <p className="text-sm text-gray-500">{t("common.loading")}</p>}
      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
            {data.items.map((item) => (
              <QuotaCard key={item.key} item={item} />
            ))}
          </div>
          <UsageChart history={data.history} available={data.series} />
        </>
      )}
    </section>
  );
}
