// ส่วน "ใบรับรองลายเซ็นดิจิทัล" ในหน้าความปลอดภัย — เก็บไฟล์ .p12/.pfx ไว้ใช้เซ็นโดยไม่ต้องเลือกไฟล์ทุกครั้ง
// (backend: /signature/certificates · app/services/certificate_store.py)
// ตรวจรหัสครั้งแรกก่อนบันทึก · ระบบไม่เก็บรหัส — กรอกทุกครั้งที่ใช้เซ็นหรือลบ
// หรือผูก passkey ไว้ปลดล็อกแทนการพิมพ์ (utils/certPasskey.js — รหัสถูกเข้ารหัสในเครื่องด้วยค่าจาก passkey, server ถอดไม่ได้)
import { useEffect, useRef, useState } from "react";
import {
  bindCertificatePasskey, deleteCertificate, listCertificates, prepareCertificatePasskey,
  unbindCertificatePasskey, uploadCertificate,
} from "../../api";
import { certPasskeyErrorMessage, supportsWebAuthn, unlockWithPasskey, wrapWithPasskey } from "../../utils/certPasskey.js";

const fmt = (iso) =>
  iso ? new Date(iso).toLocaleDateString("th-TH", { day: "numeric", month: "short", year: "numeric" }) : "—";

function CertIcon({ className = "w-5 h-5" }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2l7 3v6c0 5-3.5 9.3-7 11-3.5-1.7-7-6-7-11V5l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function KeyIcon({ className = "w-4 h-4" }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="M10.7 12.3L21 2M16 7l3 3M18.5 4.5l2 2" />
    </svg>
  );
}

const FRESH_MS = 4 * 60 * 1000; // challenge ฝั่ง server มีอายุ 5 นาที

// ผูก passkey กับใบรับรอง: กรอกรหัส (ตรวจที่ server) + สแกน passkey → เก็บรหัสที่เข้ารหัสด้วยค่าจาก passkey
function BindPasskeyDialog({ cert, onDone, onCancel }) {
  const [password, setPassword] = useState("");
  const [prepared, setPrepared] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function prepare() {
    try {
      setPrepared(await prepareCertificatePasskey(cert.id));
    } catch (e) {
      setPrepared(null);
      setError(e.message || "เตรียม passkey ไม่สำเร็จ");
    }
  }

  useEffect(() => {
    void prepare();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(e) {
    e.preventDefault();
    if (!password || busy) return;
    setError("");
    setBusy(true);
    try {
      // Safari ต้องเรียก WebAuthn ทันทีจากการกด — ใช้ options ที่ขอไว้ (ขอใหม่เฉพาะเมื่อเก่าเกิน)
      const ready = prepared && Date.now() - prepared.at < FRESH_MS ? prepared : await prepareCertificatePasskey(cert.id);
      const payload = await wrapWithPasskey({ prepared: ready, password, cert });
      const updated = await bindCertificatePasskey(cert.id, payload);
      onDone(updated);
    } catch (err) {
      const msg = certPasskeyErrorMessage(err);
      if (msg) setError(msg);
      void prepare(); // challenge ใช้ได้ครั้งเดียว
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <form onSubmit={handleSubmit} role="dialog" aria-modal="true" aria-labelledby="bind-pk-title"
        className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
        <h3 id="bind-pk-title" className="text-lg font-bold text-gray-900 mb-2">ใช้ passkey ปลดล็อกใบรับรอง</h3>
        <p className="text-sm text-gray-600">
          ผูก passkey ของอุปกรณ์นี้กับ <strong className="text-gray-900 break-words">{cert.label}</strong> —
          ครั้งต่อไปสแกนหน้า/นิ้วแทนการพิมพ์รหัสได้ทั้งตอนเซ็นและตอนลบ
        </p>
        <p className="mt-2 text-xs text-gray-500">
          รหัสถูกเข้ารหัสในเครื่องนี้ด้วยค่าที่มีแต่ passkey ให้ได้ ระบบเก็บไว้แต่เปิดอ่านเองไม่ได้
        </p>
        <label className="block mt-3 text-sm text-gray-700" htmlFor="cert-passkey-password">
          รหัสผ่านของใบรับรอง (ยืนยันครั้งนี้ครั้งเดียว)
          <input id="cert-passkey-password" type="password" autoComplete="off" value={password}
            onChange={(e) => { setPassword(e.target.value); setError(""); }}
            className="mt-1 block w-full border border-gray-300 rounded px-3 py-2 text-base sm:text-sm" />
        </label>
        {error && <p className="mt-2 text-sm text-red-600" role="alert">{error}</p>}
        <div className="flex justify-end gap-3 mt-6">
          <button type="button" onClick={onCancel} disabled={busy} className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700">ยกเลิก</button>
          <button type="submit" disabled={busy || !password}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
            <KeyIcon />
            {busy ? "กำลังยืนยัน..." : "ยืนยันด้วย passkey"}
          </button>
        </div>
      </form>
    </div>
  );
}

function StatusBadge({ cert }) {
  if (cert.expired) return <span className="inline-block whitespace-nowrap text-[11px] px-1.5 py-0.5 rounded bg-red-100 text-red-700">หมดอายุแล้ว</span>;
  if (cert.days_left < 30) return <span className="inline-block whitespace-nowrap text-[11px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">เหลือ {cert.days_left} วัน</span>;
  return <span className="inline-block whitespace-nowrap text-[11px] px-1.5 py-0.5 rounded bg-green-100 text-green-700">ใช้งานได้</span>;
}

export default function CertificatesSection() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [adding, setAdding] = useState(false);
  const [file, setFile] = useState(null);
  const [password, setPassword] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [bindFor, setBindFor] = useState(null);
  const canPasskey = supportsWebAuthn();
  const fileRef = useRef(null);

  async function reload() {
    try {
      setItems(await listCertificates());
    } catch (e) {
      setError(e.message || "โหลดรายการใบรับรองไม่สำเร็จ");
      setItems([]);
    }
  }

  useEffect(() => {
    void reload();
  }, []);

  function resetForm() {
    setAdding(false);
    setFile(null);
    setPassword("");
    setLabel("");
  }

  async function handleAdd(e) {
    e.preventDefault();
    if (!file || !password) return;
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const cert = await uploadCertificate(file, password, label.trim());
      setSuccess(`บันทึกใบรับรอง “${cert.label}” แล้ว — ระบบไม่ได้เก็บรหัสผ่าน ต้องกรอกทุกครั้งที่ใช้เซ็น`);
      resetForm();
      await reload();
    } catch (err) {
      setError(err.message || "บันทึกใบรับรองไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }

  async function handleUnbind(cert, binding) {
    setError("");
    setSuccess("");
    try {
      await unbindCertificatePasskey(cert.id, binding.id);
      setSuccess(`เลิกใช้ passkey “${binding.name}” กับ “${cert.label}” แล้ว`);
      await reload();
    } catch (err) {
      setError(err.message || "เลิกใช้ passkey ไม่สำเร็จ");
    }
  }

  async function handleDelete(e, { withPasskey = false } = {}) {
    e?.preventDefault();
    setDeleteError("");
    setBusy(true);
    try {
      const password = withPasskey ? await unlockWithPasskey(confirmDelete) : deletePassword;
      await deleteCertificate(confirmDelete.id, password);
      setSuccess(`ลบใบรับรอง “${confirmDelete.label}” แล้ว`);
      setConfirmDelete(null);
      setDeletePassword("");
      await reload();
    } catch (err) {
      const msg = withPasskey ? certPasskeyErrorMessage(err) : err.message || "ลบไม่สำเร็จ";
      if (msg) setDeleteError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="cert-title" data-testid="certificate-section" className="mt-10 pt-6 border-t border-gray-200">
      <div className="flex items-start gap-3 mb-3">
        <div className="p-2 rounded-lg bg-sky-50 text-sky-600 shrink-0"><CertIcon /></div>
        <div className="min-w-0">
          <h2 id="cert-title" className="text-lg font-semibold text-gray-900">ใบรับรองลายเซ็นดิจิทัล</h2>
          <p className="text-sm text-gray-600">
            บันทึกไฟล์ .p12 / .pfx ไว้ใช้เซ็นเอกสารแบบดิจิทัลโดยไม่ต้องเลือกไฟล์ทุกครั้ง —
            ระบบตรวจรหัสครั้งแรกก่อนบันทึก แต่<strong>ไม่เก็บรหัสผ่าน</strong> ต้องกรอกทุกครั้งที่ใช้เซ็นหรือลบ
            {canPasskey && " — หรือผูก passkey ไว้สแกนหน้า/นิ้วแทนการพิมพ์"}
          </p>
        </div>
      </div>

      {error && <div className="mb-3 p-3 bg-red-100 text-red-700 rounded text-sm" role="alert">{error}</div>}
      {success && <div className="mb-3 p-3 bg-green-100 text-green-700 rounded text-sm" role="status">{success}</div>}

      {items === null ? (
        <p className="text-sm text-gray-500">กำลังโหลด...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-gray-500 mb-3">ยังไม่มีใบรับรองที่บันทึกไว้</p>
      ) : (
        <ul className="mb-3 divide-y divide-gray-100 rounded-lg border border-gray-200" data-testid="certificate-list">
          {items.map((c) => (
            <li key={c.id} className="flex flex-wrap items-start gap-x-3 gap-y-2 px-3 py-3">
              <CertIcon className="w-4 h-4 mt-1 text-gray-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-900 break-words">
                  {c.label} <StatusBadge cert={c} />
                  {c.self_signed && (
                    <span className="ml-1 inline-block whitespace-nowrap text-[11px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600" title="สร้างเอง ไม่ได้ออกโดยผู้ให้บริการออกใบรับรอง (CA) — โปรแกรมอ่าน PDF จะแสดงว่ายังไม่ได้รับการรับรอง">
                      self-signed
                    </span>
                  )}
                </div>
                <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-gray-600">
                  <dt className="text-gray-500">ผู้ถือ</dt>
                  <dd className="break-words">{c.subject_cn || "—"}{c.organization ? ` · ${c.organization}` : ""}</dd>
                  <dt className="text-gray-500">ผู้ออก</dt>
                  <dd className="break-words">{c.issuer_cn || "—"}</dd>
                  <dt className="text-gray-500">ใช้ได้</dt>
                  <dd>{fmt(c.valid_from)} – {fmt(c.valid_to)}</dd>
                  <dt className="text-gray-500">บันทึกเมื่อ</dt>
                  <dd>{fmt(c.created_at)} · {c.last_used_at ? `ใช้ล่าสุด ${fmt(c.last_used_at)}` : "ยังไม่เคยใช้"}</dd>
                </dl>
                {canPasskey && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5" data-testid="certificate-passkeys">
                    {c.passkeys?.map((b) => (
                      <span key={b.id} className="inline-flex items-center gap-1 whitespace-nowrap text-xs pl-2 pr-1 py-0.5 rounded-full bg-sky-50 text-sky-800 border border-sky-200">
                        <KeyIcon className="w-3 h-3" />
                        {b.name}
                        <button type="button" onClick={() => handleUnbind(c, b)} aria-label={`เลิกใช้ passkey ${b.name}`}
                          title="เลิกใช้ passkey นี้กับใบรับรองนี้" className="ml-0.5 w-5 h-5 rounded-full hover:bg-sky-100 text-sky-700">
                          ×
                        </button>
                      </span>
                    ))}
                    {!c.expired && (
                      <button type="button" onClick={() => { setBindFor(c); setError(""); setSuccess(""); }}
                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border border-dashed border-sky-400 text-sky-700 hover:bg-sky-50">
                        <KeyIcon className="w-3 h-3" />
                        {c.passkeys?.length ? "เพิ่ม passkey" : "ใช้ passkey แทนรหัส"}
                      </button>
                    )}
                  </div>
                )}
              </div>
              <button type="button" onClick={() => { setConfirmDelete(c); setDeletePassword(""); setDeleteError(""); }}
                className="px-2 py-1 text-sm text-red-600 hover:bg-red-50 rounded shrink-0">
                ลบ
              </button>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <form onSubmit={handleAdd} className="space-y-3 p-3 rounded-lg bg-gray-50 border border-gray-200" data-testid="certificate-form">
          <input ref={fileRef} type="file" accept=".p12,.pfx,application/x-pkcs12" className="hidden" data-testid="certificate-file"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setError(""); } e.target.value = ""; }} />
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => fileRef.current?.click()}
              className="px-3 py-2 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50">
              เลือกไฟล์ .p12 / .pfx...
            </button>
            <span className="text-sm text-gray-600 break-all">{file ? file.name : "ยังไม่ได้เลือกไฟล์"}</span>
          </div>
          <label className="block text-sm text-gray-700" htmlFor="cert-password">
            รหัสผ่านของใบรับรอง (ใช้ตรวจครั้งนี้เท่านั้น ไม่ถูกบันทึก)
            <input id="cert-password" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded px-3 py-2 text-base sm:text-sm" />
          </label>
          <label className="block text-sm text-gray-700" htmlFor="cert-label">
            ชื่อที่จะแสดง (ไม่บังคับ — ค่าเริ่มต้นคือชื่อในใบรับรอง)
            <input id="cert-label" maxLength={100} value={label} onChange={(e) => setLabel(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded px-3 py-2 text-base sm:text-sm" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !file || !password}
              className="px-4 py-2 text-sm font-medium rounded bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
              {busy ? "กำลังตรวจใบรับรอง..." : "ตรวจและบันทึก"}
            </button>
            <button type="button" onClick={resetForm} disabled={busy} className="px-3 py-2 text-sm text-gray-600">ยกเลิก</button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => { setAdding(true); setError(""); setSuccess(""); }}
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded border border-blue-600 text-blue-700 hover:bg-blue-50">
          + เพิ่มใบรับรอง
        </button>
      )}
      <p className="mt-3 text-xs text-gray-500">
        เก็บได้สูงสุด 5 ใบ · ไฟล์ถูกเข้ารหัสอีกชั้นก่อนเก็บ · กรอกรหัสผิดหลายครั้งจะถูกพักการใช้ชั่วคราว
        {canPasskey && " · ผูก passkey ได้ทีละอุปกรณ์ (ต้องเพิ่ม passkey ด้านบนก่อน)"}
      </p>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
          <form onSubmit={handleDelete} role="dialog" aria-modal="true" aria-labelledby="del-cert-title"
            className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
            <h3 id="del-cert-title" className="text-lg font-bold text-gray-900 mb-2">ลบใบรับรอง</h3>
            <p className="text-sm text-gray-600">
              ลบ <strong className="text-gray-900 break-words">{confirmDelete.label}</strong> ออกจากระบบ?
              เอกสารที่เซ็นไปแล้วยังใช้ได้ตามปกติ — กรอกรหัสผ่านของใบรับรองเพื่อยืนยัน
            </p>
            <label className="block mt-3 text-sm text-gray-700" htmlFor="cert-delete-password">
              รหัสผ่านของใบรับรอง
              <input id="cert-delete-password" type="password" autoComplete="off" value={deletePassword}
                onChange={(e) => { setDeletePassword(e.target.value); setDeleteError(""); }}
                className="mt-1 block w-full border border-gray-300 rounded px-3 py-2 text-base sm:text-sm" />
            </label>
            {deleteError && <p className="mt-2 text-sm text-red-600" role="alert">{deleteError}</p>}
            {canPasskey && confirmDelete.passkeys?.length > 0 && (
              <button type="button" onClick={() => handleDelete(null, { withPasskey: true })} disabled={busy}
                className="mt-3 w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm rounded border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50">
                <KeyIcon />
                ยืนยันด้วย passkey แล้วลบ
              </button>
            )}
            <div className="flex justify-end gap-3 mt-6">
              <button type="button" onClick={() => setConfirmDelete(null)} disabled={busy} className="px-4 py-2 text-sm rounded border border-gray-300 text-gray-700">ยกเลิก</button>
              <button type="submit" disabled={busy || !deletePassword} className="px-4 py-2 text-sm rounded bg-red-600 hover:bg-red-700 text-white disabled:opacity-50">
                {busy ? "กำลังลบ..." : "ลบใบรับรอง"}
              </button>
            </div>
          </form>
        </div>
      )}

      {bindFor && (
        <BindPasskeyDialog cert={bindFor} onCancel={() => setBindFor(null)}
          onDone={(updated) => {
            setBindFor(null);
            setSuccess(`ผูก passkey กับ “${updated.label}” แล้ว — ครั้งต่อไปสแกน passkey แทนการพิมพ์รหัสได้`);
            void reload();
          }} />
      )}
    </section>
  );
}
