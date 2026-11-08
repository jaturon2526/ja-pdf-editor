import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

function mockStorage(initial = {}) {
  const store = { ...initial };
  return {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  };
}

describe("api client", () => {
  beforeEach(() => {
    vi.resetModules();
    globalThis.localStorage = mockStorage({ token: "abc" });
    globalThis.window = { location: { href: "/editor/1" } };
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    delete globalThis.localStorage;
    delete globalThis.window;
  });

  it("attaches the bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { fetchWithAuth } = await import("../api/client.js");
    await fetchWithAuth("/api/x");
    expect(fetchMock.mock.calls[0][1].headers.get("Authorization")).toBe("Bearer abc");
  });

  it("redirects to login and clears token on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
    const { fetchWithAuth } = await import("../api/client.js");
    await expect(fetchWithAuth("/api/x")).rejects.toThrow("Unauthorized");
    expect(localStorage.getItem("token")).toBeNull();
    expect(window.location.href).toBe("/login?expired=1");
  });

  it("login with a wrong password shows the backend message instead of 'session expired'", async () => {
    const body = JSON.stringify({ detail: "อีเมลหรือรหัสผ่านไม่ถูกต้อง" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 401 })));
    const { authLogin } = await import("../api/auth.js");
    await expect(authLogin("a@example.com", "wrong")).rejects.toThrow("อีเมลหรือรหัสผ่านไม่ถูกต้อง");
    expect(window.location.href).toBe("/editor/1"); // ไม่เด้งไป /login?expired=1
    expect(localStorage.getItem("token")).toBe("abc");
  });

  it("fetchBlob decodes UTF-8 filenames from Content-Disposition", async () => {
    const headers = { "Content-Disposition": "attachment; filename*=utf-8''%E0%B9%80%E0%B8%AD%E0%B8%81.pdf" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("pdf", { status: 200, headers })));
    const { fetchBlob } = await import("../api/client.js");
    const { filename, blob } = await fetchBlob("/api/pdf/1/download");
    expect(filename).toBe("เอก.pdf");
    expect(await blob.text()).toBe("pdf");
  });

  it("fetchBlob surfaces backend error detail", async () => {
    const body = JSON.stringify({ detail: "ไม่พบ session นี้" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 404 })));
    const { fetchBlob } = await import("../api/client.js");
    await expect(fetchBlob("/api/pdf/1/download")).rejects.toThrow("ไม่พบ session นี้");
  });

  it("barrel api.js still exposes every module", async () => {
    const api = await import("../api.js");
    for (const name of ["uploadPdf", "renderPage", "addAnnotation", "editText", "digitalSign", "getAdminStats", "authLogin", "downloadPdf"]) {
      expect(typeof api[name]).toBe("function");
    }
  });
});
