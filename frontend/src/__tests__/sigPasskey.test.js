import { describe, expect, it } from "vitest";
import { openSignatureBytes, sealSignatureBytes } from "../utils/sigPasskey.js";

describe("sigPasskey", () => {
  it("encrypts and decrypts signature PNG bytes with PRF key and label AAD", async () => {
    const prfKey = crypto.getRandomValues(new Uint8Array(32));
    const pngBytes = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 1, 2, 3, 4]);

    const sealed = await sealSignatureBytes(prfKey, pngBytes, "ลายเซ็นทางการ");
    expect(typeof sealed).toBe("string");
    expect(sealed.length).toBeGreaterThan(20);

    const opened = await openSignatureBytes(prfKey, sealed, "ลายเซ็นทางการ");
    expect(Array.from(opened)).toEqual(Array.from(pngBytes));
  });

  it("rejects decryption with wrong label (AAD mismatch) or wrong PRF key", async () => {
    const prfKey = crypto.getRandomValues(new Uint8Array(32));
    const wrongKey = crypto.getRandomValues(new Uint8Array(32));
    const pngBytes = new Uint8Array([137, 80, 78, 71, 9, 8, 7]);

    const sealed = await sealSignatureBytes(prfKey, pngBytes, "ลายเซ็น 1");
    await expect(openSignatureBytes(prfKey, sealed, "ลายเซ็น 2")).rejects.toThrow("passkey-unlock-failed");
    await expect(openSignatureBytes(wrongKey, sealed, "ลายเซ็น 1")).rejects.toThrow("passkey-unlock-failed");
  });
});
