// เครื่องมือด่วนบน Dashboard: ใส่ลายน้ำ / เซ็นเซอร์ด้วยคำค้นหา / เข้ารหัส / ปกปิดข้อมูลส่วนบุคคล (PDPA) / ลดขนาดไฟล์ โดยไม่ต้องเปิดไฟล์ใน Editor
// ขั้นตอน: เลือกไฟล์ → (ไฟล์ลงนามแล้ว? เตือน) → กรอกค่า → (มีรหัสผ่าน? ถาม) → server สร้างไฟล์ใหม่ → แจ้งผล
// ไฟล์เดิมไม่ถูกแก้เลย (ดู backend POST /pdf/files/{id}/quick-action)
import { useEffect, useState } from "react";
import { getFileSignatureStatus, quickFileAction, scanStoredFilePii } from "../../api.js";
import { useI18n } from "../../i18n/I18nContext.jsx";
import PiiReviewList, { defaultPiiSelection, downloadPiiReport } from "../pdpa/PiiReviewList.jsx";
import AddPasswordModal from "../AddPasswordModal.jsx";
import PasswordModal from "../PasswordModal.jsx";
import WatermarkModal from "../WatermarkModal.jsx";
import PageNumberModal from "../PageNumberModal.jsx";
import ChooseFileModal from "./ChooseFileModal.jsx";

const LABEL_KEYS = {
  watermark: { title: "quickAction.chooseWatermark", verb: "quickAction.verbWatermark" },
  page_numbers: { title: "quickAction.choosePageNumbers", verb: "quickAction.verbPageNumbers" },
  redact_search: { title: "quickAction.chooseRedact", verb: "quickAction.verbRedact" },
  encrypt: { title: "quickAction.chooseEncrypt", verb: "quickAction.verbEncrypt" },
  pdpa: { title: "quickAction.choosePdpa", verb: "quickAction.verbPdpa" },
  compress: { title: "quickAction.chooseCompress", verb: "quickAction.verbCompress" },
};

export function formatFileSize(bytes) {
  if (!bytes) return "";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

const COMPRESS_PROFILES = [
  { value: "screen", labelKey: "quickAction.compressScreen", hintKey: "quickAction.compressScreenHint" },
  { value: "ebook", labelKey: "quickAction.compressEbook", hintKey: "quickAction.compressEbookHint" },
  { value: "printer", labelKey: "quickAction.compressPrinter", hintKey: "quickAction.compressPrinterHint" },
];

function CompressForm({ file, submitting, initial, onSubmit, onCancel }) {
  const { t } = useI18n();
  const [profile, setProfile] = useState(initial?.compress_profile || "screen");
  return (
    <Dialog
      title={t("quickAction.compressTitle")}
      actions={
        <>
          <button type="button" className={SECONDARY} onClick={onCancel} disabled={submitting}>{t("common.cancel")}</button>
          <button type="button" className={PRIMARY} disabled={submitting} onClick={() => onSubmit({ compress_profile: profile })}>
            {submitting ? t("quickAction.compressing") : t("quickAction.compressBtn")}
          </button>
        </>
      }
    >
      <p>
        {t("quickAction.fileLabel")} <strong className="text-gray-900 break-all">{file.filename}</strong>
        {file.file_size ? <span className="text-gray-500"> ({formatFileSize(file.file_size)})</span> : null}
      </p>
      <fieldset className="space-y-2" disabled={submitting}>
        <legend className="sr-only">{t("quickAction.compressLegend")}</legend>
        {COMPRESS_PROFILES.map((p) => (
          <label key={p.value} className={`grid grid-cols-[auto_1fr] gap-x-3 items-start p-3 rounded-lg border cursor-pointer ${profile === p.value ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:bg-gray-50"}`}>
            <input type="radio" name="compress-profile" className="mt-0.5 row-span-2" value={p.value} checked={profile === p.value} onChange={() => setProfile(p.value)} />
            <span className="block font-medium text-gray-900">{t(p.labelKey)}</span>
            <span className="block text-xs text-gray-500">{t(p.hintKey)}</span>
          </label>
        ))}
      </fieldset>
      <p className="text-xs text-gray-500">{t("quickAction.compressFooter")}</p>
    </Dialog>
  );
}

function PdpaForm({ fileName, scan, submitting, onSubmit, onCancel }) {
  const { t } = useI18n();
  const [selected, setSelected] = useState(() => defaultPiiSelection(scan.findings));
  const [cleanMetadata, setCleanMetadata] = useState(true);
  const nothing = selected.size === 0 && !cleanMetadata;
  let btnLabel;
  if (submitting) {
    btnLabel = t("quickAction.pdpaRedacting");
  } else if (selected.size) {
    btnLabel = t("quickAction.pdpaRedactCount", { count: selected.size });
  } else {
    btnLabel = t("quickAction.pdpaCleanMetaOnly");
  }
  return (
    <Dialog
      title={t("quickAction.pdpaTitle")}
      wide
      actions={
        <>
          <button type="button" className={SECONDARY} onClick={onCancel} disabled={submitting}>{t("common.cancel")}</button>
          <button
            type="button"
            className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            disabled={nothing || submitting}
            onClick={() => onSubmit({ pii_ids: [...selected], clean_metadata: cleanMetadata })}
          >
            {btnLabel}
          </button>
        </>
      }
    >
      <p>{t("quickAction.fileLabel")} <strong className="text-gray-900 break-all">{fileName}</strong></p>
      <p>
        {t("quickAction.pdpaFoundBefore")} <strong className="text-gray-900">{scan.findings.length}</strong>{" "}
        {t("quickAction.pdpaFoundMid")} <strong>{t("quickAction.pdpaFoundStrong")}</strong> {t("quickAction.pdpaFoundAfter")}
      </p>
      <PiiReviewList scan={scan} selected={selected} onChange={setSelected} cleanMetadata={cleanMetadata} onCleanMetadata={setCleanMetadata} maxHeightClass="max-h-[45dvh]" />
      <p className="text-xs text-gray-500">{t("quickAction.pdpaServerOnly")}</p>
    </Dialog>
  );
}

function Dialog({ title, children, actions, labelledBy = "quick-action-title", wide = false }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-labelledby={labelledBy} className={`bg-white rounded-xl shadow-xl w-full p-6 max-h-[calc(100dvh-32px)] overflow-y-auto ${wide ? "max-w-xl" : "max-w-md"}`}>
        <h3 id={labelledBy} className="text-lg font-bold text-gray-900 mb-2">{title}</h3>
        <div className="text-sm text-gray-600 space-y-2">{children}</div>
        <div className="flex flex-wrap justify-end gap-3 mt-6">{actions}</div>
      </div>
    </div>
  );
}

const BTN = "px-4 py-2 text-sm font-medium rounded-lg";
const SECONDARY = `${BTN} text-gray-700 bg-white border border-gray-300 hover:bg-gray-50`;
const PRIMARY = `${BTN} text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50`;

function RedactForm({ fileName, submitting, initial, onSubmit, onCancel }) {
  const { t } = useI18n();
  const [keyword, setKeyword] = useState(initial?.keyword || "");
  const [isRegex, setIsRegex] = useState(initial?.is_regex || false);
  const [matchCase, setMatchCase] = useState(initial?.match_case || false);
  const hasLatin = /[A-Za-z]/.test(isRegex ? keyword.replace(/\\[A-Za-z]/g, "") : keyword); // \d \w ไม่นับ
  const submit = () => keyword.trim() && onSubmit({ keyword: keyword.trim(), is_regex: isRegex, match_case: matchCase && hasLatin });
  return (
    <Dialog
      title={t("quickAction.redactTitle")}
      actions={
        <>
          <button type="button" className={SECONDARY} onClick={onCancel} disabled={submitting}>{t("common.cancel")}</button>
          <button
            type="submit"
            form="redact-form"
            className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            disabled={!keyword.trim() || submitting}
          >
            {submitting ? t("quickAction.redacting") : t("quickAction.redactBtn")}
          </button>
        </>
      }
    >
      <p>{t("quickAction.fileLabel")} <strong className="text-gray-900 break-all">{fileName}</strong></p>
      <p>{t("quickAction.redactDescBefore")} <strong>{t("quickAction.redactDescStrong")}</strong> {t("quickAction.redactDescAfter")}</p>
      <form
        id="redact-form"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <input
          type="text"
          autoFocus
          maxLength={300}
          aria-label={t("quickAction.redactInputAria")}
          placeholder={isRegex ? t("quickAction.redactPhRegex") : t("quickAction.redactPhText")}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
        />
        <label className="mt-3 flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" className="h-4 w-4" checked={isRegex} onChange={(e) => setIsRegex(e.target.checked)} />
          {t("quickAction.redactUseRegex")}
        </label>
        {hasLatin && (
          <label className="mt-2 flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" className="h-4 w-4" checked={matchCase} onChange={(e) => setMatchCase(e.target.checked)} />
            {t("quickAction.redactMatchCase")}
          </label>
        )}
        {isRegex && (
          <div className="mt-2 text-xs text-gray-500 space-y-1">
            <p>{t("quickAction.redactExamples")}</p>
            <div className="flex flex-wrap gap-1.5">
              {REGEX_EXAMPLES.map((ex) => (
                <button key={ex.labelKey} type="button" onClick={() => setKeyword(ex.re)}
                  className="px-2 py-1 rounded-full border border-gray-300 hover:bg-gray-50 text-gray-700">{t(ex.labelKey)}</button>
              ))}
            </div>
          </div>
        )}
        <p className="mt-3 text-xs text-gray-500">
          {t("quickAction.redactFooter")}
        </p>
      </form>
    </Dialog>
  );
}

const REGEX_EXAMPLES = [
  { labelKey: "quickAction.regexPhone", re: "0[689]\\d-?\\d{3}-?\\d{4}" },
  { labelKey: "quickAction.regexNationalId", re: "\\d[- ]?\\d{4}[- ]?\\d{5}[- ]?\\d{2}[- ]?\\d" },
  { labelKey: "quickAction.regexEmail", re: "[\\w.+-]+@[\\w-]+\\.[\\w.-]+" },
  { labelKey: "quickAction.regexBankAccount", re: "\\d{3}-\\d-\\d{5}-\\d" },
];

// initialFile: เริ่มจากไฟล์ที่เลือกไว้แล้ว (เมนู ☰ ของไฟล์) ข้ามขั้นเลือกไฟล์
export default function QuickFileAction({ action, files, initialFile = null, onClose, onDone, onOpenFile }) {
  const { lang, t } = useI18n();
  const labelKeys = LABEL_KEYS[action];
  const labels = { title: t(labelKeys.title), verb: t(labelKeys.verb) };
  const [step, setStep] = useState(initialFile ? "checking" : "choose"); // choose | checking | signed | scanning | scan_error | form | password | result
  const [file, setFile] = useState(initialFile);
  const [params, setParams] = useState(null);
  const [signedCount, setSignedCount] = useState(0);
  const [pdfa, setPdfa] = useState(null); // ไฟล์เป็น PDF/A — เตือนก่อนเข้ารหัส
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [result, setResult] = useState(null);
  const [scan, setScan] = useState(null); // action=pdpa: ผลสแกน
  const [filePassword, setFilePassword] = useState(null); // รหัสผ่านที่ใช้สแกนผ่านแล้ว (pdpa)

  useEffect(() => {
    if (initialFile) void choose(initialFile);
    // เริ่มครั้งเดียว
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function choose(f) {
    setFile(f);
    setError("");
    setStep("checking");
    try {
      const status = await getFileSignatureStatus(f.id);
      setPdfa(status.pdfa || null);
      if (status.signed) {
        setSignedCount(status.count);
        setStep("signed");
        return;
      }
    } catch (e) {
      console.error(e); // ตรวจไม่ได้ก็ทำต่อได้ — ผลลัพธ์เป็นไฟล์ใหม่อยู่แล้ว
    }
    proceed(f);
  }

  function proceed(f = file) {
    if (action === "pdpa") void runScan(f, null);
    else setStep("form");
  }

  async function runScan(f, password) {
    setStep("scanning");
    setError("");
    setSubmitting(true);
    try {
      const res = await scanStoredFilePii(f.id, password);
      setScan(res);
      setFilePassword(password);
      setStep("form");
    } catch (e) {
      if (e.status === 423) {
        setPasswordError(password ? e.message : "");
        setStep("password");
      } else {
        setError(e.message || t("quickAction.scanErrorTitle"));
        setStep("scan_error");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function run(nextParams, password = null) {
    setParams(nextParams);
    setSubmitting(true);
    setError("");
    try {
      let body;
      if (action === "watermark") {
        body = { action, watermark: nextParams, password };
      } else if (action === "page_numbers") {
        body = { action, page_numbers: nextParams, password };
      } else if (action === "encrypt") {
        body = { action, new_password: nextParams.new_password, encryption: nextParams.encryption || "aes256", password };
      } else if (action === "pdpa") {
        body = { action, ...nextParams, password: password ?? filePassword };
      } else if (action === "compress") {
        body = { action, compress_profile: nextParams.compress_profile, password };
      } else {
        body = { action, keyword: nextParams.keyword, is_regex: nextParams.is_regex, match_case: !!nextParams.match_case, password };
      }
      const res = await quickFileAction(file.id, body);
      setResult(res);
      setStep("result");
      if (res.status === "ok") onDone(res.file);
    } catch (e) {
      if (e.status === 423) {
        setPasswordError(password ? e.message : "");
        setStep("password");
      } else {
        setError(e.message || t("common.errorGeneric"));
        setStep("form");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (step === "choose") {
    return <ChooseFileModal title={labels.title} files={files} onCancel={onClose} onChoose={(f) => void choose(f)} />;
  }

  if (step === "scanning") {
    return (
      <Dialog title={t("quickAction.pdpaTitle")} actions={<button type="button" className={SECONDARY} onClick={onClose}>{t("common.cancel")}</button>}>
        <p>{t("quickAction.scanningBefore")} <strong className="text-gray-900 break-all">{file.filename}</strong>...</p>
      </Dialog>
    );
  }

  if (step === "scan_error") {
    return (
      <Dialog title={t("quickAction.scanErrorTitle")} actions={<button type="button" className={PRIMARY} onClick={onClose}>{t("common.close")}</button>}>
        <p className="text-red-700">{error}</p>
      </Dialog>
    );
  }

  if (step === "checking") {
    return (
      <Dialog title={labels.title} actions={<button type="button" className={SECONDARY} onClick={onClose}>{t("common.cancel")}</button>}>
        <p>{t("quickAction.checking")}</p>
      </Dialog>
    );
  }

  if (step === "signed" && (action === "encrypt" || action === "compress")) {
    return (
      <Dialog title={t("quickAction.signedBlockedTitle", { verb: labels.verb })} actions={<button type="button" className={PRIMARY} onClick={onClose}>{t("quickAction.ok")}</button>}>
        <p>
          <strong className="text-gray-900 break-all">{file.filename}</strong>{" "}
          {t("quickAction.signedBlockedBody", { count: signedCount, verb: labels.verb })}
        </p>
      </Dialog>
    );
  }

  if (step === "signed") {
    return (
      <Dialog
        title={t("quickAction.signedWarnTitle")}
        actions={
          <>
            <button type="button" className={PRIMARY} onClick={onClose}>{t("common.cancel")}</button>
            <button type="button" className={SECONDARY} onClick={() => proceed()}>{t("quickAction.signedContinue")}</button>
          </>
        }
      >
        <p>
          <strong className="text-gray-900 break-all">{file.filename}</strong>{" "}
          {t("quickAction.signedWarnBody", { count: signedCount })}
        </p>
        <p className="p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200">
          {t("quickAction.signedWarnBoxBefore", { verb: labels.verb })} <strong>{t("quickAction.signedWarnBoxStrong")}</strong>{" "}
          {t("quickAction.signedWarnBoxAfter")}
        </p>
      </Dialog>
    );
  }

  if (step === "password") {
    return (
      <PasswordModal
        fileName={file.filename}
        error={passwordError}
        submitting={submitting}
        onCancel={onClose}
        onSubmit={(pw) => void (action === "pdpa" && !scan ? runScan(file, pw) : run(params, pw))}
      />
    );
  }

  if (step === "result") {
    if (result.status === "no_change") {
      return (
        <Dialog
          title={t("quickAction.noChangeTitle")}
          actions={
            <>
              <button type="button" className={SECONDARY} onClick={onClose}>{t("common.close")}</button>
              {params?.compress_profile !== "screen" && (
                <button type="button" className={PRIMARY} onClick={() => setStep("form")}>{t("quickAction.chooseOtherProfile")}</button>
              )}
            </>
          }
        >
          <p>{t("quickAction.noChangeBody", { name: file.filename })}</p>
          <p className="text-xs text-gray-500">
            {t("quickAction.noChangeHint")}
            {params?.compress_profile !== "screen" ? t("quickAction.noChangeTryScreen") : ""}
          </p>
        </Dialog>
      );
    }
    if (result.status === "not_found") {
      return (
        <Dialog
          title={t("quickAction.notFoundTitle")}
          actions={
            <>
              <button type="button" className={SECONDARY} onClick={onClose}>{t("common.close")}</button>
              <button type="button" className={PRIMARY} onClick={() => setStep("form")}>{t("quickAction.searchAnother")}</button>
            </>
          }
        >
          <p>{t("quickAction.notFoundBefore")}<strong className="text-gray-900">{params.keyword}</strong>{t("quickAction.notFoundAfter", { name: file.filename })}</p>
          {result.image_pages?.length > 0 && (
            <p className="mt-2 text-sm text-amber-800 bg-amber-50 rounded p-2" data-testid="image-pages-hint">
              {t("quickAction.imagePagesHint", { pages: result.image_pages.join(", ") })}
            </p>
          )}
        </Dialog>
      );
    }
    let doneTitle;
    if (action === "watermark") doneTitle = t("quickAction.doneWatermark");
    else if (action === "page_numbers") doneTitle = t("quickAction.donePageNumbers", { count: result.count });
    else if (action === "encrypt") doneTitle = t("quickAction.doneEncrypt");
    else if (action === "pdpa") doneTitle = t("quickAction.donePdpa", { count: result.count });
    else if (action === "compress") doneTitle = t("quickAction.doneCompress");
    else doneTitle = t("quickAction.doneRedact", { count: result.count });
    return (
      <Dialog
        title={doneTitle}
        actions={
          <>
            <button type="button" className={SECONDARY} onClick={onClose}>{t("common.close")}</button>
            <button type="button" className={PRIMARY} onClick={() => { onClose(); onOpenFile(result.file.session_id); }}>
              {t("quickAction.openFileBtn")}
            </button>
          </>
        }
      >
        {action === "compress" && result.sizes && (
          <p className="p-3 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 text-base">
            {formatFileSize(result.sizes.before)} → <strong>{formatFileSize(result.sizes.after)}</strong>
            {" "}(−{Math.round((1 - result.sizes.after / result.sizes.before) * 100)}%)
          </p>
        )}
        <p>{t("quickAction.savedAs")} <strong className="text-gray-900 break-all">{result.file.filename}</strong></p>
        <p>{t("quickAction.originalUnchanged")}</p>
        {action === "pdpa" && result.report?.length > 0 && (
          <button type="button" className="text-blue-700 hover:underline" onClick={() => downloadPiiReport(result.report, file.filename, { t, lang })}>
            {t("quickAction.downloadPdpaReport")}
          </button>
        )}
        {action === "encrypt" && (
          <p className="p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200">
            {t("quickAction.encryptRemember")}
          </p>
        )}
      </Dialog>
    );
  }

  // step === "form"
  const errorBox = error && <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] p-3 rounded-lg bg-red-50 text-red-700 text-sm border border-red-200 shadow" role="alert">{error}</div>;
  if (action === "encrypt") {
    return (
      <>
        {errorBox}
        <AddPasswordModal
          error={null}
          submitting={submitting}
          subtitle={t("quickAction.encryptSubtitle", { name: file.filename })}
          onCancel={onClose}
          pdfa={pdfa}
          onSubmit={(pw, encryption) => void run({ new_password: pw, encryption })}
        />
      </>
    );
  }
  if (action === "pdpa") {
    return (
      <>
        {errorBox}
        <PdpaForm fileName={file.filename} scan={scan} submitting={submitting} onCancel={onClose} onSubmit={(p) => void run(p)} />
      </>
    );
  }
  if (action === "compress") {
    return (
      <>
        {errorBox}
        <CompressForm file={file} submitting={submitting} initial={params} onCancel={onClose} onSubmit={(p) => void run(p)} />
      </>
    );
  }
  if (action === "page_numbers") {
    return (
      <>
        {errorBox}
        <PageNumberModal fileName={file.filename} submitting={submitting} onClose={onClose} onSubmit={(payload) => void run(payload)} />
      </>
    );
  }
  if (action === "watermark") {
    return (
      <>
        {errorBox}
        <WatermarkModal fileName={file.filename} submitting={submitting} onClose={onClose} onSubmit={(payload) => void run(payload)} />
      </>
    );
  }
  return (
    <>
      {errorBox}
      <RedactForm fileName={file.filename} submitting={submitting} initial={params} onCancel={onClose} onSubmit={(p) => void run(p)} />
    </>
  );
}
