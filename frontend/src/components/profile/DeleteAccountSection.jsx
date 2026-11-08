// "ลบบัญชี" ในหน้าโปรไฟล์ — แสดงสิ่งที่จะถูกลบ ต้องติ๊กยอมรับ + พิมพ์อีเมล + ยืนยันตัวตน (รหัสผ่าน หรือ passkey)
// backend: GET /auth/account/deletion-summary · POST /auth/account/delete (ดู services/account_service.py)
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  assertPasskey,
  browserSupportsWebAuthn,
  deleteAccount,
  getAccountDeletionSummary,
  getDeleteAccountPasskeyOptions,
  passkeyErrorMessage,
} from "../../api";

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${i === 0 ? v : v.toFixed(1)} ${units[i]}`;
}

function DeleteDialog({ email, onClose }) {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [ack, setAck] = useState(false);
  const [typed, setTyped] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [prepared, setPrepared] = useState(null); // passkey options ที่ขอไว้ก่อน (Safari)

  useEffect(() => {
    getAccountDeletionSummary()
      .then((s) => {
        setSummary(s);
        if (s.passkeys > 0 && browserSupportsWebAuthn()) {
          getDeleteAccountPasskeyOptions().then(setPrepared).catch(() => setPrepared(null));
        }
      })
      .catch((e) => setError(e.message || "โหลดข้อมูลไม่สำเร็จ"));
  }, []);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const emailOk = typed.trim().toLowerCase() === email.toLowerCase();
  const ready = summary && !summary.is_last_admin && ack && emailOk && !busy;

  async function finish(auth) {
    setBusy(true);
    setError("");
    try {
      await deleteAccount({ confirmEmail: typed.trim(), ...auth });
      localStorage.removeItem("token");
      navigate("/login?deleted=1", { replace: true });
    } catch (e) {
      setError(e.message || "ลบบัญชีไม่สำเร็จ");
      setBusy(false);
    }
  }

  async function withPasskey() {
    if (!prepared || Date.now() - prepared.at > 4 * 60 * 1000) {
      setError("กำลังเตรียม passkey ใหม่ — กดอีกครั้ง");
      getDeleteAccountPasskeyOptions().then(setPrepared).catch((e) => setError(e.message));
      return;
    }
    const flow = prepared;
    setPrepared(null);
    try {
      const credential = await assertPasskey(flow.options);
      await finish({ passkey: { flowId: flow.flow_id, credential } });
    } catch (e) {
      const msg = passkeyErrorMessage(e);
      if (msg) setError(msg);
      getDeleteAccountPasskeyOptions().then(setPrepared).catch(() => setPrepared(null));
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center bg-black/50 sm:p-6" onClick={() => !busy && onClose()}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-account-title"
        className="bg-white w-full sm:max-w-lg max-h-[92dvh] overflow-y-auto rounded-t-2xl sm:rounded-2xl shadow-2xl p-5 sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="delete-account-title" className="text-xl font-bold text-red-700 mb-3">ลบบัญชีถาวร</h2>
        <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-800 mb-4" role="alert">
          <strong>การลบบัญชีกู้คืนไม่ได้</strong> — ไฟล์และข้อมูลทั้งหมดของ <strong className="[overflow-wrap:anywhere]">{email}</strong> จะถูกลบทันที
          รวมถึงไฟล์ที่ระบบเก็บไว้ ผู้ดูแลระบบก็กู้คืนให้ไม่ได้ ดาวน์โหลดไฟล์ที่ต้องการเก็บไว้ก่อน
        </div>

        {!summary && !error && <p className="text-sm text-gray-500">กำลังโหลด...</p>}
        {summary && (
          <ul className="text-sm text-gray-700 space-y-1.5 mb-4 list-disc pl-5" data-testid="delete-summary">
            <li>ไฟล์ในเอกสารของฉัน <strong>{summary.files}</strong> ไฟล์ ({formatBytes(summary.storage_bytes)}) — ลบทั้งหมด</li>
            <li>
              คำขอลงนามที่คุณส่ง <strong>{summary.requests_total}</strong> รายการ — ลบทั้งหมด
              {summary.requests_in_progress > 0 && (
                <> · ที่ยังค้าง <strong>{summary.requests_in_progress}</strong> รายการจะถูกยกเลิกและแจ้งผู้ลงนาม</>
              )}
            </li>
            {summary.pending_as_signer > 0 && (
              <li>เอกสารของคนอื่นที่รอคุณลงนาม <strong>{summary.pending_as_signer}</strong> รายการ — จะถูกปฏิเสธอัตโนมัติและแจ้งเจ้าของเอกสาร</li>
            )}
            {summary.signed_for_others > 0 && (
              <li>
                ลายเซ็นที่คุณลงไว้ในเอกสารของคนอื่น <strong>{summary.signed_for_others}</strong> รายการ — ยังอยู่ในเอกสารของเจ้าของ
                พร้อมชื่อและอีเมลของคุณในประวัติการลงนาม (เป็นหลักฐานของเจ้าของเอกสาร) แต่ไม่เชื่อมกับบัญชีแล้ว
              </li>
            )}
            <li>Passkey, การเชื่อมต่อ LINE, API key ของ AI, ฟอนต์ที่ติดตั้ง และการตั้งค่าทั้งหมด — ลบทั้งหมด</li>
            {summary.line_linked && <li>บัญชี LINE ของ JA PDF ยังอยู่ในรายชื่อเพื่อน — บล็อกเองได้ใน LINE</li>}
          </ul>
        )}

        {summary?.is_last_admin ? (
          <p className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800">
            คุณเป็นผู้ดูแลระบบคนสุดท้าย — แต่งตั้งผู้ดูแลระบบคนอื่นในหน้าแผงควบคุมก่อน จึงจะลบบัญชีได้
          </p>
        ) : (
          summary && (
            <div className="space-y-3">
              <label className="flex items-start gap-2 text-sm text-gray-800 cursor-pointer">
                <input type="checkbox" className="mt-0.5 h-4 w-4" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                ฉันเข้าใจว่าบัญชี ไฟล์ และข้อมูลทั้งหมดจะถูกลบถาวรและกู้คืนไม่ได้
              </label>
              <div>
                <label htmlFor="delete-confirm-email" className="block text-sm text-gray-700 mb-1">
                  พิมพ์อีเมล <strong className="break-all select-all">{email}</strong> เพื่อยืนยัน
                </label>
                <input
                  id="delete-confirm-email"
                  type="email"
                  autoComplete="off"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2"
                />
              </div>
              <div>
                <label htmlFor="delete-password" className="block text-sm text-gray-700 mb-1">รหัสผ่านปัจจุบัน</label>
                <input
                  id="delete-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2"
                />
                <p className="mt-1 text-xs text-gray-500">
                  สมัครด้วย Google หรือ LINE และไม่เคยตั้งรหัสผ่าน? ใช้ Passkey แทน หรือกด "ลืมรหัสผ่าน" ที่หน้าเข้าสู่ระบบเพื่อตั้งรหัสก่อน
                </p>
              </div>
            </div>
          )
        )}

        {error && <div className="mt-3 p-3 rounded bg-red-100 text-red-700 text-sm" role="alert">{error}</div>}

        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button type="button" onClick={onClose} disabled={busy} className="px-4 py-2 rounded border border-gray-300 text-gray-700 hover:bg-gray-50">
            ยกเลิก
          </button>
          {summary && !summary.is_last_admin && summary.passkeys > 0 && browserSupportsWebAuthn() && (
            <button
              type="button"
              onClick={withPasskey}
              disabled={!ready}
              className="px-4 py-2 rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-40"
            >
              ยืนยันด้วย Passkey แล้วลบ
            </button>
          )}
          {summary && !summary.is_last_admin && (
            <button
              type="button"
              onClick={() => finish({ password })}
              disabled={!ready || !password}
              className="px-4 py-2 rounded bg-red-600 hover:bg-red-700 text-white font-semibold disabled:opacity-40"
            >
              {busy ? "กำลังลบ..." : "ลบบัญชีถาวร"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DeleteAccountSection({ email }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="mt-10 pt-6 border-t border-red-200" aria-labelledby="danger-title" data-testid="delete-account-section">
      <h2 id="danger-title" className="text-lg font-semibold text-red-700">ลบบัญชี</h2>
      <p className="text-sm text-gray-600 mt-1 mb-3">
        ลบบัญชีพร้อมไฟล์และข้อมูลทั้งหมดถาวร กู้คืนไม่ได้ — ดาวน์โหลดไฟล์ที่ต้องการเก็บไว้ก่อน
      </p>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="px-4 py-2 rounded border border-red-300 text-red-700 hover:bg-red-50 font-medium"
      >
        ลบบัญชีของฉัน...
      </button>
      {open && <DeleteDialog email={email} onClose={() => setOpen(false)} />}
    </section>
  );
}
