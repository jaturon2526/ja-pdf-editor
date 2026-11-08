// เครื่องมือด่วนบน Dashboard: ใส่ลายน้ำ / เซ็นเซอร์ด้วยคำค้นหา / เข้ารหัส / ปกปิดข้อมูลส่วนบุคคล (PDPA) / ลดขนาดไฟล์ โดยไม่ต้องเปิดไฟล์ใน Editor
// ขั้นตอน: เลือกไฟล์ → (ไฟล์ลงนามแล้ว? เตือน) → กรอกค่า → (มีรหัสผ่าน? ถาม) → server สร้างไฟล์ใหม่ → แจ้งผล
// ไฟล์เดิมไม่ถูกแก้เลย (ดู backend POST /pdf/files/{id}/quick-action)
import { useEffect, useState } from "react";
import { getFileSignatureStatus, quickFileAction, scanStoredFilePii } from "../../api.js";
import PiiReviewList, { defaultPiiSelection, downloadPiiReport } from "../pdpa/PiiReviewList.jsx";
import AddPasswordModal from "../AddPasswordModal.jsx";
import PasswordModal from "../PasswordModal.jsx";
import WatermarkModal from "../WatermarkModal.jsx";
import PageNumberModal from "../PageNumberModal.jsx";
import ChooseFileModal from "./ChooseFileModal.jsx";

const LABELS = {
  watermark: { title: "เลือกเอกสารที่จะใส่ลายน้ำ", verb: "ใส่ลายน้ำ", busy: "กำลังใส่ลายน้ำ..." },
  page_numbers: { title: "เลือกเอกสารที่จะใส่เลขหน้า", verb: "ใส่เลขหน้า", busy: "กำลังใส่เลขหน้า..." },
  redact_search: { title: "เลือกเอกสารที่จะเซ็นเซอร์", verb: "เซ็นเซอร์", busy: "กำลังเซ็นเซอร์..." },
  encrypt: { title: "เลือกเอกสารที่จะเข้ารหัส", verb: "เข้ารหัส", busy: "กำลังเข้ารหัส..." },
  pdpa: { title: "เลือกเอกสารที่จะปกปิดข้อมูลส่วนบุคคล", verb: "ปกปิดข้อมูล", busy: "กำลังปกปิดข้อมูล..." },
  compress: { title: "เลือกเอกสารที่จะลดขนาด", verb: "ลดขนาด", busy: "กำลังลดขนาดไฟล์..." },
};

export function formatFileSize(bytes) {
  if (!bytes) return "";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

const COMPRESS_PROFILES = [
  { value: "screen", label: "เล็กสุด (Screen)", hint: "สำหรับดูบนจอ ส่ง LINE/อีเมล — ลดความละเอียดรูปมากที่สุด" },
  { value: "ebook", label: "ปานกลาง (eBook)", hint: "ภาพชัดปานกลาง" },
  { value: "printer", label: "ใหญ่ (Printer)", hint: "คงความคมชัดสำหรับพิมพ์" },
];

function CompressForm({ file, submitting, initial, onSubmit, onCancel }) {
  const [profile, setProfile] = useState(initial?.compress_profile || "screen");
  return (
    <Dialog
      title="ลดขนาดไฟล์"
      actions={
        <>
          <button type="button" className={SECONDARY} onClick={onCancel} disabled={submitting}>ยกเลิก</button>
          <button type="button" className={PRIMARY} disabled={submitting} onClick={() => onSubmit({ compress_profile: profile })}>
            {submitting ? "กำลังลดขนาด..." : "ลดขนาด"}
          </button>
        </>
      }
    >
      <p>
        ไฟล์: <strong className="text-gray-900 break-all">{file.filename}</strong>
        {file.file_size ? <span className="text-gray-500"> ({formatFileSize(file.file_size)})</span> : null}
      </p>
      <fieldset className="space-y-2" disabled={submitting}>
        <legend className="sr-only">ระดับการบีบอัด</legend>
        {COMPRESS_PROFILES.map((p) => (
          <label key={p.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer ${profile === p.value ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:bg-gray-50"}`}>
            <input type="radio" name="compress-profile" className="mt-0.5" value={p.value} checked={profile === p.value} onChange={() => setProfile(p.value)} />
            <span>
              <span className="block font-medium text-gray-900">{p.label}</span>
              <span className="block text-xs text-gray-500">{p.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <p className="text-xs text-gray-500">บันทึกเป็นไฟล์ใหม่ (ไฟล์เดิมไม่ถูกแก้) · ไฮไลต์ กล่องข้อความ และช่องฟอร์มยังอยู่ครบ</p>
    </Dialog>
  );
}

function PdpaForm({ fileName, scan, submitting, onSubmit, onCancel }) {
  const [selected, setSelected] = useState(() => defaultPiiSelection(scan.findings));
  const [cleanMetadata, setCleanMetadata] = useState(true);
  const nothing = selected.size === 0 && !cleanMetadata;
  return (
    <Dialog
      title="ปกปิดข้อมูลส่วนบุคคล (PDPA)"
      wide
      actions={
        <>
          <button type="button" className={SECONDARY} onClick={onCancel} disabled={submitting}>ยกเลิก</button>
          <button
            type="button"
            className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            disabled={nothing || submitting}
            onClick={() => onSubmit({ pii_ids: [...selected], clean_metadata: cleanMetadata })}
          >
            {submitting ? "กำลังปกปิด..." : selected.size ? `ปกปิด ${selected.size} รายการ` : "ล้างข้อมูลเมตา"}
          </button>
        </>
      }
    >
      <p>ไฟล์: <strong className="text-gray-900 break-all">{fileName}</strong></p>
      <p>
        ตรวจพบ <strong className="text-gray-900">{scan.findings.length}</strong> รายการ — ตรวจทานแล้วติ๊กเลือก
        รายการที่เลือกจะถูก<strong>ลบออกถาวร</strong>และปิดด้วยแถบสีดำในไฟล์ใหม่ (ไฟล์เดิมไม่ถูกแก้)
      </p>
      <PiiReviewList scan={scan} selected={selected} onChange={setSelected} cleanMetadata={cleanMetadata} onCleanMetadata={setCleanMetadata} maxHeightClass="max-h-[45dvh]" />
      <p className="text-xs text-gray-500">ตรวจบนเซิร์ฟเวอร์ของระบบเท่านั้น ไม่ส่งข้อความในเอกสารไปยัง AI หรือบริการภายนอก</p>
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
  const [keyword, setKeyword] = useState(initial?.keyword || "");
  const [isRegex, setIsRegex] = useState(initial?.is_regex || false);
  const [matchCase, setMatchCase] = useState(initial?.match_case || false);
  const hasLatin = /[A-Za-z]/.test(isRegex ? keyword.replace(/\\[A-Za-z]/g, "") : keyword); // \d \w ไม่นับ
  const submit = () => keyword.trim() && onSubmit({ keyword: keyword.trim(), is_regex: isRegex, match_case: matchCase && hasLatin });
  return (
    <Dialog
      title="เซ็นเซอร์ด้วยคำค้นหา"
      actions={
        <>
          <button type="button" className={SECONDARY} onClick={onCancel} disabled={submitting}>ยกเลิก</button>
          <button
            type="submit"
            form="redact-form"
            className="px-4 py-2 text-sm font-medium rounded-lg text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
            disabled={!keyword.trim() || submitting}
          >
            {submitting ? "กำลังเซ็นเซอร์..." : "เซ็นเซอร์"}
          </button>
        </>
      }
    >
      <p>ไฟล์: <strong className="text-gray-900 break-all">{fileName}</strong></p>
      <p>ข้อความที่ตรงกับคำค้นหาจะถูก<strong>ลบออกถาวร</strong>และปิดทับด้วยแถบสีดำในไฟล์ใหม่ (ไฟล์เดิมไม่ถูกแก้)</p>
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
          aria-label="คำที่ต้องการเซ็นเซอร์"
          placeholder={isRegex ? "เช่น 0\\d{1,2}-?\\d{3}-?\\d{4}" : "เช่น ชื่อ-นามสกุล, เลขที่บัญชี"}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
        />
        <label className="mt-3 flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" className="h-4 w-4" checked={isRegex} onChange={(e) => setIsRegex(e.target.checked)} />
          ใช้รูปแบบ Regular Expression (Regex)
        </label>
        {hasLatin && (
          <label className="mt-2 flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" className="h-4 w-4" checked={matchCase} onChange={(e) => setMatchCase(e.target.checked)} />
            ตัวพิมพ์เล็ก/ใหญ่ต้องตรงกัน (Aa)
          </label>
        )}
        {isRegex && (
          <div className="mt-2 text-xs text-gray-500 space-y-1">
            <p>ตัวอย่าง (กดเพื่อใช้):</p>
            <div className="flex flex-wrap gap-1.5">
              {REGEX_EXAMPLES.map((ex) => (
                <button key={ex.label} type="button" onClick={() => setKeyword(ex.re)}
                  className="px-2 py-1 rounded-full border border-gray-300 hover:bg-gray-50 text-gray-700">{ex.label}</button>
              ))}
            </div>
          </div>
        )}
        <p className="mt-3 text-xs text-gray-500">
          ลบคำนี้ออกจากช่องกรอกฟอร์ม โน้ต/ความคิดเห็น บุ๊กมาร์ก และข้อมูลเมตาของไฟล์ด้วย ·
          ข้อความที่เป็นรูปภาพ (เอกสารสแกน ลายเซ็น ตราประทับ) ค้นด้วยคำไม่ได้
        </p>
      </form>
    </Dialog>
  );
}

const REGEX_EXAMPLES = [
  { label: "เบอร์มือถือ", re: "0[689]\\d-?\\d{3}-?\\d{4}" },
  { label: "เลขบัตรประชาชน", re: "\\d[- ]?\\d{4}[- ]?\\d{5}[- ]?\\d{2}[- ]?\\d" },
  { label: "อีเมล", re: "[\\w.+-]+@[\\w-]+\\.[\\w.-]+" },
  { label: "เลขบัญชี xxx-x-xxxxx-x", re: "\\d{3}-\\d-\\d{5}-\\d" },
];

// initialFile: เริ่มจากไฟล์ที่เลือกไว้แล้ว (เมนู ☰ ของไฟล์) ข้ามขั้นเลือกไฟล์
export default function QuickFileAction({ action, files, initialFile = null, onClose, onDone, onOpenFile }) {
  const labels = LABELS[action];
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
    if (initialFile) choose(initialFile);
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
    if (action === "pdpa") runScan(f, null);
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
        setError(e.message || "ตรวจเอกสารไม่สำเร็จ");
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
      const body =
        action === "watermark"
          ? { action, watermark: nextParams, password }
          : action === "page_numbers"
            ? { action, page_numbers: nextParams, password }
          : action === "encrypt"
            ? { action, new_password: nextParams.new_password, encryption: nextParams.encryption || "aes256", password }
            : action === "pdpa"
              ? { action, ...nextParams, password: password ?? filePassword }
              : action === "compress"
                ? { action, compress_profile: nextParams.compress_profile, password }
              : { action, keyword: nextParams.keyword, is_regex: nextParams.is_regex, match_case: !!nextParams.match_case, password };
      const res = await quickFileAction(file.id, body);
      setResult(res);
      setStep("result");
      if (res.status === "ok") onDone(res.file);
    } catch (e) {
      if (e.status === 423) {
        setPasswordError(password ? e.message : "");
        setStep("password");
      } else {
        setError(e.message || "เกิดข้อผิดพลาด");
        setStep("form");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (step === "choose") {
    return <ChooseFileModal title={labels.title} files={files} onCancel={onClose} onChoose={choose} />;
  }

  if (step === "scanning") {
    return (
      <Dialog title="ปกปิดข้อมูลส่วนบุคคล (PDPA)" actions={<button type="button" className={SECONDARY} onClick={onClose}>ยกเลิก</button>}>
        <p>กำลังตรวจหาข้อมูลส่วนบุคคลใน <strong className="text-gray-900 break-all">{file.filename}</strong>...</p>
      </Dialog>
    );
  }

  if (step === "scan_error") {
    return (
      <Dialog title="ตรวจเอกสารไม่สำเร็จ" actions={<button type="button" className={PRIMARY} onClick={onClose} autoFocus>ปิด</button>}>
        <p className="text-red-700">{error}</p>
      </Dialog>
    );
  }

  if (step === "checking") {
    return (
      <Dialog title={labels.title} actions={<button type="button" className={SECONDARY} onClick={onClose}>ยกเลิก</button>}>
        <p>กำลังตรวจสอบเอกสาร...</p>
      </Dialog>
    );
  }

  if (step === "signed" && (action === "encrypt" || action === "compress")) {
    return (
      <Dialog title={`${labels.verb}ไม่ได้`} actions={<button type="button" className={PRIMARY} onClick={onClose} autoFocus>ตกลง</button>}>
        <p>
          <strong className="text-gray-900 break-all">{file.filename}</strong> มีลายเซ็นดิจิทัล {signedCount} รายการ
          การ{labels.verb}ต้องเขียนไฟล์ใหม่ทั้งไฟล์ ทำให้ลายเซ็นใช้ไม่ได้ จึง{labels.verb}เอกสารที่ลงนามแล้วไม่ได้
        </p>
      </Dialog>
    );
  }

  if (step === "signed") {
    return (
      <Dialog
        title="เอกสารนี้ลงนามแล้ว"
        actions={
          <>
            <button type="button" className={PRIMARY} onClick={onClose} autoFocus>ยกเลิก</button>
            <button type="button" className={SECONDARY} onClick={() => proceed()}>ทำต่อ (สร้างไฟล์ใหม่)</button>
          </>
        }
      >
        <p>
          <strong className="text-gray-900 break-all">{file.filename}</strong> มีลายเซ็นดิจิทัล {signedCount} รายการ
          เอกสารที่ลงนามแล้วไม่ควรแก้ไขอีก
        </p>
        <p className="p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200">
          ถ้า{labels.verb} ลายเซ็นใน<strong>ไฟล์ใหม่</strong>จะแสดงว่า "ไม่ถูกต้อง / เอกสารถูกแก้หลังลงนาม"
          — ไฟล์ต้นฉบับที่ลงนามไว้ยังอยู่เหมือนเดิม
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
        onSubmit={(pw) => (action === "pdpa" && !scan ? runScan(file, pw) : run(params, pw))}
      />
    );
  }

  if (step === "result") {
    if (result.status === "no_change") {
      return (
        <Dialog
          title="ลดขนาดเพิ่มไม่ได้แล้ว"
          actions={
            <>
              <button type="button" className={SECONDARY} onClick={onClose}>ปิด</button>
              {params?.compress_profile !== "screen" && (
                <button type="button" className={PRIMARY} onClick={() => setStep("form")}>เลือกระดับอื่น</button>
              )}
            </>
          }
        >
          <p>บีบอัด {file.filename} แล้วเล็กลงไม่ถึง 3% — ไม่ได้สร้างไฟล์ใหม่</p>
          <p className="text-xs text-gray-500">ไฟล์นี้อาจบีบอัดมาแล้ว หรือรูปในไฟล์ความละเอียดต่ำอยู่แล้ว
            {params?.compress_profile !== "screen" ? " — ลองระดับ \"เล็กสุด\" ซึ่งลดความละเอียดรูปมากที่สุด" : ""}</p>
        </Dialog>
      );
    }
    if (result.status === "not_found") {
      return (
        <Dialog
          title="ไม่พบคำที่ค้นหา"
          actions={
            <>
              <button type="button" className={SECONDARY} onClick={onClose}>ปิด</button>
              <button type="button" className={PRIMARY} onClick={() => setStep("form")}>ค้นหาคำอื่น</button>
            </>
          }
        >
          <p>ไม่พบ "<strong className="text-gray-900">{params.keyword}</strong>" ใน {file.filename} — ไม่ได้สร้างไฟล์ใหม่</p>
          {result.image_pages?.length > 0 && (
            <p className="mt-2 text-sm text-amber-800 bg-amber-50 rounded p-2" data-testid="image-pages-hint">
              หน้า {result.image_pages.join(", ")} มีรูปภาพ — ข้อความที่อยู่ในรูป (เช่น ลายเซ็นและชื่อผู้ลงนาม ตราประทับ
              เอกสารสแกน) ค้นหาด้วยคำไม่ได้ เปิดไฟล์แล้วใช้เครื่องมือกล่องทึบลากปิดทับแทน
            </p>
          )}
        </Dialog>
      );
    }
    return (
      <Dialog
        title={
          action === "watermark" ? "ใส่ลายน้ำเรียบร้อยแล้ว"
            : action === "page_numbers" ? `ใส่เลขหน้าแล้ว ${result.count} หน้า`
            : action === "encrypt" ? "เข้ารหัสเรียบร้อยแล้ว"
              : action === "pdpa" ? `ปกปิดข้อมูลแล้ว ${result.count} รายการ`
                : action === "compress" ? "ลดขนาดไฟล์เรียบร้อยแล้ว"
                : `เซ็นเซอร์แล้ว ${result.count} จุด`
        }
        actions={
          <>
            <button type="button" className={SECONDARY} onClick={onClose}>ปิด</button>
            <button type="button" className={PRIMARY} onClick={() => { onClose(); onOpenFile(result.file.session_id); }}>
              เปิดไฟล์
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
        <p>บันทึกเป็นไฟล์ใหม่: <strong className="text-gray-900 break-all">{result.file.filename}</strong></p>
        <p>ไฟล์เดิมยังอยู่เหมือนเดิม</p>
        {action === "pdpa" && result.report?.length > 0 && (
          <button type="button" className="text-blue-700 hover:underline" onClick={() => downloadPiiReport(result.report, file.filename)}>
            ดาวน์โหลดรายงานการปกปิด (CSV)
          </button>
        )}
        {action === "encrypt" && (
          <p className="p-3 rounded-lg bg-amber-50 text-amber-800 border border-amber-200">
            จำรหัสผ่านไว้ให้ดี — ถ้าลืม จะเปิดไฟล์ใหม่นี้ไม่ได้ และระบบกู้รหัสผ่านให้ไม่ได้
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
          subtitle={`${file.filename} — ระบบจะสร้างไฟล์ใหม่ที่ต้องใช้รหัสผ่านนี้เปิด (ไฟล์เดิมไม่เปลี่ยน)`}
          onCancel={onClose}
          pdfa={pdfa}
          onSubmit={(pw, encryption) => run({ new_password: pw, encryption })}
        />
      </>
    );
  }
  if (action === "pdpa") {
    return (
      <>
        {errorBox}
        <PdpaForm fileName={file.filename} scan={scan} submitting={submitting} onCancel={onClose} onSubmit={(p) => run(p)} />
      </>
    );
  }
  if (action === "compress") {
    return (
      <>
        {errorBox}
        <CompressForm file={file} submitting={submitting} initial={params} onCancel={onClose} onSubmit={(p) => run(p)} />
      </>
    );
  }
  if (action === "page_numbers") {
    return (
      <>
        {errorBox}
        <PageNumberModal fileName={file.filename} submitting={submitting} onClose={onClose} onSubmit={(payload) => run(payload)} />
      </>
    );
  }
  if (action === "watermark") {
    return (
      <>
        {errorBox}
        <WatermarkModal fileName={file.filename} submitting={submitting} onClose={onClose} onSubmit={(payload) => run(payload)} />
      </>
    );
  }
  return (
    <>
      {errorBox}
      <RedactForm fileName={file.filename} submitting={submitting} initial={params} onCancel={onClose} onSubmit={(p) => run(p)} />
    </>
  );
}
