// สร้างเอกสารอัตโนมัติ (Mail Merge): Template Word + ไฟล์ข้อมูล → Word/PDF แยกไฟล์ (.zip) หรือรวมไฟล์เดียว
import { useEffect, useState } from "react";
import * as api from "../api.js";

const SAMPLES = [
  ["template_flat.docx", "Template แบบง่าย"],
  ["data_flat.xlsx", "ข้อมูล Excel"],
  ["data_flat.csv", "ข้อมูล CSV"],
  ["template.docx", "Template ขั้นสูง (ตาราง/เงื่อนไข)"],
  ["data.json", "ข้อมูล JSON"],
  ["template_qr.docx", "Template QR/บาร์โค้ด"],
  ["data_qr.xlsx", "ข้อมูลบัตรพนักงาน"],
];
const label = "block text-sm font-medium text-gray-700 mb-1";
const input = "block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:text-gray-400";
const isText = (f) => f && /\.(csv|txt)$/i.test(f.name);

function filenameFrom(res, fallback) {
  const cd = res.headers.get("Content-Disposition") || "";
  const utf8 = cd.match(/filename\*=utf-8''([^;]+)/i);
  if (utf8) return decodeURIComponent(utf8[1]);
  const ascii = cd.match(/filename="?([^";]+)"?/i);
  return ascii ? ascii[1] : fallback;
}

export default function AutoGenModal({ onClose }) {
  const [templateFile, setTemplateFile] = useState(null);
  const [dataFile, setDataFile] = useState(null);
  const [outputFormat, setOutputFormat] = useState("docx");
  const [splitFiles, setSplitFiles] = useState(true);
  const [filenameField, setFilenameField] = useState("");
  const [outputFilename, setOutputFilename] = useState("");
  const [usePassword, setUsePassword] = useState(false);
  const [passwordField, setPasswordField] = useState("");
  const [csvDelimiter, setCsvDelimiter] = useState("auto");
  const [csvEncoding, setCsvEncoding] = useState("auto");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null); // {created, errors, name}
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const canEncrypt = splitFiles && outputFormat === "pdf";
  const dirty = !!(templateFile || dataFile);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !submitting && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  // ตัวอย่างข้อมูล + ตรวจกับตัวแปรใน Template (เมื่อเลือกครบ)
  useEffect(() => {
    if (!dataFile) { setPreview(null); return undefined; }
    let cancelled = false;
    (async () => {
      setPreviewLoading(true);
      setError("");
      const fd = new FormData();
      fd.append("data", dataFile);
      if (templateFile) fd.append("template", templateFile);
      fd.append("csv_delimiter", csvDelimiter);
      fd.append("csv_encoding", csvEncoding);
      try {
        const res = await api.autogenPreview(fd);
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || "ดึงตัวอย่างข้อมูลล้มเหลว");
        if (!cancelled) setPreview(d);
      } catch (err) {
        if (!cancelled) { setError(err.message); setPreview(null); }
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [dataFile, templateFile, csvDelimiter, csvEncoding]);

  const maxRows = preview ? (outputFormat === "pdf" ? preview.max_rows_pdf : preview.max_rows_docx) : null;
  const tooMany = preview && maxRows && preview.total_records > maxRows;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!templateFile || !dataFile) { setError("กรุณาเลือกทั้งไฟล์ Template และไฟล์ข้อมูล"); return; }
    if (canEncrypt && usePassword && !passwordField.trim()) { setError("กรุณาระบุคอลัมน์ที่ใช้เป็นรหัสผ่าน"); return; }
    setError("");
    setResult(null);
    setSubmitting(true);
    const fd = new FormData();
    fd.append("template", templateFile);
    fd.append("data", dataFile);
    fd.append("output_format", outputFormat);
    fd.append("split_files", splitFiles);
    if (splitFiles && filenameField.trim()) fd.append("filename_field", filenameField.trim());
    if (outputFilename.trim()) fd.append("output_filename", outputFilename.trim());
    if (canEncrypt && usePassword) fd.append("password_field", passwordField.trim());
    fd.append("csv_delimiter", csvDelimiter);
    fd.append("csv_encoding", csvEncoding);
    try {
      const res = await api.autogenGenerate(fd);
      if (!res.ok) {
        let msg = "เกิดข้อผิดพลาดในการสร้างเอกสาร";
        try { msg = (await res.json()).detail || msg; } catch { /* ไม่ใช่ JSON (เช่น หมดเวลา) */ }
        if (res.status === 504) msg = "ใช้เวลานานเกินไป — ลดจำนวนแถวในไฟล์ข้อมูลแล้วลองใหม่";
        throw new Error(msg);
      }
      const name = filenameFrom(res, splitFiles ? "autogen_result.zip" : `autogen_merged.${outputFormat}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      const created = Number(res.headers.get("X-Autogen-Created") || 0);
      const errors = Number(res.headers.get("X-Autogen-Errors") || 0);
      setResult({ created, errors, name });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const headers = preview?.headers || [];

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && !dirty && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="autogen-title" data-testid="autogen-modal"
        className="bg-white w-full sm:max-w-3xl rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92vh]">
        <div className="p-4 border-b border-gray-100 flex items-start gap-3">
          <div className="flex-1">
            <h3 id="autogen-title" className="text-lg font-bold text-gray-900">สร้างเอกสารอัตโนมัติ</h3>
            <p className="mt-1 text-sm text-gray-500">หยอดข้อมูลจาก Excel / CSV / JSON ลงไฟล์ Word ที่มี <code className="px-1 rounded bg-gray-100">{"{{ ชื่อคอลัมน์ }}"}</code> ได้เอกสารหลายชุดในคลิกเดียว · <a href="/manual.html#auto-gen" target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">วิธีใช้</a></p>
          </div>
          <button type="button" aria-label="ปิด" onClick={onClose} disabled={submitting} className="w-9 h-9 rounded-lg text-gray-500 hover:bg-gray-100">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-4">
          <details className="text-sm text-gray-600">
            <summary className="cursor-pointer text-blue-700">ดาวน์โหลดไฟล์ตัวอย่าง</summary>
            <div className="mt-2 flex flex-wrap gap-2">
              {SAMPLES.map(([f, t]) => (
                <a key={f} href={`/api/autogen/samples/${f}`} className="px-2.5 py-1 rounded-lg border border-gray-200 bg-gray-50 hover:bg-gray-100 text-xs">{t}</a>
              ))}
            </div>
          </details>

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className={label} htmlFor="autogen-template">1. ไฟล์ Template (.docx)</label>
              <input id="autogen-template" type="file" accept=".docx" className="block w-full text-sm" data-testid="autogen-template"
                onChange={(e) => { setTemplateFile(e.target.files?.[0] || null); setResult(null); }} />
            </div>
            <div>
              <label className={label} htmlFor="autogen-data">2. ไฟล์ข้อมูล (.xlsx, .csv, .txt, .json)</label>
              <input id="autogen-data" type="file" accept=".json,.csv,.txt,.xlsx" className="block w-full text-sm" data-testid="autogen-data"
                onChange={(e) => { setDataFile(e.target.files?.[0] || null); setResult(null); }} />
            </div>
          </div>

          {isText(dataFile) && (
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className={label}>ตัวคั่นคอลัมน์</label>
                <select className={input} value={csvDelimiter} onChange={(e) => setCsvDelimiter(e.target.value)}>
                  <option value="auto">อัตโนมัติ{preview?.delimiter ? ` (พบ ${preview.delimiter === "\t" ? "Tab" : `"${preview.delimiter}"`})` : ""}</option>
                  <option value=",">จุลภาค ( , )</option>
                  <option value=";">อัฒภาค ( ; )</option>
                  <option value={"\t"}>Tab</option>
                  <option value="|">ขีดตั้ง ( | )</option>
                </select>
              </div>
              <div>
                <label className={label}>การเข้ารหัสภาษา</label>
                <select className={input} value={csvEncoding} onChange={(e) => setCsvEncoding(e.target.value)}>
                  <option value="auto">อัตโนมัติ{preview?.encoding ? ` (${preview.encoding === "cp874" ? "Windows-874" : "UTF-8"})` : ""}</option>
                  <option value="utf-8-sig">UTF-8</option>
                  <option value="cp874">Windows-874 / TIS-620 (Excel ไทยรุ่นเก่า)</option>
                </select>
              </div>
            </div>
          )}

          {previewLoading && <p className="text-sm text-gray-500">กำลังอ่านไฟล์ข้อมูล...</p>}
          {preview && headers.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 space-y-2" data-testid="autogen-preview">
              <p className="text-sm font-medium text-gray-800">ตัวอย่างข้อมูล — {Math.min(3, preview.total_records)} จาก {preview.total_records.toLocaleString()} แถว</p>
              {preview.has_numeric_header_warning && (
                <p className="text-xs text-red-700 bg-red-50 rounded px-2 py-1">⚠️ พบตัวเลขในหัวคอลัมน์ — แถวแรกของไฟล์ต้องเป็นชื่อคอลัมน์</p>
              )}
              {preview.missing_variables?.length > 0 && (
                <p className="text-xs text-amber-800 bg-amber-50 rounded px-2 py-1" data-testid="autogen-missing">
                  ⚠️ ตัวแปรใน Template ที่ไม่มีในไฟล์ข้อมูล: {preview.missing_variables.map((v) => `{{ ${v} }}`).join(", ")} — จะแสดงเป็นช่องว่าง (ตรวจตัวสะกดชื่อคอลัมน์)
                </p>
              )}
              {preview.template_variables && preview.missing_variables?.length === 0 && (
                <p className="text-xs text-emerald-800 bg-emerald-50 rounded px-2 py-1">✓ ตัวแปรทุกตัวใน Template มีในไฟล์ข้อมูล</p>
              )}
              {tooMany && (
                <p className="text-xs text-red-700 bg-red-50 rounded px-2 py-1">ข้อมูลมีมากกว่า {maxRows.toLocaleString()} แถว — สร้างแบบ {outputFormat.toUpperCase()} ได้ครั้งละไม่เกินนี้ แบ่งไฟล์ข้อมูลเป็นหลายชุด</p>
              )}
              <div className="overflow-auto max-h-56 rounded border border-gray-200 bg-white">
                <table className="min-w-full text-xs">
                  <thead className="bg-gray-100 sticky top-0">
                    <tr>{headers.map((h) => <th key={h} className="px-2 py-1.5 text-left font-medium text-gray-700 whitespace-nowrap border-b border-gray-200">{`{{ ${h} }}`}</th>)}</tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((r, i) => (
                      <tr key={i} className="border-b border-gray-100 last:border-0">
                        {headers.map((h) => <td key={h} className="px-2 py-1.5 whitespace-nowrap text-gray-800">{typeof r[h] === "object" && r[h] !== null ? JSON.stringify(r[h]) : String(r[h] ?? "")}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className={label}>รูปแบบผลลัพธ์</label>
              <select className={input} value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)} data-testid="autogen-format">
                <option value="docx">Word (.docx)</option>
                <option value="pdf">PDF (.pdf)</option>
              </select>
            </div>
            <div>
              <label className={label}>การจัดการไฟล์</label>
              <select className={input} value={String(splitFiles)} onChange={(e) => setSplitFiles(e.target.value === "true")} data-testid="autogen-split">
                <option value="true">แยกไฟล์ละ 1 แถว (ดาวน์โหลดเป็น .zip)</option>
                <option value="false">รวมทุกแถวเป็นไฟล์เดียว (ขึ้นหน้าใหม่ทุกแถว)</option>
              </select>
            </div>
          </div>

          {splitFiles && (
            <div>
              <label className={label} htmlFor="autogen-fname">ตั้งชื่อไฟล์ย่อยจากคอลัมน์ (ไม่บังคับ)</label>
              <input id="autogen-fname" type="text" className={input} list="autogen-headers" value={filenameField}
                onChange={(e) => setFilenameField(e.target.value)}
                placeholder="เช่น invoice_no หรือหลายคอลัมน์คั่นด้วยเว้นวรรค · หรือ {{ invoice_no }}_{{ name }}" />
              <p className="mt-1 text-xs text-gray-500">ไม่ระบุ = ใช้ค่าคอลัมน์แรก · ชื่อซ้ำจะเติม -2, -3 · ตัวอักษรที่ใช้ในชื่อไฟล์ไม่ได้ (/ \ : * ? " &lt; &gt; |) เปลี่ยนเป็น _</p>
            </div>
          )}

          <div>
            <label className={`flex items-center gap-2 text-sm font-medium ${canEncrypt ? "text-gray-700" : "text-gray-400"}`}>
              <input type="checkbox" className="h-4 w-4" checked={canEncrypt && usePassword} disabled={!canEncrypt} onChange={(e) => setUsePassword(e.target.checked)} />
              เข้ารหัส PDF แต่ละไฟล์ด้วยรหัสผ่านจากคอลัมน์
            </label>
            {!canEncrypt && <p className="ml-6 mt-1 text-xs text-gray-400">ใช้ได้เมื่อเลือก PDF + แยกไฟล์</p>}
            {canEncrypt && usePassword && (
              <div className="ml-6 mt-2">
                <input type="text" className={input} list="autogen-headers" aria-label="คอลัมน์ที่ใช้เป็นรหัสผ่าน" value={passwordField}
                  onChange={(e) => setPasswordField(e.target.value)} placeholder="ชื่อคอลัมน์ เช่น citizen_id หรือ {{ emp_id }}{{ birth_year }}" />
                <p className="mt-1 text-xs text-gray-500">แต่ละไฟล์เปิดได้ด้วยค่าของแถวนั้น · แถวที่ไม่มีค่ารหัสผ่านจะไม่ถูกสร้าง (มีไฟล์ error_item_*.txt แจ้งใน .zip)</p>
              </div>
            )}
          </div>
          <datalist id="autogen-headers">{headers.map((h) => <option key={h} value={h} />)}</datalist>

          <div>
            <label className={label} htmlFor="autogen-out">ชื่อไฟล์ที่ดาวน์โหลด (ไม่บังคับ)</label>
            <input id="autogen-out" type="text" className={input} value={outputFilename} onChange={(e) => setOutputFilename(e.target.value)}
              placeholder={splitFiles ? "เช่น ใบแจ้งหนี้_มกราคม (ได้ .zip)" : `เช่น ใบแจ้งหนี้_มกราคม (ได้ .${outputFormat})`} />
          </div>

          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          {result && (
            <div className={`text-sm rounded-lg px-3 py-2 ${result.errors ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-900"}`} role="status" data-testid="autogen-result">
              ✓ ดาวน์โหลด <strong>{result.name}</strong> แล้ว — สร้าง {result.created.toLocaleString()} เอกสาร
              {result.errors > 0 && <> · <strong>ข้าม {result.errors} แถว</strong> ที่มีปัญหา{splitFiles ? " (ดูรายละเอียดในไฟล์ error_item_*.txt ใน .zip)" : ""}</>}
            </div>
          )}
        </form>

        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">ปิด</button>
          <button type="button" onClick={handleSubmit} disabled={submitting || !templateFile || !dataFile || tooMany} data-testid="autogen-submit"
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:opacity-40">
            {submitting ? (outputFormat === "pdf" ? "กำลังสร้างและแปลงเป็น PDF..." : "กำลังสร้างเอกสาร...") : `สร้างเอกสาร${preview?.total_records ? ` (${preview.total_records.toLocaleString()} แถว)` : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}
