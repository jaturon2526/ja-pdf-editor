// ส่วน "Passkey" ในหน้าความปลอดภัย — ดู/เพิ่ม/เปลี่ยนชื่อ/ลบ passkey (backend: /auth/passkeys)
import { useEffect, useState } from "react";
import {
  browserSupportsWebAuthn,
  deletePasskey,
  guessDeviceName,
  listPasskeys,
  passkeyErrorMessage,
  preparePasskeyRegistration,
  registerPasskey,
  renamePasskey,
} from "../../api";
import { useI18n } from "../../i18n/I18nContext.jsx";

const fmtDate = (iso, locale) =>
  iso ? new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" }) : null;

function KeyIcon({ className = "w-5 h-5" }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <circle cx="8" cy="15" r="4" />
      <path d="M10.85 12.15L19 4M17 6l2 2M15 8l2 2" />
    </svg>
  );
}

export default function PasskeySection({ onChanged } = {}) {
  const { lang, t } = useI18n();
  const locale = lang === "en" ? "en-US" : "th-TH";
  const fmt = (iso) => fmtDate(iso, locale);
  const supported = browserSupportsWebAuthn();
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState(guessDeviceName());
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // {id, name}
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [prepared, setPrepared] = useState(null); // options ที่ขอไว้ก่อน (Safari ต้องเรียก WebAuthn ทันทีตอนกดปุ่ม)

  function prepare() {
    setPrepared(null);
    preparePasskeyRegistration().then(setPrepared).catch((e) => setError(e.message || t("security.passkey.prepareError")));
  }

  async function reload() {
    try {
      setItems(await listPasskeys());
    } catch (e) {
      setError(e.message || t("security.passkey.loadError"));
      setItems([]);
    }
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAdd(e) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const pk = await registerPasskey(newName.trim() || guessDeviceName(), prepared);
      setSuccess(t("security.passkey.addSuccess", { name: pk.name }));
      setAdding(false);
      await reload();
      onChanged?.();
    } catch (err) {
      const msg = passkeyErrorMessage(err, { registering: true });
      if (msg) setError(msg);
      prepare(); // challenge ใช้ได้ครั้งเดียว — เตรียมใหม่สำหรับครั้งถัดไป
    } finally {
      setBusy(false);
    }
  }

  async function handleRename(e) {
    e.preventDefault();
    if (!editing?.name.trim()) return;
    setBusy(true);
    setError("");
    try {
      await renamePasskey(editing.id, editing.name.trim());
      setEditing(null);
      await reload();
    } catch (err) {
      setError(err.message || t("security.passkey.renameError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    const pk = confirmDelete;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await deletePasskey(pk.id);
      setConfirmDelete(null);
      setSuccess(t("security.passkey.deleteSuccess", { name: pk.name }));
      await reload();
      onChanged?.();
    } catch (err) {
      setError(err.message || t("security.passkey.deleteError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="passkey-title" data-testid="passkey-section">
      <div className="flex items-start gap-3 mb-3">
        <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600 shrink-0"><KeyIcon /></div>
        <div className="min-w-0">
          <h2 id="passkey-title" className="text-lg font-semibold text-gray-900">Passkey</h2>
          <p className="text-sm text-gray-600">
            {t("security.passkey.desc")}
          </p>
        </div>
      </div>

      {error && <div className="mb-3 p-3 bg-red-100 text-red-700 rounded text-sm" role="alert">{error}</div>}
      {success && <div className="mb-3 p-3 bg-green-100 text-green-700 rounded text-sm">{success}</div>}

      {!supported ? (
        <p className="p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-sm">
          {t("security.passkey.unsupported")}
        </p>
      ) : (
        <>
          {items === null ? (
            <p className="text-sm text-gray-500">{t("common.loading")}</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-gray-500 mb-3">{t("security.passkey.empty")}</p>
          ) : (
            <ul className="mb-3 divide-y divide-gray-100 rounded-lg border border-gray-200" data-testid="passkey-list">
              {items.map((pk) => (
                <li key={pk.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3">
                  <KeyIcon className="w-4 h-4 text-gray-400 shrink-0" />
                  {editing?.id === pk.id ? (
                    <form onSubmit={(e) => void handleRename(e)} className="flex flex-1 min-w-0 gap-2">
                      <input
                        autoFocus
                        aria-label={t("security.passkey.nameAria")}
                        maxLength={60}
                        value={editing.name}
                        onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                        className="flex-1 min-w-0 border border-gray-300 rounded px-2 py-1 text-sm"
                      />
                      <button type="submit" disabled={busy} className="px-3 py-1 text-sm rounded bg-blue-600 text-white disabled:opacity-50">{t("common.saveShort")}</button>
                      <button type="button" onClick={() => setEditing(null)} className="px-2 py-1 text-sm text-gray-600">{t("common.cancel")}</button>
                    </form>
                  ) : (
                    <>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-gray-900 break-words">
                          {pk.name}
                          {pk.backed_up && (
                            <span className="ml-2 align-middle text-[11px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-700" title={t("security.passkey.syncedTitle")}>
                              {t("security.passkey.syncedBadge")}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500">
                          {t("security.passkey.createdAt", { date: fmt(pk.created_at) })} · {pk.last_used_at ? t("security.passkey.lastUsedAt", { date: fmt(pk.last_used_at) }) : t("security.passkey.neverUsed")}
                        </div>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button type="button" onClick={() => setEditing({ id: pk.id, name: pk.name })} className="px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded">
                          {t("security.passkey.renameBtn")}
                        </button>
                        <button type="button" onClick={() => setConfirmDelete(pk)} className="px-2 py-1 text-sm text-red-600 hover:bg-red-50 rounded">
                          {t("common.delete")}
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}

          {adding ? (
            <form onSubmit={(e) => void handleAdd(e)} className="flex flex-wrap items-end gap-2 p-3 rounded-lg bg-gray-50 border border-gray-200">
              <label className="flex-1 min-w-[180px] text-sm text-gray-700">
                {t("security.passkey.deviceNameLabel")}
                <input
                  autoFocus
                  maxLength={60}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="mt-1 block w-full border border-gray-300 rounded px-3 py-2 text-sm"
                />
              </label>
              <button type="submit" disabled={busy} className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
                {busy ? t("security.passkey.waitingDevice") : t("security.passkey.createBtn")}
              </button>
              <button type="button" onClick={() => setAdding(false)} disabled={busy} className="px-3 py-2 text-sm text-gray-600">{t("common.cancel")}</button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => { setAdding(true); setError(""); setSuccess(""); setNewName(guessDeviceName()); prepare(); }}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded border border-blue-600 text-blue-700 hover:bg-blue-50"
            >
              {t("security.passkey.addBtn")}
            </button>
          )}
          <p className="mt-3 text-xs text-gray-500">
            {t("security.passkey.footerHint")}
          </p>
        </>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
          <div role="dialog" aria-modal="true" aria-labelledby="del-pk-title" className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
            <h3 id="del-pk-title" className="text-lg font-bold text-gray-900 mb-2">{t("security.passkey.deleteTitle")}</h3>
            <p className="text-sm text-gray-600">
              {t("security.passkey.deleteConfirmBefore")} <strong className="text-gray-900 break-words">{confirmDelete.name}</strong>{" "}
              {t("security.passkey.deleteConfirmAfter")}
            </p>
            {items?.length === 1 && (
              <p className="mt-3 p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-sm">
                {t("security.passkey.deleteLastWarning")}
              </p>
            )}
            <div className="flex justify-end gap-3 mt-6">
              <button type="button" onClick={() => setConfirmDelete(null)} disabled={busy} className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700">{t("common.cancel")}</button>
              <button type="button" onClick={() => void handleDelete()} disabled={busy} className="px-4 py-2 text-sm rounded bg-red-600 hover:bg-red-700 text-white disabled:opacity-50">
                {busy ? t("deleteAccount.deleting") : t("security.passkey.deleteBtn")}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
