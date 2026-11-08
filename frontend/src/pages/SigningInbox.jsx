// รายการคำขอลงนาม: รอฉันลงนาม / ที่ฉันส่ง / ทั้งหมด
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getSigningPreferences, listSigningRequests, setSigningPreferences } from "../api/signing.js";
import { getLineStatus } from "../api/line.js";
import SigningHeader from "../components/signing/SigningHeader.jsx";
import { DueDate, StatusBadge, formatDateTime } from "../components/signing/labels.jsx";

const TABS = [
  { key: "to_sign", label: "รอฉันลงนาม" },
  { key: "sent", label: "ที่ฉันส่ง" },
  { key: "all", label: "ทั้งหมด" },
];

function progress(r) {
  const signed = r.steps.filter((s) => s.status === "signed").length;
  return `${signed}/${r.steps.length}`;
}

function nextSigner(r) {
  return r.waiting_for?.length ? r.waiting_for.join(", ") : "-";
}

export default function SigningInbox() {
  const [params, setParams] = useSearchParams();
  const box = TABS.some((t) => t.key === params.get("box")) ? params.get("box") : "to_sign";
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [emailOn, setEmailOn] = useState(null); // null = ยังโหลดไม่เสร็จ
  const [savingPref, setSavingPref] = useState(false);
  const [line, setLine] = useState(null); // สถานะ LINE (null = ปิดใช้/โหลดไม่ได้)

  useEffect(() => {
    getSigningPreferences()
      .then((p) => setEmailOn(p.email_notifications))
      .catch(() => setEmailOn(null));
    getLineStatus()
      .then((s) => setLine(s.enabled ? s : null))
      .catch(() => setLine(null));
  }, []);

  async function toggleEmail(enabled) {
    setSavingPref(true);
    try {
      const p = await setSigningPreferences({ emailNotifications: enabled });
      setEmailOn(p.email_notifications);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingPref(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError("");
    listSigningRequests(box)
      .then((data) => !cancelled && setItems(data))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [box]);

  return (
    <div className="min-h-screen bg-slate-50">
      <SigningHeader title="การลงนามเอกสาร" backTo="/dashboard" />
      <main className="max-w-6xl mx-auto px-3 sm:px-4 py-4 sm:py-6">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <div className="flex gap-1 bg-white rounded-lg border border-gray-200 p-1 w-full sm:w-auto" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={box === t.key}
                onClick={() => setParams({ box: t.key })}
                className={`flex-1 sm:flex-none px-4 py-1.5 rounded-md text-sm font-medium whitespace-nowrap ${box === t.key ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"}`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex flex-col items-start sm:items-end gap-1">
          {emailOn !== null && (
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={emailOn}
                disabled={savingPref}
                onChange={(e) => toggleEmail(e.target.checked)}
              />
              รับอีเมลแจ้งเตือนการลงนาม
            </label>
          )}
          {line && (
            <Link to="/security" className="text-xs text-green-700 hover:underline">
              {line.linked && line.notifications ? "แจ้งเตือนส่งทาง LINE แทนอีเมล · ตั้งค่า →" : "รับแจ้งเตือนทาง LINE แทน →"}
            </Link>
          )}
          </div>
        </div>
        <p className="text-sm text-gray-500 mb-4">ส่งเอกสารให้ลงนามได้จากการ์ด "ส่งเอกสารให้ลงนาม" หรือเมนู ☰ ของไฟล์ในหน้าเอกสารของฉัน</p>

        {error && <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm mb-4">{error}</div>}
        {items === null && !error && <p className="text-sm text-gray-500">กำลังโหลด...</p>}
        {items && items.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-500 text-sm">
            {box === "to_sign" ? "ไม่มีเอกสารที่รอคุณลงนาม" : "ยังไม่มีรายการ"}
          </div>
        )}
        {items && items.length > 0 && (
          <ul className="md:hidden space-y-3" data-testid="signing-cards">
            {items.map((r) => (
              <li key={r.id}>
                <Link to={`/signing/${r.id}`} className="block bg-white rounded-xl border border-gray-200 p-4 active:bg-blue-50">
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-semibold text-gray-900 leading-snug min-w-0 break-words">{r.title}</p>
                    <StatusBadge status={r.status} />
                  </div>
                  {r.my_turn && <span className="inline-block mt-2 text-xs text-white bg-blue-600 rounded px-1.5 py-0.5">ถึงคิวคุณ</span>}
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                    <dt className="text-gray-500">ผู้ส่ง</dt>
                    <dd className="text-gray-800 truncate">{r.is_owner ? "คุณ" : r.owner.name}</dd>
                    <dt className="text-gray-500">ลงนามแล้ว</dt>
                    <dd className="text-gray-800">{progress(r)}</dd>
                    {r.status === "in_progress" && (
                      <>
                        <dt className="text-gray-500">รอ</dt>
                        <dd className="text-gray-800 truncate">{nextSigner(r)}</dd>
                        {r.due_at && (
                          <>
                            <dt className="text-gray-500">ครบกำหนด</dt>
                            <dd><DueDate request={r} /></dd>
                          </>
                        )}
                      </>
                    )}
                    <dt className="text-gray-500">ส่งเมื่อ</dt>
                    <dd className="text-gray-600">{formatDateTime(r.created_at)}</dd>
                  </dl>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {items && items.length > 0 && (
          <div className="hidden md:block bg-white rounded-xl border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">เอกสาร</th>
                  <th className="text-left px-4 py-3 font-medium">ผู้ส่ง</th>
                  <th className="text-left px-4 py-3 font-medium">สถานะ</th>
                  <th className="text-left px-4 py-3 font-medium">ลงนามแล้ว</th>
                  <th className="text-left px-4 py-3 font-medium">รอ</th>
                  <th className="text-left px-4 py-3 font-medium">ครบกำหนด</th>
                  <th className="text-left px-4 py-3 font-medium">ส่งเมื่อ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((r) => (
                  <tr key={r.id} className="hover:bg-blue-50/40">
                    <td className="px-4 py-3">
                      <Link to={`/signing/${r.id}`} className="font-medium text-blue-700 hover:underline">{r.title}</Link>
                      {r.my_turn && <span className="ml-2 text-xs text-white bg-blue-600 rounded px-1.5 py-0.5">ถึงคิวคุณ</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-700">{r.is_owner ? "คุณ" : r.owner.name}</td>
                    <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3 text-gray-700">{progress(r)}</td>
                    <td className="px-4 py-3 text-gray-700">{r.status === "in_progress" ? nextSigner(r) : "-"}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{r.status === "in_progress" ? <DueDate request={r} /> : "-"}</td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{formatDateTime(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
