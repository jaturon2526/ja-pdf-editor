// หน้าต่าง "แทรกหน้า" (v1.39.0): จากเครื่อง (PDF/รูปภาพ/Office) · เอกสารของฉัน · หน้าว่าง
// ไฟล์ต้นทางเปิดเป็น session ชั่วคราวบน server (ไม่บันทึกในเอกสารของฉัน) — ภาพย่อใช้ renderPage ของ session นั้น
// ปิดหน้าต่าง/แทรกเสร็จ → ปิด session ต้นทาง
import { useEffect, useMemo, useRef, useState } from "react";
import * as api from "../../api.js";
import { useI18n } from "../../i18n/I18nContext.jsx";
import { pageImageSrc } from "../../utils/pageImage.js";
import { formatPageRange, parsePageRange } from "../../utils/pageRange.js";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.rtf,.odt,.ods,.odp";
const THUMB_ZOOM = 0.2;
const A4 = { width: 595, height: 842 };

function TabButton({ id, current, onSelect, children }) {
  return (
    <button type="button" role="tab" aria-selected={current === id} onClick={() => onSelect(id)}
      className={`flex-1 px-2 py-2 text-sm border-b-2 ${current === id ? "border-sky-600 text-sky-700 font-semibold" : "border-transparent text-slate-600 hover:text-slate-900"}`}>
      {children}
    </button>
  );
}

function PositionSelect({ pageCount, value, onChange, t }) {
  return (
    <label className="block text-sm text-slate-700" htmlFor="insert-position">
      {t("editor.modals.insertPages.positionLabel")}
      <select id="insert-position" value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 block w-full border border-slate-300 rounded px-2 py-2 text-base sm:text-sm bg-white">
        <option value={0}>{t("editor.modals.insertPages.beforePage1")}</option>
        {Array.from({ length: pageCount }, (_, i) => {
          const page = i + 1;
          const label = page === pageCount
            ? t("editor.modals.insertPages.afterLastPage", { page })
            : t("editor.modals.insertPages.afterPage", { page });
          return <option key={page} value={page}>{label}</option>;
        })}
      </select>
    </label>
  );
}

function getBlankDims(blankSize, session, currentPage) {
  if (blankSize === "a4-landscape") return { width: A4.height, height: A4.width };
  if (blankSize === "a4") return A4;
  return {
    width: session.pageSizes?.[currentPage]?.[0] || A4.width,
    height: session.pageSizes?.[currentPage]?.[1] || A4.height,
  };
}

export default function InsertPagesModal({ session, currentPage, defaultPosition, onInsert, onClose }) {
  const { t } = useI18n();
  const [tab, setTab] = useState("local");
  const [position, setPosition] = useState(defaultPosition);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  // ต้นทาง: { session_id, filename, page_count, status, own }
  const [source, setSource] = useState(null);
  const [password, setPassword] = useState("");
  const [thumbs, setThumbs] = useState({});
  const [selected, setSelected] = useState([]);   // เลขหน้า 1-based ตามที่เลือก
  const [rangeText, setRangeText] = useState("");
  const [myFiles, setMyFiles] = useState(null);
  const [blankCount, setBlankCount] = useState(1);
  const [blankSize, setBlankSize] = useState("current");
  const fileRef = useRef(null);
  const sourceRef = useRef(null);
  sourceRef.current = source;

  // ปิด session ต้นทางชั่วคราวเมื่อเปลี่ยนไฟล์/ปิดหน้าต่าง
  function releaseSource(src) {
    if (src && !src.own) api.closeSession(src.session_id).catch(() => {});
  }
  useEffect(() => () => releaseSource(sourceRef.current), []);

  useEffect(() => {
    if (tab !== "mine" || myFiles !== null) return;
    api.getMyFiles()
      .then((res) => setMyFiles(res.files || []))
      .catch((e) => { setMyFiles([]); setError(e.message || t("editor.modals.insertPages.errLoadFiles")); });
  }, [tab, myFiles, t]);

  // ภาพย่อหน้าของต้นทาง — โหลดทีละหน้า (ไฟล์ยาวก็ไม่ยิงพร้อมกันทีเดียว)
  const ready = source && source.status === "ok" && source.page_count > 0;
  useEffect(() => {
    if (!ready) return undefined;
    const ctrl = new AbortController(); // ปิดหน้าต่าง/เปลี่ยนต้นทาง → หยุดโหลดภาพย่อที่เหลือ
    const stopped = () => ctrl.signal.aborted;
    void (async () => {
      for (let p = 0; p < source.page_count && !stopped(); p++) {
        try {
          const data = await api.renderPage(source.session_id, p, THUMB_ZOOM);
          if (!stopped()) setThumbs((prev) => ({ ...prev, [p + 1]: data.image_base64 }));
        } catch {
          if (!stopped()) setThumbs((prev) => ({ ...prev, [p + 1]: null }));
        }
      }
    })();
    return () => ctrl.abort();
  }, [ready, source?.session_id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openSource(promise) {
    setError("");
    setBusy(t("editor.modals.insertPages.busyOpening"));
    releaseSource(source);
    setSource(null);
    setThumbs({});
    try {
      const src = await promise;
      setSource(src);
      setPassword("");
      if (src.status === "ok") pickAll(src.page_count);
    } catch (e) {
      setError(e.message || t("editor.modals.insertPages.errOpenFile"));
    } finally {
      setBusy("");
    }
  }

  function pickAll(count) {
    const all = Array.from({ length: count }, (_, i) => i + 1);
    setSelected(all);
    setRangeText(formatPageRange(all));
  }

  async function handleUnlock(e) {
    e.preventDefault();
    setError("");
    try {
      const res = await api.unlockPdf(source.session_id, password);
      if (res.status !== "ok") { setError(t("editor.modals.insertPages.errWrongPassword")); return; }
      const next = { ...source, status: "ok", page_count: res.page_count };
      setSource(next);
      pickAll(res.page_count);
    } catch (err) {
      setError(err.message || t("editor.modals.insertPages.errUnlockFailed"));
    }
  }

  function toggle(p) {
    const next = selected.includes(p) ? selected.filter((x) => x !== p) : [...selected, p].sort((a, b) => a - b);
    setSelected(next);
    setRangeText(formatPageRange(next));
  }

  const parsedRange = useMemo(() => (ready ? parsePageRange(rangeText, source.page_count) : null), [ready, rangeText, source]);
  function onRangeChange(text) {
    setRangeText(text);
    const parsed = parsePageRange(text, source.page_count);
    if (parsed) setSelected(parsed);
  }

  const blankDims = getBlankDims(blankSize, session, currentPage);

  const count = tab === "blank" ? blankCount : (parsedRange?.length || 0);
  const canSubmit = !busy && (tab === "blank" ? blankCount >= 1 && blankCount <= 50 : ready && parsedRange && parsedRange.length > 0);

  let summaryText = "";
  if (count > 0) {
    summaryText = position === 0
      ? t("editor.modals.insertPages.summaryStart", { count })
      : t("editor.modals.insertPages.summaryAfter", { count, position });
  }

  async function submit() {
    setError("");
    setBusy(t("editor.modals.insertPages.busyInserting"));
    try {
      const body = tab === "blank"
        ? { position, blank: { count: blankCount, ...blankDims } }
        : { position, source_session_id: source.session_id, pages: rangeText };
      const ok = await onInsert(body);
      if (ok) onClose();
    } catch (e) {
      setError(e.message || t("editor.modals.insertPages.errInsertFailed"));
    } finally {
      setBusy("");
    }
  }

  function switchTab(next) {
    setTab(next);
    setError("");
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/40" role="presentation" onClick={busy ? undefined : onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="insert-pages-title" onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[92dvh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
          <h3 id="insert-pages-title" className="text-lg font-bold text-slate-900">{t("editor.modals.insertPages.title")}</h3>
          <button type="button" onClick={onClose} disabled={!!busy} aria-label={t("editor.modals.insertPages.closeAria")} className="icon-btn">✕</button>
        </div>

        <div role="tablist" aria-label={t("editor.modals.insertPages.sourceTablistAria")} className="flex border-b border-slate-200 px-3">
          <TabButton id="local" current={tab} onSelect={switchTab}>{t("editor.modals.insertPages.tabLocal")}</TabButton>
          <TabButton id="mine" current={tab} onSelect={switchTab}>{t("editor.modals.insertPages.tabMine")}</TabButton>
          <TabButton id="blank" current={tab} onSelect={switchTab}>{t("editor.modals.insertPages.tabBlank")}</TabButton>
        </div>

        <div className="px-5 py-4 overflow-y-auto space-y-4 flex-1">
          {tab === "local" && (
            <div className="space-y-1">
              <input ref={fileRef} type="file" accept={ACCEPT} className="hidden" data-testid="insert-pages-file"
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void openSource(api.createInsertSource(f)); }} />
              <button type="button" onClick={() => fileRef.current?.click()} disabled={!!busy}
                className="px-3 py-2 text-sm rounded border border-slate-300 bg-white hover:bg-slate-50">
                {t("editor.modals.insertPages.chooseFile")}
              </button>
              <p className="text-xs text-slate-500">{t("editor.modals.insertPages.localHint")}</p>
            </div>
          )}

          {tab === "mine" && !source && (
            myFiles === null ? <p className="text-sm text-slate-500">{t("editor.modals.insertPages.loadingFiles")}</p> : (
              <ul className="max-h-60 overflow-y-auto divide-y divide-slate-100 border border-slate-200 rounded-lg" data-testid="insert-pages-mine">
                {myFiles.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">{t("editor.modals.insertPages.noFiles")}</li>}
                {myFiles.map((f) => (
                  <li key={f.id}>
                    <button type="button" disabled={!!busy}
                      onClick={() => void openSource(f.session_id === session.sessionId
                        ? Promise.resolve({ session_id: session.sessionId, filename: f.filename, page_count: session.pageCount, status: "ok", own: true })
                        : api.createInsertSourceFromFile(f.id))}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-sky-50">
                      <span className="block text-slate-900 break-all">{f.filename}</span>
                      {f.session_id === session.sessionId && (
                        <span className="block text-xs text-slate-500">{t("editor.modals.insertPages.currentOpenFileHint")}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )
          )}

          {tab !== "blank" && source && (
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="text-slate-700 break-all">
                {t("editor.modals.insertPages.filePrefix")} <strong>{source.filename}</strong>
                {ready && t("editor.modals.insertPages.sourcePageCount", { count: source.page_count })}
              </span>
              {tab === "mine" && (
                <button type="button" className="text-blue-700 hover:underline shrink-0" onClick={() => { releaseSource(source); setSource(null); }}>
                  {t("editor.modals.insertPages.changeFile")}
                </button>
              )}
            </div>
          )}

          {tab !== "blank" && source?.status === "password_required" && (
            <form onSubmit={(e) => void handleUnlock(e)} className="flex gap-2 items-end">
              <label className="flex-1 text-sm text-slate-700" htmlFor="insert-source-password">
                {t("editor.modals.insertPages.passwordLabel")}
                <input id="insert-source-password" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)}
                  className="mt-1 block w-full border border-slate-300 rounded px-3 py-2 text-base sm:text-sm" />
              </label>
              <button type="submit" disabled={!password} className="px-3 py-2 text-sm rounded bg-slate-800 text-white disabled:opacity-50">
                {t("editor.modals.insertPages.unlock")}
              </button>
            </form>
          )}

          {tab !== "blank" && ready && (
            <>
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex-1 min-w-[12rem] text-sm text-slate-700" htmlFor="insert-pages-range">
                  {t("editor.modals.insertPages.pagesRangeLabel")}
                  <input id="insert-pages-range" value={rangeText} onChange={(e) => onRangeChange(e.target.value)}
                    aria-invalid={!parsedRange}
                    className={`mt-1 block w-full border rounded px-3 py-2 text-base sm:text-sm ${parsedRange ? "border-slate-300" : "border-red-400"}`} />
                </label>
                <button type="button" onClick={() => pickAll(source.page_count)} className="px-3 py-2 text-sm rounded border border-slate-300 hover:bg-slate-50">
                  {t("editor.modals.insertPages.allPages")}
                </button>
                <button type="button" onClick={() => { setSelected([]); setRangeText(""); }} className="px-3 py-2 text-sm rounded border border-slate-300 hover:bg-slate-50">
                  {t("editor.modals.insertPages.clear")}
                </button>
              </div>
              {!parsedRange && (
                <p className="text-xs text-red-600" role="alert">
                  {t("editor.modals.insertPages.errInvalidRange", { count: source.page_count })}
                </p>
              )}
              <ul className="grid grid-cols-3 sm:grid-cols-5 gap-2" data-testid="insert-pages-thumbs">
                {Array.from({ length: source.page_count }, (_, i) => i + 1).map((p) => {
                  const on = selected.includes(p);
                  return (
                    <li key={p}>
                      <button type="button" onClick={() => toggle(p)} aria-pressed={on}
                        aria-label={t("editor.modals.insertPages.sourcePageAria", { page: p })}
                        className={`w-full rounded-lg border-2 p-1 bg-white ${on ? "border-sky-600 ring-2 ring-sky-200" : "border-slate-200 opacity-70 hover:opacity-100"}`}>
                        <span className="block aspect-[3/4] bg-slate-50 overflow-hidden rounded">
                          {thumbs[p] ? <img src={pageImageSrc(thumbs[p])} alt="" className="w-full h-full object-contain" /> : null}
                        </span>
                        <span className="block text-xs text-center mt-1 text-slate-700">{on ? "✓ " : ""}{p}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          {tab === "blank" && (
            <div className="grid grid-cols-2 gap-3">
              <label className="text-sm text-slate-700" htmlFor="insert-blank-count">
                {t("editor.modals.insertPages.blankCountLabel")}
                <input id="insert-blank-count" type="number" min={1} max={50} value={blankCount}
                  onChange={(e) => setBlankCount(Math.max(1, Math.min(50, Number.parseInt(e.target.value, 10) || 1)))}
                  className="mt-1 block w-full border border-slate-300 rounded px-3 py-2 text-base sm:text-sm" />
              </label>
              <label className="text-sm text-slate-700" htmlFor="insert-blank-size">
                {t("editor.modals.insertPages.blankSizeLabel")}
                <select id="insert-blank-size" value={blankSize} onChange={(e) => setBlankSize(e.target.value)}
                  className="mt-1 block w-full border border-slate-300 rounded px-2 py-2 text-base sm:text-sm bg-white">
                  <option value="current">{t("editor.modals.insertPages.sizeCurrent")}</option>
                  <option value="a4">{t("editor.modals.insertPages.sizeA4")}</option>
                  <option value="a4-landscape">{t("editor.modals.insertPages.sizeA4Landscape")}</option>
                </select>
              </label>
            </div>
          )}

          <PositionSelect pageCount={session.pageCount} value={position} onChange={setPosition} t={t} />
          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          {busy && <p className="text-sm text-slate-600" role="status">{busy}</p>}
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3 px-5 py-3 border-t border-slate-200">
          <span className="text-sm text-slate-600" data-testid="insert-pages-summary">
            {summaryText}
          </span>
          <div className="flex gap-2 justify-end">
            <button type="button" onClick={onClose} disabled={!!busy} className="px-4 py-2 text-sm rounded border border-slate-300 text-slate-700 whitespace-nowrap">
              {t("editor.modals.insertPages.cancel")}
            </button>
            <button type="button" onClick={() => void submit()} disabled={!canSubmit}
              className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 whitespace-nowrap">
              {t("editor.modals.insertPages.submit")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
