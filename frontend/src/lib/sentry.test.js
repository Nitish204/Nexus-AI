import { describe, expect, it, vi } from "vitest";

vi.mock("@sentry/react", () => ({
  init: vi.fn(),
  browserTracingIntegration: vi.fn(() => ({})),
}));

import * as Sentry from "@sentry/react";
import { initSentry } from "./sentry";

describe("initSentry", () => {
  it("is a no-op and returns false when VITE_SENTRY_DSN isn't set", () => {
    // The test environment has no VITE_SENTRY_DSN configured (see
    // vite.config.js / .env.example) — this must never throw or
    // silently phone home in dev/CI.
    const result = initSentry();
    expect(result).toBe(false);
    expect(Sentry.init).not.toHaveBeenCalled();
  });
});
