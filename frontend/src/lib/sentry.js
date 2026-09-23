/**
 * NEXUS — frontend error tracking (Sentry).
 *
 * Mirrors the backend's app/core/observability.py: a missing DSN is a
 * completely normal, silent no-op (every local dev/CI run is in this
 * state), not a misconfiguration to warn about loudly.
 */
import * as Sentry from "@sentry/react";

const dsn = import.meta.env.VITE_SENTRY_DSN;

export function initSentry() {
  if (!dsn) return false;

  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_RELEASE_VERSION || "unknown",
    integrations: [Sentry.browserTracingIntegration()],
    // Kept low: this is a per-pageview cost multiplier, not a one-time
    // toggle, and NEXUS's own WebSocket-driven UI already generates a
    // lot of transactions.
    tracesSampleRate: 0.1,
    // Session Replay is off by default — it captures DOM snapshots,
    // and this app renders user-typed feature requests and AI-authored
    // source code, neither of which should be replayed to Sentry
    // without an explicit decision to do so.
  });
  return true;
}
