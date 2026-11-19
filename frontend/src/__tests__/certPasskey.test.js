// ปลดล็อกใบรับรองด้วย passkey: เข้ารหัส/ถอดรหัสในเบราว์เซอร์ด้วยค่า PRF (ไม่มีค่านี้ = ถอดไม่ได้)
import { afterEach, describe, expect, it, vi } from "vitest";
import { bufferToBase64URLString as toB64 } from "@simplewebauthn/browser";
import { PasskeyUnlockError, PrfUnsupportedError, openPassword, sealPassword, unlockWithPasskey, wrapWithPasskey } from "../utils/certPasskey.js";

const CERT = { id: 7, fingerprint_sha256: "ab".repeat(32) };
const prf = (byte) => new Uint8Array(32).fill(byte).buffer;
const bytes = (n, fill) => new Uint8Array(n).fill(fill).buffer;

// credential ที่ navigator.credentials.get คืน (เฉพาะส่วนที่ utils ใช้)
function fakeCredential(id, prfOut) {
  return {
    id: toB64(id),
    rawId: id,
    type: "public-key",
    response: { clientDataJSON: bytes(4, 1), authenticatorData: bytes(4, 2), signature: bytes(4, 3), userHandle: null },
    getClientExtensionResults: () => (prfOut ? { prf: { results: { first: prfOut } } } : {}),
  };
}

function stubGet(impl) {
  vi.stubGlobal("navigator", { credentials: { get: vi.fn(impl) } });
  return navigator.credentials.get;
}

afterEach(() => vi.unstubAllGlobals());

describe("certPasskey", () => {
  it("ถอดได้เฉพาะค่า PRF เดิม และเฉพาะใบรับรองเดิม", async () => {
    const wrapped = await sealPassword(prf(1), "รหัส-p12-pass", CERT);
    expect(await openPassword(prf(1), wrapped, CERT)).toBe("รหัส-p12-pass");
    await expect(openPassword(prf(2), wrapped, CERT)).rejects.toBeInstanceOf(PasskeyUnlockError);
    await expect(openPassword(prf(1), wrapped, { ...CERT, fingerprint_sha256: "cd".repeat(32) }))
      .rejects.toBeInstanceOf(PasskeyUnlockError);
  });

  it("ผูกแล้วปลดล็อกได้ — ส่ง PRF ตามรายการ credential ที่ผูก และไม่ส่งค่า PRF ไป server", async () => {
    const credId = bytes(16, 9);
    let salt;
    stubGet(async ({ publicKey }) => {
      salt = publicKey.extensions.prf.eval.first;
      expect(publicKey.userVerification).toBe("required");
      return fakeCredential(credId, prf(5));
    });
    const prepared = { flow_id: "f1", options: { challenge: toB64(bytes(32, 0)), rpId: "localhost", allowCredentials: [{ id: toB64(credId), type: "public-key" }] } };
    const payload = await wrapWithPasskey({ prepared, password: "p12-pass", cert: CERT });
    expect(payload.flow_id).toBe("f1");
    expect(payload.prf_salt).toBe(toB64(salt.buffer));
    expect(payload.credential.clientExtensionResults).toEqual({});
    expect(JSON.stringify(payload)).not.toContain(toB64(prf(5)));

    const cert = { ...CERT, passkeys: [{ id: 1, credential_id: toB64(credId), rp_id: "localhost", transports: ["internal"], prf_salt: payload.prf_salt, wrapped: payload.wrapped }] };
    const get = stubGet(async () => fakeCredential(credId, prf(5)));
    expect(await unlockWithPasskey(cert)).toBe("p12-pass");
    const { publicKey } = get.mock.calls[0][0];
    expect(publicKey.rpId).toBe("localhost");
    expect(Object.keys(publicKey.extensions.prf.evalByCredential)).toEqual([toB64(credId)]);
  });

  it("เบราว์เซอร์ไม่คืนค่า PRF → บอกว่าไม่รองรับ", async () => {
    stubGet(async () => fakeCredential(bytes(16, 9), null));
    const cert = { ...CERT, passkeys: [{ id: 1, credential_id: toB64(bytes(16, 9)), rp_id: "localhost", transports: [], prf_salt: toB64(bytes(32, 1)), wrapped: "AAAA" }] };
    await expect(unlockWithPasskey(cert)).rejects.toBeInstanceOf(PrfUnsupportedError);
  });
});
