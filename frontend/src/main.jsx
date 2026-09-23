import React from "react";
import ReactDOM from "react-dom/client";
import * as Sentry from "@sentry/react";
import App from "./App.jsx";
import { initSentry } from "./lib/sentry.js";
import { registerServiceWorker } from "./utils/push.js";

initSentry();

// Registered unconditionally at load (not only when the user opts into
// push, as before) so the offline app-shell cache in public/sw.js
// actually applies to everyone who installs/revisits NEXUS, not just
// push subscribers. registerServiceWorker() itself already no-ops
// safely when the browser doesn't support service workers.
registerServiceWorker().catch(() => {
  // Non-fatal: the app works fully online without a service worker,
  // it just loses the offline-shell fallback and push notifications.
});

function ErrorFallback({ error, resetError }) {
  return (
    <div style={{ padding: 32, fontFamily: "sans-serif", color: "#2e2e3a" }}>
      <h2>Something went wrong.</h2>
      <p style={{ color: "#8a8a9a" }}>
        The error has been reported. Try reloading the page.
      </p>
      <button onClick={resetError} style={{ marginTop: 12 }}>
        Try again
      </button>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Sentry.ErrorBoundary fallback={ErrorFallback}>
      <App />
    </Sentry.ErrorBoundary>
  </React.StrictMode>
);
