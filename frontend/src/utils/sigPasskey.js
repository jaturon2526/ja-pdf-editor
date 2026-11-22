// เข้ารหัสและปลดล็อกรูปลายเซ็นด้วย Passkey (WebAuthn PRF, v1.48.0) — backend: app/services/signature_store.py
//
// บันทึก: passkey ให้ค่าลับ 32 ไบต์ (ผูกกับ prf_salt สุ่ม) → HKDF → กุญแจ AES-GCM 256-bit → เข้ารหัส PNG ในเบราว์เซอร์
//         server เก็บเฉพาะ prf_salt + ciphertext (ไม่เคยเห็นรูปลายเซ็นจริง)
// ใช้งาน: ขอค่าลับเดิมจาก passkey → ถอด ciphertext เป็น PNG data URL ในหน่วยความจำเบราว์เซอร์เท่านั้น
// Safari: ต้องเรียก navigator.credentials.get ทันทีจากการกดปุ่ม (ห้าม fetch คั่น) — จึงโหลด prepared/blob ไว้ล่วงหน้า
import { base64URLStringToBuffer as fromB64Url, bufferToBase64URLString as toB64Url } from "@simplewebauthn/browser";
import { passkeyErrorMessage } from "../api/passkey.js";
import { PasskeyUnlockError, PrfUnsupportedError, supportsWebAuthn } from "./certPasskey.js";

export { PasskeyUnlockError, PrfUnsupportedError, supportsWebAuthn };

const HKDF_INFO = new TextEncoder().encode("ja-pdf-editor/saved-signature/v1");
const IV_BYTES = 12;

export function sigPasskeyErrorMessage(err) {
  if (err?.name === "PrfUnsupportedError") {
    return "อุปกรณ์หรือเบราว์เซอร์นี้ยังไม่รองรับ Passkey PRF สำหรับเข้ารหัสลายเซ็น (ต้องใช้ Chrome/Edge รุ่นใหม่, Android หรือ Safari บน iOS/macOS 18 ขึ้นไป)";
  }
  if (err?.name === "PasskeyUnlockError") {
    return "Passkey นี้ปลดล็อกรูปลายเซ็นไม่ได้ กรุณาใช้ Passkey อันเดียวกับที่บันทึกไว้";
  }
  return passkeyErrorMessage(err);
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function base64ToBytes(b64) {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

export function dataUrlToBytes(dataUrl) {
  const idx = dataUrl.indexOf(",");
  const b64 = idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
  return base64ToBytes(b64);
}

export function bytesToPngDataUrl(bytes) {
  return `data:image/png;base64,${bytesToBase64(bytes)}`;
}

const aadFor = (label) => new TextEncoder().encode(`ja-pdf-sig:${label}`);

async function deriveAesKey(prfOutput) {
  const ikm = await crypto.subtle.importKey("raw", prfOutput, "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: HKDF_INFO },
    ikm,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function sealSignatureBytes(prfOutput, pngBytes, label) {
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: aadFor(label) },
    await deriveAesKey(prfOutput),
    pngBytes,
  );
  const out = new Uint8Array(IV_BYTES + ct.byteLength);
  out.set(iv);
  out.set(new Uint8Array(ct), IV_BYTES);
  return bytesToBase64(out);
}

export async function openSignatureBytes(prfOutput, encryptedB64, label) {
  const raw = base64ToBytes(encryptedB64);
  try {
    const pt = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: raw.slice(0, IV_BYTES), additionalData: aadFor(label) },
      await deriveAesKey(prfOutput),
      raw.slice(IV_BYTES),
    );
    return new Uint8Array(pt);
  } catch {
    throw new PasskeyUnlockError();
  }
}

function assertionToJSON(cred) {
  const r = cred.response;
  return {
    id: cred.id,
    rawId: toB64Url(cred.rawId),
    type: cred.type,
    clientExtensionResults: {},
    authenticatorAttachment: cred.authenticatorAttachment ?? undefined,
    response: {
      clientDataJSON: toB64Url(r.clientDataJSON),
      authenticatorData: toB64Url(r.authenticatorData),
      signature: toB64Url(r.signature),
      userHandle: r.userHandle ? toB64Url(r.userHandle) : undefined,
    },
  };
}

function prfOutputOf(cred) {
  const out = cred?.getClientExtensionResults?.()?.prf?.results?.first;
  if (!out) throw new PrfUnsupportedError();
  return out;
}

const descriptor = (id, transports) => ({
  type: "public-key",
  id: fromB64Url(id),
  ...(transports?.length ? { transports } : {}),
});

// เข้ารหัสรูปลายเซ็นด้วย Passkey — prepared = { flow_id, options } จาก api.prepareSavedSignatureOptions (ขอไว้ก่อนกดปุ่ม)
export async function sealSignatureWithPasskey({ prepared, pngBytes, label }) {
  const { flow_id, options } = prepared;
  const cleanLabel = label.trim() || "ลายเซ็นของฉัน";
  const salt = crypto.getRandomValues(new Uint8Array(32));
  const cred = await navigator.credentials.get({
    publicKey: {
      challenge: fromB64Url(options.challenge),
      rpId: options.rpId,
      allowCredentials: (options.allowCredentials || []).map((c) => descriptor(c.id, c.transports)),
      userVerification: "required",
      timeout: options.timeout || 60000,
      extensions: { prf: { eval: { first: salt } } },
    },
  });
  const encrypted_png_b64 = await sealSignatureBytes(prfOutputOf(cred), pngBytes, cleanLabel);
  return {
    flow_id,
    credential: assertionToJSON(cred),
    label: cleanLabel,
    prf_salt: toB64Url(salt.buffer),
    encrypted_png_b64,
  };
}

// ปลดล็อกรูปลายเซ็นที่บันทึกไว้ด้วย Passkey (เรียกตรงจากการกดปุ่ม — ห้ามมี fetch คั่นก่อนคำสั่งนี้)
export async function unlockSignatureWithPasskey(blob) {
  const challenge = crypto.getRandomValues(new Uint8Array(32));
  const cred = await navigator.credentials.get({
    publicKey: {
      challenge,
      rpId: blob.rp_id,
      allowCredentials: [descriptor(blob.credential_id, blob.transports)],
      userVerification: "required",
      timeout: 60000,
      extensions: {
        prf: {
          evalByCredential: {
            [blob.credential_id]: { first: fromB64Url(blob.prf_salt) },
          },
        },
      },
    },
  });
  const pngBytes = await openSignatureBytes(prfOutputOf(cred), blob.encrypted_png_b64, blob.label);
  return bytesToPngDataUrl(pngBytes);
}
