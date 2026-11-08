// รายละเอียดคำขอลงนาม: ดูเอกสาร + ลำดับผู้ลงนาม + ลงนาม/ปฏิเสธ (เมื่อถึงคิว) + ยกเลิก (ผู้ส่ง)
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { assertPasskey, browserSupportsWebAuthn, listPasskeys, passkeyErrorMessage } from "../api/passkey.js";
import { saveBlob } from "../api/client.js";
import {
  cancelSigningRequest,
  downloadSigningDocument,
  downloadSigningEvidence,
  getSigningPasskeyOptions,
  getSigningRequest,
  rejectSigningRequest,
  remindSigningRequest,
  signSigningRequest,
  signingRequestPageUrl,
  verifySigningRequest,
} from "../api/signing.js";
import DigitalSignModal from "../components/DigitalSignModal.jsx";
import ElectronicSignModal from "../components/ElectronicSignModal.jsx";
import SignaturePagePreview from "../components/signing/SignaturePagePreview.jsx";
import SigningHeader from "../components/signing/SigningHeader.jsx";
import { previewScale, previewZoom, useElementWidth } from "../components/signing/useElementWidth.js";
import { DueDate, EVENT_LABELS, SIGN_TYPES, STEP_STATUS, StatusBadge, formatDateTime } from "../components/signing/labels.jsx";

const BOX_STYLE = {
  signed: "border-green-600 bg-green-100/70 text-green-900",
  pending: "border-blue-600 bg-blue-100/70 text-blue-900",
  waiting: "border-gray-400 bg-gray-100/70 text-gray-700 border-dashed",
  rejected: "border-red-500 bg-red-100/70 text-red-800",
  skipped: "border-gray-300 bg-gray-50/70 text-gray-500 border-dashed",
};

function dataUrlToBlob(dataUrl) {
  const [head, body] = dataUrl.split(",");
  const mime = /data:([^;]+)/.exec(head)?.[1] || "image/png";
  const bytes = atob(body);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i += 1) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

export default function SigningRequest() {
  const { id } = useParams();
  const [req, setReq] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState(0);
  const [modal, setModal] = useState(null); // electronic | digital | reject | cancel
  const [rejectReason, setRejectReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [version, setVersion] = useState(0);
  const [previewRef, previewWidth] = useElementWidth();
  // ยืนยันตัวตนด้วย passkey ก่อนลงนาม: hasPasskey = บัญชีมี passkey ไหม · usePasskey = ผู้ใช้เลือกยืนยัน
  // prepared = options ที่ขอไว้ก่อน (Safari ต้องเรียก WebAuthn ทันทีจากการกดปุ่ม) · verified = ผลที่จะส่งไปกับการลงนาม
  const [hasPasskey, setHasPasskey] = useState(null);
  const [usePasskey, setUsePasskey] = useState(true);
  const [prepared, setPrepared] = useState(null);
  const [verified, setVerified] = useState(null);

  const load = useCallback(() => {
    return getSigningRequest(id)
      .then((data) => {
        setReq(data);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const myStep = useMemo(() => (req?.my_turn ? req.steps.find((s) => s.order === req.my_step_order) : null), [req]);
  const passkeyRequired = Boolean(req?.my_require_passkey);
  const wantPasskey = Boolean(myStep) && hasPasskey === true && (passkeyRequired || usePasskey);

  useEffect(() => {
    if (!myStep) return;
    if (!browserSupportsWebAuthn()) {
      setHasPasskey(false);
      return;
    }
    listPasskeys().then((items) => setHasPasskey(items.length > 0)).catch(() => setHasPasskey(false));
  }, [myStep?.order]); // eslint-disable-line react-hooks/exhaustive-deps

  const preparePasskey = useCallback(() => {
    setPrepared(null);
    getSigningPasskeyOptions(id)
      .then((p) => setPrepared({ ...p, at: Date.now() }))
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (wantPasskey && !prepared) preparePasskey();
  }, [wantPasskey]); // eslint-disable-line react-hooks/exhaustive-deps

  // กดปุ่มลงนาม → (ถ้าเลือก) สแกน passkey ทันที → เปิดหน้าต่างวาด/เลือกใบรับรอง
  async function startSigning(kind) {
    setError("");
    if (!wantPasskey) {
      setVerified(null);
      setModal(kind);
      return;
    }
    if (!prepared || Date.now() - prepared.at > 4 * 60 * 1000) {
      preparePasskey();
      setError("กำลังเตรียมการยืนยันด้วย passkey — กรุณากดอีกครั้ง");
      return;
    }
    const flow = prepared;
    setPrepared(null);
    try {
      const credential = await assertPasskey(flow.options);
      setVerified({ flowId: flow.flow_id, credential });
      setModal(kind);
    } catch (err) {
      const msg = passkeyErrorMessage(err) || (err?.name === "NotAllowedError" ? "ยกเลิกการยืนยันด้วย passkey แล้ว" : null);
      if (msg) {
        setError(passkeyRequired ? msg
          : `${msg} — ถ้าอุปกรณ์นี้ไม่มี passkey ให้เอาติ๊ก "ยืนยันตัวตนด้วย Passkey" ออก แล้วกดลงนามอีกครั้ง`);
      }
      preparePasskey();
    }
  }

  // เปิดมาแล้วไปที่หน้าที่มีกล่องลายเซ็นของคนที่ถึงคิว
  useEffect(() => {
    const target =
      req?.steps.find((s) => s.order === req.my_step_order) || req?.steps.find((s) => s.status === "pending");
    if (target) setPage(target.page);
  }, [req?.id, req?.current_order, req?.my_step_order]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(action, success) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await action();
      setModal(null);
      setVerified(null);
      setNotice(res?.warning ? `${success} — หมายเหตุ: ${res.warning}` : success);
      setReport(null);
      setVersion((v) => v + 1);
      await load();
    } catch (err) {
      setError(err.message);
      if (verified) {
        // challenge ใช้ได้ครั้งเดียว — ต้องสแกนใหม่
        setVerified(null);
        setModal(null);
        preparePasskey();
      }
    } finally {
      setBusy(false);
    }
  }

  if (!req) {
    return (
      <div className="min-h-screen bg-slate-50">
        <SigningHeader title="คำขอลงนาม" />
        <main className="max-w-6xl mx-auto px-4 py-6 text-sm">{error ? <p className="text-red-600">{error}</p> : <p className="text-gray-500">กำลังโหลด...</p>}</main>
      </div>
    );
  }

  const size = req.page_sizes[page] || [595, 842];
  const scale = previewScale(size[0], previewWidth);
  const boxes = req.steps
    .filter((s) => s.page === page && s.status !== "signed")
    .map((s) => ({
      id: s.order,
      rect: s.rect,
      label: `${s.stage}. ${s.signer.name}${myStep?.order === s.order ? " (คุณ)" : ""}`,
      className: BOX_STYLE[s.status],
    }));
  const currentSignerName = req.waiting_for?.length ? req.waiting_for.join(", ") : "ผู้ลงนาม";
  const signTypeAllowed = (t) => myStep && (myStep.sign_type === "either" || myStep.sign_type === t);
  const hasTop = Boolean(error || notice || myStep);

  return (
    <div className="min-h-screen bg-slate-50">
      <SigningHeader title={req.title} />
      {/* มือถือ: แจ้งเตือน/ปุ่มลงนาม → เอกสาร → รายละเอียด · เดสก์ท็อป: เอกสารซ้าย แผงขวา */}
      <main className="max-w-6xl mx-auto px-3 sm:px-4 py-4 sm:py-6 grid gap-4 sm:gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
        {hasTop && (
          <div className="space-y-4 lg:col-start-2 lg:row-start-1">
            {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm" role="alert">{error}</div>}
            {notice && <div className="p-3 rounded-lg bg-green-50 text-green-800 text-sm" role="status">{notice}</div>}
            {myStep && (
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-2">
                <p className="text-sm font-semibold text-blue-900">ถึงคิวคุณลงนาม (ลำดับที่ {myStep.order})</p>
                <p className="text-xs text-blue-800">ประเภท: {SIGN_TYPES[myStep.sign_type]} · กล่องลายเซ็นอยู่หน้า {myStep.page + 1}</p>
                {passkeyRequired && hasPasskey === false ? (
                  <div className="p-2.5 rounded-lg bg-amber-50 text-amber-900 border border-amber-200 text-xs" data-testid="passkey-needed">
                    ผู้ส่งกำหนดให้<strong>ยืนยันตัวตนด้วย Passkey</strong> ก่อนลงนาม แต่บัญชีนี้ยังไม่มี passkey —{" "}
                    <Link to="/security" className="underline font-medium">เพิ่ม passkey ที่หน้าความปลอดภัย</Link> แล้วกลับมาที่หน้านี้
                  </div>
                ) : passkeyRequired ? (
                  <p className="text-xs text-blue-900" data-testid="passkey-required">🔑 ผู้ส่งกำหนดให้ยืนยันตัวตนด้วย Passkey (สแกนหน้า/นิ้ว) ก่อนลงนาม</p>
                ) : hasPasskey ? (
                  <label className="flex items-start gap-2 text-xs text-blue-900">
                    <input type="checkbox" className="mt-0.5" checked={usePasskey} onChange={(e) => setUsePasskey(e.target.checked)} />
                    <span>ยืนยันตัวตนด้วย Passkey ก่อนลงนาม (บันทึกในหนังสือรับรองการลงนาม)</span>
                  </label>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  {signTypeAllowed("electronic") && (
                    <button className="px-3 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50" disabled={busy || (passkeyRequired && !hasPasskey)} onClick={() => startSigning("electronic")}>
                      ลงนามอิเล็กทรอนิกส์
                    </button>
                  )}
                  {signTypeAllowed("digital") && (
                    <button className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm disabled:opacity-50" disabled={busy || (passkeyRequired && !hasPasskey)} onClick={() => startSigning("digital")}>
                      ลงนามดิจิทัล (ใบรับรอง)
                    </button>
                  )}
                  <button className="px-3 py-2 rounded-lg border border-red-300 text-red-600 text-sm bg-white disabled:opacity-50" disabled={busy} onClick={() => setModal("reject")}>
                    ปฏิเสธ
                  </button>
                </div>
                {myStep.page !== page && (
                  <button className="text-xs text-blue-700 underline" onClick={() => setPage(myStep.page)}>ไปหน้าที่มีกล่องลายเซ็นของคุณ</button>
                )}
                {busy && <p className="text-xs text-blue-800">กำลังลงนาม...</p>}
              </div>
            )}
          </div>
        )}

        <section className={`min-w-0 lg:col-start-1 lg:row-start-1 ${hasTop ? "lg:row-span-2" : ""}`}>
          <div className="flex items-center justify-between gap-2 mb-3 text-sm">
            <StatusBadge status={req.status} />
            {req.page_sizes.length > 1 && (
              <div className="flex items-center gap-1.5" aria-label="เปลี่ยนหน้า">
                <button className="w-9 h-9 rounded-lg border border-gray-300 bg-white disabled:opacity-40" aria-label="หน้าก่อน" disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>
                <span className="min-w-[4.5rem] text-center text-gray-700">หน้า {page + 1} / {req.page_sizes.length}</span>
                <button className="w-9 h-9 rounded-lg border border-gray-300 bg-white disabled:opacity-40" aria-label="หน้าถัดไป" disabled={page >= req.page_sizes.length - 1} onClick={() => setPage(page + 1)}>›</button>
              </div>
            )}
          </div>
          <div ref={previewRef} className="overflow-hidden rounded-lg">
            <SignaturePagePreview
              imageUrl={signingRequestPageUrl(req.id, page, previewZoom(scale), `${version}-${req.steps.filter((s) => s.status === "signed").length}`)}
              pageWidthPt={size[0]}
              pageHeightPt={size[1]}
              scale={scale}
              boxes={boxes}
            />
          </div>
        </section>

        <aside className={`min-w-0 space-y-4 lg:col-start-2 ${hasTop ? "lg:row-start-2" : "lg:row-start-1"}`}>

          <div className="bg-white rounded-xl border border-gray-200 p-4 text-sm space-y-1">
            <p><span className="text-gray-500">ผู้ส่ง:</span> {req.is_owner ? "คุณ" : `${req.owner.name} (${req.owner.email})`}</p>
            <p><span className="text-gray-500">ส่งเมื่อ:</span> {formatDateTime(req.created_at)}</p>
            {req.due_at && <p><span className="text-gray-500">ครบกำหนด:</span> <DueDate request={req} /></p>}
            {req.completed_at && <p><span className="text-gray-500">ครบเมื่อ:</span> {formatDateTime(req.completed_at)}</p>}
            {req.message && <p className="mt-2 p-2 bg-gray-50 rounded whitespace-pre-wrap">{req.message}</p>}
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">ลำดับผู้ลงนาม</h2>
            {req.steps.some((s) => s.stage !== s.order) && (
              <p className="text-xs text-gray-500 -mt-2 mb-3">ตัวเลขคือขั้น — คนที่อยู่ขั้นเดียวกันลงนามพร้อมกันได้</p>
            )}
            <ol className="space-y-3" data-testid="signing-steps">
              {req.steps.map((s) => (
                <li key={s.order} className="text-sm">
                  <div className="flex items-start gap-2">
                    <span className={`mt-0.5 w-6 h-6 shrink-0 rounded-full flex items-center justify-center text-xs font-bold border-2 ${BOX_STYLE[s.status]}`}>{s.stage}</span>
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900 truncate">{s.signer.name}</p>
                      <p className="text-xs text-gray-500 truncate">{s.signer.email} · {SIGN_TYPES[s.sign_type]}</p>
                      {s.signer.invited && (
                        <p className="text-xs text-amber-700">✉ ส่งคำเชิญแล้ว — รอสมัครสมาชิกด้วยอีเมลนี้</p>
                      )}
                      <p className="text-xs mt-0.5">
                        <span className={s.status === "signed" ? "text-green-700" : s.status === "rejected" ? "text-red-600" : s.status === "pending" ? "text-blue-700" : "text-gray-500"}>
                          {STEP_STATUS[s.status]}
                        </span>
                        {s.signed_at && <span className="text-gray-500"> · {formatDateTime(s.signed_at)}</span>}
                        {s.signed_type && <span className="text-gray-500"> · {s.signed_type === "digital" ? "ดิจิทัล" : "อิเล็กทรอนิกส์"}</span>}
                      </p>
                      {s.verified_method === "passkey" ? (
                        <p className="text-xs text-indigo-700">🔑 ยืนยันตัวตนด้วย Passkey ({s.verified_detail})</p>
                      ) : s.require_passkey && s.status !== "signed" ? (
                        <p className="text-xs text-gray-500">🔑 ต้องยืนยันด้วย Passkey</p>
                      ) : null}
                      {s.cert_subject && <p className="text-xs text-gray-500 truncate" title={s.cert_subject}>ผู้ลงนามในใบรับรอง: {s.cert_subject}</p>}
                      {s.comment && <p className="text-xs text-red-600 mt-0.5">เหตุผล: {s.comment}</p>}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
            <button
              className="w-full py-2 rounded-lg border border-gray-300 text-sm hover:bg-gray-50"
              onClick={() => downloadSigningDocument(req.id, `${req.title}.pdf`).then(({ blob, filename }) => saveBlob(blob, filename)).catch((e) => setError(e.message))}
            >
              ดาวน์โหลดเอกสาร (เวอร์ชันล่าสุด)
            </button>
            <button
              className="w-full py-2 rounded-lg border border-gray-300 text-sm hover:bg-gray-50"
              onClick={() => verifySigningRequest(req.id).then((r) => setReport(r.signatures)).catch((e) => setError(e.message))}
            >
              ตรวจสอบลายเซ็นในเอกสาร
            </button>
            <button
              className="w-full py-2 rounded-lg border border-gray-300 text-sm hover:bg-gray-50"
              title="สรุปผู้ลงนาม เวลา IP และค่า SHA-256 ของเอกสาร (PDF แยก ลงนามโดยระบบ)"
              onClick={() =>
                downloadSigningEvidence(req.id, `${req.title} (หลักฐานการลงนาม).pdf`)
                  .then(({ blob, filename }) => saveBlob(blob, filename))
                  .catch((e) => setError(e.message))
              }
            >
              ดาวน์โหลดหนังสือรับรองการลงนาม
            </button>
            {report && (
              <ul className="text-xs space-y-1" data-testid="verify-report">
                {report.map((r) => (
                  <li key={r.field_name} className={!r.signed ? "text-gray-500" : r.intact && r.valid && r.modification_ok ? "text-green-700" : "text-red-600"}>
                    {r.field_name}: {!r.signed ? "ยังไม่ลงนาม" : r.intact && r.valid && r.modification_ok ? `ถูกต้อง (${r.signer})` : "ลายเซ็นไม่ถูกต้อง หรือเอกสารถูกแก้หลังลงนาม"}
                    {r.timestamp && <span className="text-gray-500"> · ประทับเวลาโดย TSA {formatDateTime(r.timestamp)}</span>}
                  </li>
                ))}
                <li className="text-gray-500">* ตรวจความครบถ้วนของเอกสารและลายเซ็น ไม่ได้ตรวจว่าผู้ออกใบรับรองเป็นหน่วยงานที่เชื่อถือได้</li>
              </ul>
            )}
            {req.is_owner && req.status === "in_progress" && (
              <>
                <button
                  className="w-full py-2 rounded-lg border border-blue-200 text-blue-700 text-sm hover:bg-blue-50 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => run(() => remindSigningRequest(req.id), `ส่งเตือน ${currentSignerName} แล้ว`)}
                >
                  ส่งเตือนผู้ลงนาม
                </button>
                {req.last_reminded_at && (
                  <p className="text-xs text-gray-500">เตือนล่าสุด: {formatDateTime(req.last_reminded_at)}</p>
                )}
              </>
            )}
            {req.is_owner && req.status === "in_progress" && (
              <button className="w-full py-2 rounded-lg border border-red-200 text-red-600 text-sm hover:bg-red-50" onClick={() => setModal("cancel")}>
                ยกเลิกคำขอนี้
              </button>
            )}
            {req.is_owner && req.status === "completed" && (
              <p className="text-xs text-green-700">ไฟล์ที่ลงนามครบแล้วอยู่ในหน้า "เอกสารของฉัน" — อย่าแก้ไขเนื้อหาไฟล์นั้น เพราะลายเซ็นจะไม่ถูกต้อง</p>
            )}
          </div>

          <details className="bg-white rounded-xl border border-gray-200 p-4 text-xs">
            <summary className="cursor-pointer text-sm font-semibold text-gray-800">ประวัติ (หลักฐาน)</summary>
            <ul className="mt-2 space-y-1.5">
              {(req.events || []).map((e, i) => (
                <li key={i} className="text-gray-600">
                  <span className="text-gray-400">{formatDateTime(e.created_at)}</span> · {EVENT_LABELS[e.action] || e.action}
                  {e.detail ? ` — ${e.detail}` : ""}
                  {e.sha256_after && <span className="block text-gray-400 break-all">SHA-256: {e.sha256_after}</span>}
                </li>
              ))}
            </ul>
          </details>
        </aside>
      </main>

      {modal === "electronic" && (
        <ElectronicSignModal
          onCancel={() => { setModal(null); setVerified(null); if (wantPasskey) preparePasskey(); }}
          onConfirm={(_base64, dataUrl) =>
            run(() => signSigningRequest(req.id, { signType: "electronic", signatureBlob: dataUrlToBlob(dataUrl), passkey: verified }), "ลงนามเรียบร้อยแล้ว")
          }
        />
      )}
      {modal === "digital" && (
        <DigitalSignModal
          onCancel={() => { setModal(null); setVerified(null); if (wantPasskey) preparePasskey(); }}
          onConfirm={(file, password, reason, _location, _contact, _name, imageFile) =>
            run(() => signSigningRequest(req.id, { signType: "digital", pfxFile: file, password, reason, signatureBlob: imageFile, passkey: verified }), "ลงนามดิจิทัลเรียบร้อยแล้ว")
          }
        />
      )}
      {(modal === "reject" || modal === "cancel") && (
        <div className="modal-overlay">
          <div className="modal-card">
            <h2 className="modal-title">{modal === "reject" ? "ปฏิเสธการลงนาม" : "ยกเลิกคำขอลงนาม"}</h2>
            {modal === "reject" ? (
              <>
                <p className="modal-subtitle">ผู้ส่งจะได้รับแจ้งพร้อมเหตุผล และคำขอนี้จะสิ้นสุด</p>
                <textarea className="modal-input" rows={3} placeholder="เหตุผล" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
              </>
            ) : (
              <p className="modal-subtitle">ผู้ลงนามที่ยังไม่ได้ลงนามจะลงนามต่อไม่ได้ ต้องการยกเลิกหรือไม่?</p>
            )}
            <div className="modal-actions">
              <button className="secondary-btn" onClick={() => setModal(null)}>ปิด</button>
              <button
                className="primary-btn"
                disabled={busy || (modal === "reject" && !rejectReason.trim())}
                onClick={() =>
                  modal === "reject"
                    ? run(() => rejectSigningRequest(req.id, rejectReason.trim()), "ปฏิเสธการลงนามแล้ว")
                    : run(() => cancelSigningRequest(req.id), "ยกเลิกคำขอแล้ว")
                }
              >
                ยืนยัน
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
