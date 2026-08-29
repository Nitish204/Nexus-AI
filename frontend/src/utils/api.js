/**
 * NEXUS — shared fetch helper for the cookie-based auth session.
 *
 * The access token is no longer stored in localStorage or attached as
 * a manual Authorization header from here — the backend sets it as an
 * httpOnly cookie on login/signup, which the browser attaches to same-
 * site requests automatically and which JavaScript can never read
 * (so an XSS bug elsewhere in the app can't exfiltrate it, unlike the
 * old localStorage approach).
 *
 * Because that cookie is sent automatically, every state-changing
 * request also needs a CSRF token to prove the request actually came
 * from this app and not a malicious third-party page silently
 * triggering an authenticated request in the background. The backend
 * pairs the session cookie with a second, JS-readable "nexus_csrf"
 * cookie for exactly this purpose (the "double-submit cookie" pattern)
 * — read it here and echo it back as a header.
 */

// In production this is empty on purpose: vercel.json rewrites
// "/api/*" to the real backend, making every request same-origin from
// the browser's point of view (no CORS preflight, and critically, the
// session cookie becomes first-party instead of third-party — which
// several browsers, Safari by default and Chrome increasingly, refuse
// to send/store at all for a cross-domain request). Locally there's no
// such proxy running (unless using `vercel dev`), so dev falls back to
// hitting the backend directly.
export const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? "http://localhost:8000" : "");
// Used only for the WebSocket, which connects to the real backend
// domain directly (see the comment on getWsToken below for why that's
// fine even though every other request goes through the proxy).
export const BACKEND_WS_ORIGIN =
  import.meta.env.VITE_BACKEND_WS_ORIGIN || "wss://nexus-ai-wqx2.onrender.com";

function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)nexus_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Drop-in replacement for fetch() against the NEXUS API: always sends
 * the session cookie, and automatically attaches the CSRF header on
 * any request that changes state.
 */
export function apiFetch(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };

  if (MUTATING_METHODS.has(method)) {
    const csrf = getCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  return fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    headers,
    credentials: "include", // send/receive the httpOnly session cookie
  });
}

/**
 * A short-lived, single-purpose token for the WebSocket connection.
 * WebSocket auth can't ride on the httpOnly cookie the same way HTTP
 * requests do (the browser's WebSocket API doesn't support custom
 * headers, and depending on the deployment's cross-site cookie
 * settings, cookies aren't guaranteed to be sent on the handshake
 * either) — so the frontend asks the backend for a fresh, narrowly-
 * scoped token right before opening the socket instead of ever
 * persisting the main session token in JS-accessible storage.
 */
export async function getWsToken() {
  const res = await apiFetch("/api/auth/ws-token");
  if (!res.ok) throw new Error("Couldn't authenticate the live connection.");
  const data = await res.json();
  return data.ws_token;
}
