import { beforeEach, describe, expect, it, vi } from "vitest";

// api.js reads import.meta.env.VITE_API_BASE / DEV at module load time,
// so API_BASE just needs to resolve to *some* string here — the tests
// below only assert on how apiFetch calls the global fetch(), not on
// what origin it targets.
import { apiFetch } from "./api";

describe("apiFetch", () => {
  beforeEach(() => {
    document.cookie = "";
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, json: async () => ({}) })));
  });

  it("always sends credentials so the httpOnly session cookie is included", async () => {
    await apiFetch("/api/projects");
    const [, options] = fetch.mock.calls[0];
    expect(options.credentials).toBe("include");
  });

  it("does not attach an X-CSRF-Token header on a plain GET", async () => {
    await apiFetch("/api/projects");
    const [, options] = fetch.mock.calls[0];
    expect(options.headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("attaches X-CSRF-Token from the nexus_csrf cookie on a POST", async () => {
    document.cookie = "nexus_csrf=abc123";
    await apiFetch("/api/projects", { method: "POST", body: "{}" });
    const [, options] = fetch.mock.calls[0];
    expect(options.headers["X-CSRF-Token"]).toBe("abc123");
  });

  it("omits the CSRF header on a mutating request when no csrf cookie exists yet", async () => {
    await apiFetch("/api/projects", { method: "DELETE" });
    const [, options] = fetch.mock.calls[0];
    expect(options.headers["X-CSRF-Token"]).toBeUndefined();
  });

  it("URL-decodes a percent-encoded csrf cookie value", async () => {
    document.cookie = `nexus_csrf=${encodeURIComponent("a b/c")}`;
    await apiFetch("/api/projects", { method: "PUT" });
    const [, options] = fetch.mock.calls[0];
    expect(options.headers["X-CSRF-Token"]).toBe("a b/c");
  });

  it("preserves caller-supplied headers alongside the default Content-Type", async () => {
    await apiFetch("/api/projects", { headers: { "X-Custom": "1" } });
    const [, options] = fetch.mock.calls[0];
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(options.headers["X-Custom"]).toBe("1");
  });

  it("uppercases a lowercase method before checking whether it mutates", async () => {
    document.cookie = "nexus_csrf=abc123";
    await apiFetch("/api/projects", { method: "post" });
    const [, options] = fetch.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.headers["X-CSRF-Token"]).toBe("abc123");
  });
});
