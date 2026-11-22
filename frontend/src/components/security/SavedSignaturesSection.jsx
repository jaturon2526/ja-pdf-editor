// ส่วน "รูปลายเซ็นที่บันทึกไว้" ในหน้าความปลอดภัย (v1.48.0):
// อัปโหลดรูปลายเซ็น (ลบพื้นหลังขาวอัตโนมัติ) → เข้ารหัสในเบราว์เซอร์ด้วย Passkey (WebAuthn PRF) → เก็บ ciphertext บนระบบ
// เวลาเซ็นเอกสารค่อยปลดล็อกด้วย Passkey — เซิร์ฟเวอร์ไม่เคยเห็นรูปลายเซ็นจริง
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteSavedSignature,
  listSavedSignatures,
  prepareSavedSignatureOptions,
  saveEncryptedSignature,
} from "../../api/signature.js";
import { cleanSignatureImage } from "../signature/SignatureCreator.jsx";
import {
  dataUrlToBytes,
  sealSignatureWithPasskey,
  sigPasskeyErrorMessage,
  supportsWebAuthn,
} from "../../utils/sigPasskey.js";

const FRESH_MS = 4 * 60 * 1000;

export default function SavedSignaturesSection({ passkeyVersion = 0 } = {}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [prepared, setPrepared] = useState(null);
  const [noPasskey, setNoPasskey] = useState(false);

  const [label, setLabel] = useState("");
  const [rawImage, setRawImage] = useState(null);
  const [removeBg, setRemoveBg] = useState(true);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const fileRef = useRef(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listSavedSignatures();
      setItems(list || []);
    } catch (err) {
      setError(err?.message || "โหลดรายการรูปลายเซ็นไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
    try {
      const opt = await prepareSavedSignatureOptions();
      setPrepared(opt);
      setNoPasskey(false);
    } catch {
      setPrepared(null);
      setNoPasskey(true);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll, passkeyVersion]);

  useEffect(() => {
    if (!rawImage) {
      setPreviewUrl(null);
      return undefined;
    }
    let cancelled = false;
    cleanSignatureImage(rawImage, removeBg)
      .then((url) => { if (!cancelled) setPreviewUrl(url); })
      .catch(() => { if (!cancelled) setPreviewUrl(rawImage); });
    return () => { cancelled = true; };
  }, [rawImage, removeBg]);

  function handleFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("กรุณาเลือกไฟล์รูปภาพ (PNG, JPG, WebP)");
      return;
    }
    setError("");
    setSuccess("");
    const reader = new FileReader();
    reader.onload = () => setRawImage(String(reader.result || ""));
    reader.readAsDataURL(file);
  }

  async function handleSave() {
    if (!previewUrl || submitting) return;
    if (!supportsWebAuthn()) {
      setError("เบราว์เซอร์หรือที่อยู่เว็บนี้ไม่รองรับ Passkey (ต้องเป็น https หรือ localhost)");
      return;
    }
    setSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const opt = prepared && Date.now() - prepared.at < FRESH_MS
        ? prepared
        : await prepareSavedSignatureOptions();
      const pngBytes = dataUrlToBytes(previewUrl);
      const cleanLabel = label.trim() || `ลายเซ็น ${items.length + 1}`;
      const payload = await sealSignatureWithPasskey({ prepared: opt, pngBytes, label: cleanLabel });
      await saveEncryptedSignature(payload);
      setLabel("");
      setRawImage(null);
      setPreviewUrl(null);
      setSuccess(`บันทึกรูปลายเซ็น "${cleanLabel}" และล็อกด้วย Passkey เรียบร้อยแล้ว`);
      await loadAll();
    } catch (err) {
      const msg = sigPasskeyErrorMessage(err);
      if (msg) setError(msg);
      // ขอ challenge ใหม่เผื่ออันเดิมถูกใช้ไปแล้ว
      prepareSavedSignatureOptions().then(setPrepared).catch(() => {});
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(item) {
    if (deletingId) return;
    setDeletingId(item.id);
    setError("");
    setSuccess("");
    try {
      await deleteSavedSignature(item.id);
      setSuccess(`ลบรูปลายเซ็น "${item.label}" แล้ว`);
      await loadAll();
    } catch (err) {
      setError(err?.message || "ลบรูปลายเซ็นไม่สำเร็จ");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section
      className="mt-10 pt-6 border-t border-gray-200"
      aria-labelledby="saved-sigs-heading"
      data-testid="saved-sig-section"
    >
      <h2 id="saved-sigs-heading" className="text-lg font-semibold text-gray-900 mb-1">
        รูปลายเซ็นที่บันทึกไว้ (ล็อกด้วย Passkey)
      </h2>
      <p className="text-sm text-gray-600 mb-4">
        อัปโหลดรูปลายเซ็นเก็บไว้เรียกใช้ซ้ำได้ทั้งลายเซ็นอิเล็กทรอนิกส์และลายเซ็นดิจิทัล — รูปลายเซ็นถูกเข้ารหัสในอุปกรณ์ของคุณด้วย Passkey ระบบไม่สามารถเปิดดูรูปลายเซ็นจริงได้ (สูงสุด 5 อัน)
      </p>

      {error && <div role="alert" className="mb-3 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">{error}</div>}
      {success && <div role="status" className="mb-3 p-3 rounded-lg bg-green-50 border border-green-200 text-sm text-green-700">{success}</div>}

      {/* รายการรูปลายเซ็นที่บันทึกไว้ */}
      {loading ? (
        <p className="text-sm text-gray-500 mb-4">กำลังโหลด...</p>
      ) : items.length > 0 && (
        <ul className="space-y-2 mb-5" data-testid="saved-sig-list">
          {items.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border border-gray-200 bg-gray-50">
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate">{item.label}</div>
                <div className="text-xs text-gray-500">
                  ล็อกด้วย Passkey: {item.passkey_name}
                </div>
              </div>
              <button
                type="button"
                disabled={deletingId === item.id}
                onClick={() => void handleDelete(item)}
                className="px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 border border-red-200 rounded-lg disabled:opacity-50"
              >
                {deletingId === item.id ? "กำลังลบ..." : "ลบ"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* ฟอร์มอัปโหลดและล็อกด้วย Passkey */}
      {noPasskey ? (
        <div className="p-3.5 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800">
          ต้องเพิ่ม <strong>Passkey</strong> ด้านบนอย่างน้อย 1 อันก่อน จึงจะบันทึกรูปลายเซ็นแบบเข้ารหัสได้
        </div>
      ) : items.length < 5 && (
        <div className="p-4 rounded-xl border border-gray-200 bg-gray-50/70 space-y-3">
          <div>
            <label htmlFor="saved-sig-label" className="block text-xs font-medium text-gray-700 mb-1">
              ชื่อรูปลายเซ็น
            </label>
            <input
              id="saved-sig-label"
              type="text"
              maxLength={100}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="เช่น ลายเซ็นทางการ, ลายเซ็นย่อ"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={handleFileChange}
              className="hidden"
              data-testid="saved-sig-file-input"
            />
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="px-3.5 py-2 text-xs font-medium text-gray-700 bg-white hover:bg-gray-100 border border-gray-300 rounded-lg"
              >
                {rawImage ? "เปลี่ยนรูปลายเซ็น" : "เลือกรูปลายเซ็น (PNG / JPG)"}
              </button>
              <label className="inline-flex items-center gap-2 text-xs text-gray-700 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={removeBg}
                  onChange={(e) => setRemoveBg(e.target.checked)}
                  className="rounded border-gray-300 text-blue-600"
                />
                <span>ลบพื้นหลังสีขาวอัตโนมัติ</span>
              </label>
            </div>
          </div>

          {previewUrl && (
            <div className="rounded-lg border border-gray-200 bg-white p-3 flex items-center justify-center max-h-36 overflow-hidden">
              <img src={previewUrl} alt="ตัวอย่างรูปลายเซ็น" className="max-h-28 w-auto object-contain" />
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              disabled={!previewUrl || submitting}
              onClick={() => void handleSave()}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
            >
              {submitting ? "กำลังเข้ารหัสและบันทึก..." : "บันทึกด้วย Passkey"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
