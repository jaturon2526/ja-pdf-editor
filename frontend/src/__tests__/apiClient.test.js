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
    globalThis.localStorage = mockStorage();
    globalThis.sessionStorage = mockStorage();
    globalThis.window = { location: { href: "/editor/1" } };
    globalThis.document = { cookie: "other=1; ja_csrf=csrf%2Dabc" };
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
    delete globalThis.window;
    delete globalThis.document;
  });

  it("sends the CSRF cookie back as a header and never a bearer token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { fetchWithAuth, isLoggedIn } = await import("../api/client.js");
    await fetchWithAuth("/api/x", { method: "POST", headers: { "Content-Type": "application/json" } });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.headers.get("X-CSRF-Token")).toBe("csrf-abc");
    expect(opts.headers.get("Content-Type")).toBe("application/json");
    expect(opts.headers.get("Authorization")).toBeNull();
    expect(opts.credentials).toBe("same-origin");
    expect(isLoggedIn()).toBe(true);
  });

  it("redirects to login and forgets the local session on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
    const { fetchWithAuth } = await import("../api/client.js");
    await expect(fetchWithAuth("/api/x")).rejects.toThrow("Unauthorized");
    expect(document.cookie).toContain("ja_csrf=; Max-Age=0");
    expect(window.location.href).toBe("/login?expired=1");
  });

  it("login asks the backend for a cookie session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ token_type: "cookie" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { authLogin } = await import("../api/auth.js");
    await authLogin("a@example.com", "pw");
    expect(fetchMock.mock.calls[0][1].headers["X-Auth-Mode"]).toBe("cookie");
  });

  it("moves a legacy localStorage token into a cookie once", async () => {
    localStorage.setItem("token", "old");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { migrateLegacyToken } = await import("../api/client.js");
    await migrateLegacyToken();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/session/cookie");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer old");
    expect(localStorage.getItem("token")).toBeNull();
    await migrateLegacyToken();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("login with a wrong password shows the backend message instead of 'session expired'", async () => {
    const body = JSON.stringify({ detail: "อีเมลหรือรหัสผ่านไม่ถูกต้อง" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 401 })));
    const { authLogin } = await import("../api/auth.js");
    await expect(authLogin("a@example.com", "wrong")).rejects.toThrow("อีเมลหรือรหัสผ่านไม่ถูกต้อง");
    expect(window.location.href).toBe("/editor/1"); // ไม่เด้งไป /login?expired=1
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
