// ปลดล็อกใบรับรองที่บันทึกไว้ด้วย passkey (ส่วนขยาย WebAuthn PRF) — backend: app/services/certificate_store.py
//
// ผูก: passkey ให้ค่าลับ 32 ไบต์ (ผูกกับ prf_salt สุ่ม) → HKDF → กุญแจ AES-GCM → เข้ารหัสรหัสผ่านของใบรับรอง **ในเครื่องนี้**
//      server เก็บแค่ prf_salt + wrapped (ไม่มีค่าลับจาก passkey → ถอดเองไม่ได้)
// ใช้:  ขอค่าลับเดิมจาก passkey → ถอด wrapped ได้รหัส → ส่งรหัสไปตรวจเหมือนพิมพ์เอง (นับครั้งผิด/ล็อกเหมือนเดิม)
// AAD = ลายนิ้วมือใบรับรอง — wrapped ของใบหนึ่งเอาไปใช้กับอีกใบไม่ได้
// Safari: ต้องเรียก navigator.credentials.get ทันทีจากการกดปุ่ม (ห้าม fetch คั่น) → ขอ options ไว้ก่อน / ใช้ข้อมูลจากรายการใบรับรอง
import { base64URLStringToBuffer as fromB64, bufferToBase64URLString as toB64 } from "@simplewebauthn/browser";
import { passkeyErrorMessage } from "../api/passkey.js";

const HKDF_INFO = new TextEncoder().encode("ja-pdf-editor/certificate-password/v1");
const IV_BYTES = 12;

export class PrfUnsupportedError extends Error {
  constructor() {
    super("prf-unsupported");
    this.name = "PrfUnsupportedError";
  }
}

export class PasskeyUnlockError extends Error {
  constructor() {
    super("passkey-unlock-failed");
    this.name = "PasskeyUnlockError";
  }
}

export function certPasskeyErrorMessage(err) {
  if (err?.name === "PrfUnsupportedError") {
    return "อุปกรณ์หรือเบราว์เซอร์นี้ยังใช้ passkey ปลดล็อกใบรับรองไม่ได้ (ต้องใช้ Chrome/Edge รุ่นใหม่, Android หรือ Safari บน iOS/macOS 18 ขึ้นไป) — กรอกรหัสผ่านแทนได้";
  }
  if (err?.name === "PasskeyUnlockError") {
    return "passkey นี้ปลดล็อกใบรับรองไม่ได้ — ผูก passkey ใหม่ที่หน้า “ความปลอดภัย” หรือกรอกรหัสผ่านแทน";
  }
  return passkeyErrorMessage(err);
}

export function supportsWebAuthn() {
  return typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials?.get;
}

const aadFor = (cert) => new TextEncoder().encode(`ja-pdf-cert:${cert.fingerprint_sha256}`);

async function aesKey(prfOutput) {
  const ikm = await crypto.subtle.importKey("raw", prfOutput, "HKDF", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: HKDF_INFO },
    ikm,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function sealPassword(prfOutput, password, cert) {
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: aadFor(cert) },
    await aesKey(prfOutput),
    new TextEncoder().encode(password),
  );
  const out = new Uint8Array(IV_BYTES + ct.byteLength);
  out.set(iv);
  out.set(new Uint8Array(ct), IV_BYTES);
  return toB64(out.buffer);
}

export async function openPassword(prfOutput, wrapped, cert) {
  const raw = new Uint8Array(fromB64(wrapped));
  try {
    const pt = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: raw.slice(0, IV_BYTES), additionalData: aadFor(cert) },
      await aesKey(prfOutput),
      raw.slice(IV_BYTES),
    );
    return new TextDecoder().decode(pt);
  } catch {
    throw new PasskeyUnlockError();
  }
}

// assertion → JSON แบบที่ py_webauthn รับ (ไม่ส่งผล PRF ไป server)
function assertionToJSON(cred) {
  const r = cred.response;
  return {
    id: cred.id,
    rawId: toB64(cred.rawId),
    type: cred.type,
    clientExtensionResults: {},
    authenticatorAttachment: cred.authenticatorAttachment ?? undefined,
    response: {
      clientDataJSON: toB64(r.clientDataJSON),
      authenticatorData: toB64(r.authenticatorData),
      signature: toB64(r.signature),
      userHandle: r.userHandle ? toB64(r.userHandle) : undefined,
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
  id: fromB64(id),
  ...(transports?.length ? { transports } : {}),
});

// ผูก passkey กับใบรับรอง — prepared = { flow_id, options } จาก api.prepareCertificatePasskey (ขอไว้ก่อนกด)
// คืน payload สำหรับ api.bindCertificatePasskey
export async function wrapWithPasskey({ prepared, password, cert }) {
  const { flow_id, options } = prepared;
  const salt = crypto.getRandomValues(new Uint8Array(32));
  const cred = await navigator.credentials.get({
    publicKey: {
      challenge: fromB64(options.challenge),
      rpId: options.rpId,
      timeout: options.timeout,
      userVerification: "required",
      allowCredentials: (options.allowCredentials || []).map((c) => descriptor(c.id, c.transports)),
      extensions: { prf: { eval: { first: salt } } },
    },
  });
  const wrapped = await sealPassword(prfOutputOf(cred), password, cert);
  return { flow_id, credential: assertionToJSON(cred), password, prf_salt: toB64(salt.buffer), wrapped };
}

// ถอดรหัสผ่านของใบรับรองด้วย passkey ที่ผูกไว้ (cert.passkeys จาก api.listCertificates) — ไม่ต้องคุยกับ server ก่อน
export async function unlockWithPasskey(cert) {
  const bindings = (cert.passkeys || []).filter((b) => b.credential_id);
  if (!bindings.length) throw new PasskeyUnlockError();
  const evalByCredential = {};
  for (const b of bindings) evalByCredential[b.credential_id] = { first: fromB64(b.prf_salt) };
  const cred = await navigator.credentials.get({
    publicKey: {
      challenge: crypto.getRandomValues(new Uint8Array(32)),
      rpId: bindings[0].rp_id,
      timeout: 120000,
      userVerification: "required",
      allowCredentials: bindings.map((b) => descriptor(b.credential_id, b.transports)),
      extensions: { prf: { evalByCredential } },
    },
  });
  const output = prfOutputOf(cred);
  const binding = bindings.find((b) => b.credential_id === cred.id);
  if (!binding) throw new PasskeyUnlockError();
  return openPassword(output, binding.wrapped, cert);
}
