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

const fmt = (iso) =>
  iso ? new Date(iso).toLocaleDateString("th-TH", { day: "numeric", month: "short", year: "numeric" }) : null;

function KeyIcon({ className = "w-5 h-5" }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <circle cx="8" cy="15" r="4" />
      <path d="M10.85 12.15L19 4M17 6l2 2M15 8l2 2" />
    </svg>
  );
}

export default function PasskeySection() {
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
    preparePasskeyRegistration().then(setPrepared).catch((e) => setError(e.message || "เริ่มสร้าง passkey ไม่สำเร็จ"));
  }

  async function reload() {
    try {
      setItems(await listPasskeys());
    } catch (e) {
      setError(e.message || "โหลดรายการ passkey ไม่สำเร็จ");
      setItems([]);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleAdd(e) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const pk = await registerPasskey(newName.trim() || guessDeviceName(), prepared);
      setSuccess(`เพิ่ม passkey "${pk.name}" แล้ว — ครั้งหน้าเข้าสู่ระบบด้วย passkey ได้เลย`);
      setAdding(false);
      await reload();
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
      setError(err.message || "เปลี่ยนชื่อไม่สำเร็จ");
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
      setSuccess(`ลบ passkey "${pk.name}" แล้ว`);
      await reload();
    } catch (err) {
      setError(err.message || "ลบไม่สำเร็จ");
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
            เข้าสู่ระบบด้วย Face ID, Touch ID, Windows Hello หรือรหัส PIN ของอุปกรณ์ โดยไม่ต้องพิมพ์รหัสผ่าน —
            ปลอดภัยกว่ารหัสผ่านและถูกหลอกเอาไปใช้ในเว็บปลอมไม่ได้
          </p>
        </div>
      </div>

      {error && <div className="mb-3 p-3 bg-red-100 text-red-700 rounded text-sm" role="alert">{error}</div>}
      {success && <div className="mb-3 p-3 bg-green-100 text-green-700 rounded text-sm">{success}</div>}

      {!supported ? (
        <p className="p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-sm">
          เบราว์เซอร์นี้ยังไม่รองรับ passkey — ลองใช้ Safari, Chrome หรือ Edge รุ่นล่าสุด
        </p>
      ) : (
        <>
          {items === null ? (
            <p className="text-sm text-gray-500">กำลังโหลด...</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-gray-500 mb-3">ยังไม่มี passkey</p>
          ) : (
            <ul className="mb-3 divide-y divide-gray-100 rounded-lg border border-gray-200" data-testid="passkey-list">
              {items.map((pk) => (
                <li key={pk.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3">
                  <KeyIcon className="w-4 h-4 text-gray-400 shrink-0" />
                  {editing?.id === pk.id ? (
                    <form onSubmit={handleRename} className="flex flex-1 min-w-0 gap-2">
                      <input
                        autoFocus
                        aria-label="ชื่อ passkey"
                        maxLength={60}
                        value={editing.name}
                        onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                        className="flex-1 min-w-0 border border-gray-300 rounded px-2 py-1 text-sm"
                      />
                      <button type="submit" disabled={busy} className="px-3 py-1 text-sm rounded bg-blue-600 text-white disabled:opacity-50">บันทึก</button>
                      <button type="button" onClick={() => setEditing(null)} className="px-2 py-1 text-sm text-gray-600">ยกเลิก</button>
                    </form>
                  ) : (
                    <>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-gray-900 break-words">
                          {pk.name}
                          {pk.backed_up && (
                            <span className="ml-2 align-middle text-[11px] px-1.5 py-0.5 rounded bg-sky-100 text-sky-700" title="ใช้ได้ทุกอุปกรณ์ที่ลงชื่อเข้าบัญชีเดียวกัน (iCloud Keychain / Google Password Manager)">
                              ซิงก์ข้ามอุปกรณ์
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500">
                          สร้าง {fmt(pk.created_at)} · {pk.last_used_at ? `ใช้ล่าสุด ${fmt(pk.last_used_at)}` : "ยังไม่เคยใช้"}
                        </div>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button type="button" onClick={() => setEditing({ id: pk.id, name: pk.name })} className="px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded">
                          เปลี่ยนชื่อ
                        </button>
                        <button type="button" onClick={() => setConfirmDelete(pk)} className="px-2 py-1 text-sm text-red-600 hover:bg-red-50 rounded">
                          ลบ
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}

          {adding ? (
            <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-2 p-3 rounded-lg bg-gray-50 border border-gray-200">
              <label className="flex-1 min-w-[180px] text-sm text-gray-700">
                ตั้งชื่อให้จำได้ว่าเป็นอุปกรณ์ไหน
                <input
                  autoFocus
                  maxLength={60}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="mt-1 block w-full border border-gray-300 rounded px-3 py-2 text-sm"
                />
              </label>
              <button type="submit" disabled={busy} className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
                {busy ? "รอยืนยันที่อุปกรณ์..." : "สร้าง passkey"}
              </button>
              <button type="button" onClick={() => setAdding(false)} disabled={busy} className="px-3 py-2 text-sm text-gray-600">ยกเลิก</button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => { setAdding(true); setError(""); setSuccess(""); setNewName(guessDeviceName()); prepare(); }}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded border border-blue-600 text-blue-700 hover:bg-blue-50"
            >
              + เพิ่ม passkey
            </button>
          )}
          <p className="mt-3 text-xs text-gray-500">
            เพิ่มได้หลายอุปกรณ์ · รหัสผ่านและการเข้าสู่ระบบด้วย Google / LINE ยังใช้ได้ตามปกติ
          </p>
        </>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
          <div role="dialog" aria-modal="true" aria-labelledby="del-pk-title" className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
            <h3 id="del-pk-title" className="text-lg font-bold text-gray-900 mb-2">ลบ passkey</h3>
            <p className="text-sm text-gray-600">
              ลบ <strong className="text-gray-900 break-words">{confirmDelete.name}</strong> ออกจากบัญชี? อุปกรณ์นี้จะเข้าสู่ระบบด้วย passkey ไม่ได้อีก
              (ควรลบ passkey ในผู้จัดการรหัสผ่านของอุปกรณ์ด้วย)
            </p>
            {items?.length === 1 && (
              <p className="mt-3 p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-sm">
                นี่คือ passkey อันสุดท้าย — หลังลบต้องเข้าสู่ระบบด้วยรหัสผ่านหรือ Google
              </p>
            )}
            <div className="flex justify-end gap-3 mt-6">
              <button type="button" onClick={() => setConfirmDelete(null)} disabled={busy} className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700">ยกเลิก</button>
              <button type="button" onClick={handleDelete} disabled={busy} className="px-4 py-2 text-sm rounded bg-red-600 hover:bg-red-700 text-white disabled:opacity-50">
                {busy ? "กำลังลบ..." : "ลบ passkey"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
