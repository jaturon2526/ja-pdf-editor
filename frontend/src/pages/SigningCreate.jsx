// สร้างคำขอลงนาม: เพิ่มผู้ลงนามตามลำดับ + วางกล่องลายเซ็นของแต่ละคนบนหน้าเอกสาร แล้วส่ง
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { createSigningRequest, getSigningSourceInfo, lookupSigner, signingSourcePageUrl } from "../api/signing.js";
import SignaturePagePreview from "../components/signing/SignaturePagePreview.jsx";
import SigningHeader from "../components/signing/SigningHeader.jsx";
import { SIGN_TYPES } from "../components/signing/labels.jsx";
import { previewScale, previewZoom, useElementWidth } from "../components/signing/useElementWidth.js";

const BOX_W = 160;
const BOX_H = 60;
const COLORS = ["border-blue-500 bg-blue-100/60 text-blue-900", "border-emerald-500 bg-emerald-100/60 text-emerald-900",
  "border-amber-500 bg-amber-100/60 text-amber-900", "border-purple-500 bg-purple-100/60 text-purple-900",
  "border-rose-500 bg-rose-100/60 text-rose-900"];

let nextKey = 1;
const newSigner = () => ({
  key: nextKey++, email: "", user: null, lookupError: "", signType: "either", page: null, rect: null, parallel: false, requirePasskey: false,
});
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MAX_SIGNERS = 20; // ตรงกับ backend signing_service.MAX_SIGNERS

// ค่า min ของ datetime-local = ตอนนี้ (เวลาเครื่องผู้ใช้)
function localInputNow() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

// เลขขั้นของแต่ละคน: ติ๊ก "ลงนามพร้อมกับคนก่อนหน้า" = ขั้นเดียวกับคนก่อนหน้า
function stagesOf(signers) {
  let stage = 0;
  return signers.map((s, i) => (i === 0 || !s.parallel ? ++stage : stage));
}

export default function SigningCreate() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const fileId = Number(params.get("file"));
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [dueLocal, setDueLocal] = useState(""); // ค่า datetime-local (เวลาเครื่องผู้ใช้) — ว่าง = ไม่กำหนด
  const [signers, setSigners] = useState([newSigner()]);
  const [placing, setPlacing] = useState(null); // key ของผู้ลงนามที่กำลังวางกล่อง
  const [submitting, setSubmitting] = useState(false);
  const [previewRef, previewWidth] = useElementWidth();

  useEffect(() => {
    if (!fileId) {
      setError("ไม่ได้เลือกไฟล์");
      return;
    }
    getSigningSourceInfo(fileId)
      .then((data) => {
        setInfo(data);
        setTitle((current) => current || data.filename.replace(/\.pdf$/i, "")); // ไม่ทับชื่อที่ผู้ใช้พิมพ์ไปก่อนโหลดเสร็จ
      })
      .catch((err) => setError(err.message));
  }, [fileId]);

  const stages = stagesOf(signers);
  const size = info?.page_sizes?.[page] || [595, 842];
  const scale = previewScale(size[0], previewWidth);

  const boxes = useMemo(
    () =>
      signers
        .map((s, i) => ({ s, i }))
        .filter(({ s }) => s.rect && s.page === page)
        .map(({ s, i }) => ({
          id: s.key,
          rect: s.rect,
          label: `${stages[i]}. ${s.user?.name || s.email || "ผู้ลงนาม"}`,
          editable: true,
          className: COLORS[i % COLORS.length],
        })),
    [signers, page], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const placingIndex = signers.findIndex((s) => s.key === placing);
  const placingGhost =
    placingIndex >= 0
      ? {
          width: BOX_W,
          height: BOX_H,
          label: `${stages[placingIndex]}. ${signers[placingIndex].user?.name || signers[placingIndex].email || "ผู้ลงนาม"}`,
          className: COLORS[placingIndex % COLORS.length],
        }
      : null;

  // Esc ยกเลิกการวางกล่อง
  useEffect(() => {
    if (placing == null) return undefined;
    const onKey = (e) => e.key === "Escape" && setPlacing(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [placing]);

  function update(key, patch) {
    setSigners((list) => list.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  }

  async function checkEmail(signer) {
    const email = signer.email.trim();
    if (!email) return;
    if (!EMAIL_RE.test(email)) {
      update(signer.key, { user: null, lookupError: "รูปแบบอีเมลไม่ถูกต้อง" });
      return;
    }
    try {
      const user = await lookupSigner(email);
      // ยังไม่มีบัญชี → เชิญทางอีเมล (ผูกบัญชีให้เองเมื่อสมัครด้วยอีเมลนี้)
      update(signer.key, { user: user || { id: null, email: email.toLowerCase(), name: email, invited: true }, lookupError: "" });
    } catch (err) {
      update(signer.key, { user: null, lookupError: err.message });
    }
  }

  function move(index, delta) {
    setSigners((list) => {
      const next = [...list];
      const target = index + delta;
      if (target < 0 || target >= next.length) return list;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function place(xPt, yPt) {
    if (placing == null) return;
    const [w, h] = size;
    const bw = Math.min(BOX_W, w); // หน้าเล็กกว่ากล่อง (ใบเสร็จ/สลิป) — ไม่ให้กล่องล้นออกนอกหน้า
    const bh = Math.min(BOX_H, h);
    const x0 = Math.max(0, Math.min(xPt - bw / 2, w - bw));
    const y0 = Math.max(0, Math.min(yPt - bh / 2, h - bh));
    update(placing, { page, rect: { x0, y0, x1: x0 + bw, y1: y0 + bh } });
    setPlacing(null);
  }

  const problems = [];
  if (!signers.length) problems.push("เพิ่มผู้ลงนามอย่างน้อย 1 คน");
  signers.forEach((s, i) => {
    if (!s.user) problems.push(`ผู้ลงนามคนที่ ${i + 1}: ตรวจสอบอีเมลก่อน`);
    else if (!s.rect) problems.push(`ผู้ลงนามคนที่ ${i + 1}: ยังไม่ได้วางกล่องลายเซ็น`);
  });
  const emails = signers.filter((s) => s.user).map((s) => s.user.email.toLowerCase());
  if (new Set(emails).size !== emails.length) problems.push("มีผู้ลงนามซ้ำกัน");
  const dueDate = dueLocal ? new Date(dueLocal) : null;
  if (dueDate && !(dueDate.getTime() > Date.now())) problems.push("วันครบกำหนดต้องเป็นเวลาในอนาคต");

  async function submit() {
    setSubmitting(true);
    setError("");
    try {
      const created = await createSigningRequest({
        fileId,
        title,
        message,
        dueAt: dueDate ? dueDate.toISOString() : null,
        steps: signers.map((s, i) => ({
          email: s.user.email, sign_type: s.signType, page: s.page, parallel: i > 0 && s.parallel,
          require_passkey: s.requirePasskey, ...s.rect,
        })),
      });
      navigate(`/signing/${created.id}`);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <SigningHeader title="ส่งเอกสารให้ลงนาม" />
      <main className="max-w-6xl mx-auto px-3 sm:px-4 py-4 sm:py-6 grid gap-4 sm:gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="min-w-0">
          {info && (
            <>
              <div className="flex items-center justify-between mb-3 text-sm">
                <span className="text-gray-600 truncate">{info.filename}</span>
                <div className="flex items-center gap-2">
                  <button className="px-2 py-1 rounded border border-gray-300 bg-white disabled:opacity-40" disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>
                  <span>หน้า {page + 1} / {info.page_sizes.length}</span>
                  <button className="px-2 py-1 rounded border border-gray-300 bg-white disabled:opacity-40" disabled={page >= info.page_sizes.length - 1} onClick={() => setPage(page + 1)}>›</button>
                </div>
              </div>
              {placing != null && (
                <div className="mb-3 p-2 rounded bg-blue-50 text-blue-800 text-sm">
                  เลื่อนเมาส์ไปตำแหน่งที่ต้องการแล้วคลิกเพื่อวางกล่องลายเซ็น (เปลี่ยนหน้าได้ก่อนคลิก · กด Esc เพื่อยกเลิก) ·{" "}
                  <button className="underline" onClick={() => setPlacing(null)}>ยกเลิก</button>
                </div>
              )}
              <div ref={previewRef} className="overflow-auto">
                <SignaturePagePreview
                  imageUrl={signingSourcePageUrl(fileId, page, previewZoom(scale))}
                  pageWidthPt={size[0]}
                  pageHeightPt={size[1]}
                  scale={scale}
                  boxes={boxes}
                  placing={placing != null}
                  ghost={placingGhost}
                  onPlace={place}
                  onBoxChange={(key, rect) => update(key, { rect })}
                />
              </div>
            </>
          )}
        </section>

        <aside className="space-y-4">
          {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <label className="block text-sm">
              <span className="text-gray-700">ชื่อเอกสาร</span>
              <input className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2" value={title} maxLength={255} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="text-gray-700">ข้อความถึงผู้ลงนาม (ไม่บังคับ)</span>
              <textarea className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2" rows={2} maxLength={2000} value={message} onChange={(e) => setMessage(e.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="text-gray-700">ครบกำหนดลงนาม (ไม่บังคับ)</span>
              <input
                type="datetime-local"
                aria-label="ครบกำหนดลงนาม"
                className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                value={dueLocal}
                min={localInputNow()}
                onChange={(e) => setDueLocal(e.target.value)}
              />
              <span className="block mt-1 text-xs text-gray-500">ระบบจะเตือนผู้ลงนามเมื่อใกล้ครบกำหนด และแจ้งคุณเมื่อเลยกำหนด</span>
            </label>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">ผู้ลงนาม (เรียงตามลำดับขั้น)</h2>
            <ol className="space-y-3">
              {signers.map((s, i) => (
                <li key={s.key} className="border border-gray-300 rounded-lg p-3 space-y-2" data-testid="signer-row">
                  <div className="flex items-center gap-2">
                    <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border-2 ${COLORS[i % COLORS.length]}`} title={`ขั้นที่ ${stages[i]}`}>{stages[i]}</span>
                    <input
                      type="email"
                      placeholder="อีเมลผู้ลงนาม"
                      className="flex-1 min-w-0 border border-gray-300 rounded px-2 py-1 text-sm"
                      value={s.email}
                      onChange={(e) => update(s.key, { email: e.target.value, user: null, lookupError: "" })}
                      onBlur={() => checkEmail(s)}
                      onKeyDown={(e) => e.key === "Enter" && checkEmail(s)}
                    />
                    <button title="เลื่อนขึ้น" className="text-gray-500 disabled:opacity-30" disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                    <button title="เลื่อนลง" className="text-gray-500 disabled:opacity-30" disabled={i === signers.length - 1} onClick={() => move(i, 1)}>↓</button>
                    <button title="ลบ" className="text-red-500" onClick={() => setSigners(signers.filter((x) => x.key !== s.key))}>✕</button>
                  </div>
                  {s.user && !s.user.invited && <p className="text-xs text-green-700">✓ {s.user.name}</p>}
                  {s.user?.invited && (
                    <p className="text-xs text-amber-700" data-testid="invite-note">
                      ✉ ยังไม่มีบัญชีในระบบ — จะส่งอีเมลเชิญให้สมัครด้วยอีเมลนี้ แล้วลงนามได้เมื่อถึงคิว
                    </p>
                  )}
                  {i > 0 && (
                    <label className="flex items-center gap-2 text-xs text-gray-700">
                      <input type="checkbox" checked={s.parallel} onChange={(e) => update(s.key, { parallel: e.target.checked })} />
                      ลงนามพร้อมกับคนก่อนหน้า (ขั้นเดียวกัน ใครเซ็นก่อนก็ได้)
                    </label>
                  )}
                  <label className="flex items-start gap-2 text-xs text-gray-700" title="ผู้ลงนามต้องสแกนหน้า/นิ้วด้วย passkey ของบัญชีตัวเองก่อนลงนาม — บันทึกลงหนังสือรับรอง">
                    <input type="checkbox" className="mt-0.5" checked={s.requirePasskey} onChange={(e) => update(s.key, { requirePasskey: e.target.checked })} />
                    <span>
                      ต้องยืนยันตัวตนด้วย Passkey ก่อนลงนาม
                      {s.requirePasskey && <span className="block text-gray-500">ผู้ลงนามต้องมี passkey ในบัญชี (เพิ่มได้ที่เมนูความปลอดภัย)</span>}
                    </span>
                  </label>
                  {s.lookupError && <p className="text-xs text-red-600">{s.lookupError}</p>}
                  <select className="w-full border border-gray-300 rounded px-2 py-1 text-sm" value={s.signType} onChange={(e) => update(s.key, { signType: e.target.value })}>
                    {Object.entries(SIGN_TYPES).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
                  </select>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500">{s.rect ? `กล่องลายเซ็นอยู่หน้า ${s.page + 1}` : "ยังไม่ได้วางกล่องลายเซ็น"}</span>
                    <button
                      className={`px-2 py-1 rounded ${placing === s.key ? "bg-blue-600 text-white" : "bg-blue-50 text-blue-700 hover:bg-blue-100"}`}
                      onClick={() => {
                        setPlacing(placing === s.key ? null : s.key);
                        if (s.rect) setPage(s.page);
                      }}
                    >
                      {s.rect ? "วางใหม่" : "วางกล่องลายเซ็น"}
                    </button>
                  </div>
                </li>
              ))}
            </ol>
            {signers.length < MAX_SIGNERS && <button className="mt-3 w-full border-2 border-dashed border-gray-300 rounded-lg py-2 text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600" onClick={() => setSigners([...signers, newSigner()])}>
              + เพิ่มผู้ลงนาม
            </button>}
          </div>

          {problems.length > 0 && (
            <ul className="text-xs text-gray-500 list-disc pl-5 space-y-0.5">
              {problems.map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}
          <button
            className="w-full py-2.5 rounded-lg bg-blue-600 text-white font-medium disabled:opacity-50"
            disabled={!info || problems.length > 0 || submitting}
            onClick={submit}
          >
            {submitting ? "กำลังส่ง..." : `ส่งให้ลงนาม (${signers.length} คน)`}
          </button>
          <p className="text-xs text-gray-500">
            หลังส่งแล้วเอกสารจะถูกล็อก แก้ไขเนื้อหาไม่ได้ ผู้ลงนามลงนามได้เมื่อถึงขั้นของตัวเอง (คนในขั้นเดียวกันลงนามพร้อมกันได้) เมื่อครบแล้วไฟล์ที่ลงนามจะกลับมาอยู่ในเอกสารของคุณ
          </p>
        </aside>
      </main>
    </div>
  );
}
