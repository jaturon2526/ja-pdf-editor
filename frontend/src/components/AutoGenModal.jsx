// สร้างเอกสารอัตโนมัติ (Mail Merge): Template Word + ไฟล์ข้อมูล → Word/PDF แยกไฟล์ (.zip) หรือรวมไฟล์เดียว
import { useEffect, useState } from "react";
import * as api from "../api.js";
import { useI18n } from "../i18n/I18nContext.jsx";

const SAMPLES = [
  ["template_flat.docx", "autogenModal.sampleSimple"],
  ["data_flat.xlsx", "autogenModal.sampleExcel"],
  ["data_flat.csv", "autogenModal.sampleCsv"],
  ["template.docx", "autogenModal.sampleAdvanced"],
  ["data.json", "autogenModal.sampleJson"],
  ["template_qr.docx", "autogenModal.sampleQr"],
  ["data_qr.xlsx", "autogenModal.sampleBadge"],
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
  const { lang, t } = useI18n();
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
    void (async () => {
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
        if (!res.ok) throw new Error(d.detail || t("autogenModal.previewError"));
        if (!cancelled) setPreview(d);
      } catch (err) {
        if (!cancelled) { setError(err.message); setPreview(null); }
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataFile, templateFile, csvDelimiter, csvEncoding]);

  const maxRows = preview ? (outputFormat === "pdf" ? preview.max_rows_pdf : preview.max_rows_docx) : null;
  const tooMany = preview && maxRows && preview.total_records > maxRows;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!templateFile || !dataFile) { setError(t("autogenModal.needBothFiles")); return; }
    if (canEncrypt && usePassword && !passwordField.trim()) { setError(t("autogenModal.needPasswordCol")); return; }
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
        let msg = t("autogenModal.genError");
        try { msg = (await res.json()).detail || msg; } catch { /* ไม่ใช่ JSON (เช่น หมดเวลา) */ }
        if (res.status === 504) msg = t("autogenModal.timeoutError");
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
  const manualUrl = lang === "en" ? "/manual-en.html#auto-gen" : "/manual.html#auto-gen";
  const detectedDelim = preview?.delimiter === "\t" ? "Tab" : `"${preview?.delimiter}"`;
  const detectedEnc = preview?.encoding === "cp874" ? "Windows-874" : "UTF-8";

  let submitBtnText;
  if (submitting) {
    submitBtnText = outputFormat === "pdf" ? t("autogenModal.generatingPdf") : t("autogenModal.generatingDoc");
  } else if (preview?.total_records) {
    submitBtnText = t("autogenModal.generateWithRows", { count: preview.total_records.toLocaleString() });
  } else {
    submitBtnText = t("autogenModal.generateBtn");
  }

  return (
    <div role="presentation" className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/40 backdrop-blur-sm"
      onMouseDown={(e) => e.target === e.currentTarget && !submitting && !dirty && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="autogen-title" data-testid="autogen-modal"
        className="bg-white w-full sm:max-w-3xl rounded-t-2xl sm:rounded-xl shadow-xl flex flex-col max-h-[92vh]">
        <div className="p-4 border-b border-gray-100 flex items-start gap-3">
          <div className="flex-1">
            <h3 id="autogen-title" className="text-lg font-bold text-gray-900">{t("autogenModal.title")}</h3>
            <p className="mt-1 text-sm text-gray-500">
              {t("autogenModal.subtitleBefore")} <code className="px-1 rounded bg-gray-100">{"{{ column_name }}"}</code>{" "}
              {t("autogenModal.subtitleAfter")}{" "}
              <a href={manualUrl} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">{t("autogenModal.howTo")}</a>
            </p>
          </div>
          <button type="button" aria-label={t("common.close")} onClick={onClose} disabled={submitting} className="w-9 h-9 rounded-lg text-gray-500 hover:bg-gray-100">✕</button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="flex-1 overflow-y-auto p-4 space-y-4">
          <details className="text-sm text-gray-600">
            <summary className="cursor-pointer text-blue-700">{t("autogenModal.downloadSamples")}</summary>
            <div className="mt-2 flex flex-wrap gap-2">
              {SAMPLES.map(([f, key]) => (
                <a key={f} href={`/api/autogen/samples/${f}`} className="px-2.5 py-1 rounded-lg border border-gray-200 bg-gray-50 hover:bg-gray-100 text-xs">{t(key)}</a>
              ))}
            </div>
          </details>

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className={label} htmlFor="autogen-template">{t("autogenModal.step1Label")}</label>
              <input id="autogen-template" type="file" accept=".docx" className="block w-full text-sm" data-testid="autogen-template"
                onChange={(e) => { setTemplateFile(e.target.files?.[0] || null); setResult(null); }} />
            </div>
            <div>
              <label className={label} htmlFor="autogen-data">{t("autogenModal.step2Label")}</label>
              <input id="autogen-data" type="file" accept=".json,.csv,.txt,.xlsx" className="block w-full text-sm" data-testid="autogen-data"
                onChange={(e) => { setDataFile(e.target.files?.[0] || null); setResult(null); }} />
            </div>
          </div>

          {isText(dataFile) && (
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="autogenmodal-f166" className={label}>{t("autogenModal.delimiterLabel")}</label>
                <select id="autogenmodal-f166" className={input} value={csvDelimiter} onChange={(e) => setCsvDelimiter(e.target.value)}>
                  <option value="auto">{preview?.delimiter ? t("autogenModal.autoDetected", { val: detectedDelim }) : t("autogenModal.auto")}</option>
                  <option value=",">{t("autogenModal.comma")}</option>
                  <option value=";">{t("autogenModal.semicolon")}</option>
                  <option value={"\t"}>Tab</option>
                  <option value="|">{t("autogenModal.pipe")}</option>
                </select>
              </div>
              <div>
                <label htmlFor="autogenmodal-f176" className={label}>{t("autogenModal.encodingLabel")}</label>
                <select id="autogenmodal-f176" className={input} value={csvEncoding} onChange={(e) => setCsvEncoding(e.target.value)}>
                  <option value="auto">{preview?.encoding ? t("autogenModal.encodingAuto", { val: detectedEnc }) : t("autogenModal.auto")}</option>
                  <option value="utf-8-sig">UTF-8</option>
                  <option value="cp874">{t("autogenModal.encodingCp874")}</option>
                </select>
              </div>
            </div>
          )}

          {previewLoading && <p className="text-sm text-gray-500">{t("autogenModal.readingData")}</p>}
          {preview && headers.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 space-y-2" data-testid="autogen-preview">
              <p className="text-sm font-medium text-gray-800">{t("autogenModal.previewHeading", { shown: Math.min(3, preview.total_records), total: preview.total_records.toLocaleString() })}</p>
              {preview.has_numeric_header_warning && (
                <p className="text-xs text-red-700 bg-red-50 rounded px-2 py-1">{t("autogenModal.numericHeaderWarn")}</p>
              )}
              {preview.missing_variables?.length > 0 && (
                <p className="text-xs text-amber-800 bg-amber-50 rounded px-2 py-1" data-testid="autogen-missing">
                  {t("autogenModal.missingVars", { vars: preview.missing_variables.map((v) => `{{ ${v} }}`).join(", ") })}
                </p>
              )}
              {preview.template_variables && preview.missing_variables?.length === 0 && (
                <p className="text-xs text-emerald-800 bg-emerald-50 rounded px-2 py-1">{t("autogenModal.allVarsOk")}</p>
              )}
              {tooMany && (
                <p className="text-xs text-red-700 bg-red-50 rounded px-2 py-1">{t("autogenModal.tooManyRows", { max: maxRows.toLocaleString(), fmt: outputFormat.toUpperCase() })}</p>
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
              <label htmlFor="autogenmodal-f223" className={label}>{t("autogenModal.outputFormatLabel")}</label>
              <select id="autogenmodal-f223" className={input} value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)} data-testid="autogen-format">
                <option value="docx">Word (.docx)</option>
                <option value="pdf">PDF (.pdf)</option>
              </select>
            </div>
            <div>
              <label htmlFor="autogenmodal-f230" className={label}>{t("autogenModal.fileHandlingLabel")}</label>
              <select id="autogenmodal-f230" className={input} value={String(splitFiles)} onChange={(e) => setSplitFiles(e.target.value === "true")} data-testid="autogen-split">
                <option value="true">{t("autogenModal.splitTrue")}</option>
                <option value="false">{t("autogenModal.splitFalse")}</option>
              </select>
            </div>
          </div>

          {splitFiles && (
            <div>
              <label className={label} htmlFor="autogen-fname">{t("autogenModal.filenameFieldLabel")}</label>
              <input id="autogen-fname" type="text" className={input} list="autogen-headers" value={filenameField}
                onChange={(e) => setFilenameField(e.target.value)}
                placeholder={t("autogenModal.filenameFieldPh")} />
              <p className="mt-1 text-xs text-gray-500">{t("autogenModal.filenameFieldHint")}</p>
            </div>
          )}

          <div>
            <label className={`flex items-center gap-2 text-sm font-medium ${canEncrypt ? "text-gray-700" : "text-gray-400"}`}>
              <input type="checkbox" className="h-4 w-4" checked={canEncrypt && usePassword} disabled={!canEncrypt} onChange={(e) => setUsePassword(e.target.checked)} />
              {t("autogenModal.encryptCheckbox")}
            </label>
            {!canEncrypt && <p className="ml-6 mt-1 text-xs text-gray-400">{t("autogenModal.encryptHint")}</p>}
            {canEncrypt && usePassword && (
              <div className="ml-6 mt-2">
                <input type="text" className={input} list="autogen-headers" aria-label={t("autogenModal.passwordFieldAria")} value={passwordField}
                  onChange={(e) => setPasswordField(e.target.value)} placeholder={t("autogenModal.passwordFieldPh")} />
                <p className="mt-1 text-xs text-gray-500">{t("autogenModal.passwordFieldHint")}</p>
              </div>
            )}
          </div>
          <datalist id="autogen-headers">{headers.map((h) => <option key={h} value={h} />)}</datalist>

          <div>
            <label className={label} htmlFor="autogen-out">{t("autogenModal.outputNameLabel")}</label>
            <input id="autogen-out" type="text" className={input} value={outputFilename} onChange={(e) => setOutputFilename(e.target.value)}
              placeholder={splitFiles ? t("autogenModal.outputNamePhZip") : t("autogenModal.outputNamePhSingle", { ext: outputFormat })} />
          </div>

          {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
          {result && (
            <div className={`text-sm rounded-lg px-3 py-2 ${result.errors ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-900"}`} role="status" data-testid="autogen-result">
              {t("autogenModal.resultDownloaded")} <strong>{result.name}</strong> {t("autogenModal.resultCreated", { count: result.created.toLocaleString() })}
              {result.errors > 0 && <> · <strong>{t("autogenModal.resultSkipped", { count: result.errors })}</strong> {t("autogenModal.resultSkippedTail")}{splitFiles ? t("autogenModal.resultSkippedZip") : ""}</>}
            </div>
          )}
        </form>

        <div className="p-3 border-t border-gray-100 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={submitting}
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">{t("common.close")}</button>
          <button type="button" onClick={(e) => void handleSubmit(e)} disabled={submitting || !templateFile || !dataFile || tooMany} data-testid="autogen-submit"
            className="px-4 py-2 min-h-[40px] text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:opacity-40">
            {submitBtnText}
          </button>
        </div>
      </div>
    </div>
  );
}
