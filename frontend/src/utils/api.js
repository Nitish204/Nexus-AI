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
export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)nexus_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

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
    credentials: "include",
  });
}

export async function getWsToken() {
  const res = await apiFetch("/api/auth/ws-token");
  if (!res.ok) throw new Error("Couldn't authenticate the live connection.");
  const data = await res.json();
  return data.ws_token;
}
