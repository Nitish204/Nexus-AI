// NEXUS service worker.
//
// Scope: push notifications (see below) plus a minimal app-shell cache
// so re-opening the installed PWA when briefly offline shows a real
// "you're offline" screen instead of a blank tab or the browser's own
// dinosaur-game error page. This is NOT a full offline-first app —
// NEXUS's actual product (talking to LLM agents, streaming code over
// a WebSocket, running sandboxed builds) fundamentally requires a live
// backend connection, so caching API responses or generated code for
// offline editing would be misleading rather than helpful. See
// docs/adr/0001-pwa-not-native-mobile.md for the full reasoning.
const SHELL_CACHE = "nexus-shell-v1";
// Precached at install time: just enough that the tab itself opens
// (HTML/CSS/JS entry + icons). Hashed build assets from `dist/assets/`
// are deliberately NOT enumerated here — their filenames change on
// every build, so precaching a fixed list would go stale immediately.
// They're instead cached opportunistically the first time each is
// actually fetched (see the fetch handler below), which is safe
// because Vite's hashed filenames are already content-addressed —
// caching one forever is correct, never a staleness bug.
const SHELL_ASSETS = ["/", "/index.html", "/manifest.json", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => {
      // Precaching is a best-effort optimization, not a hard
      // requirement — if a device is offline during the SW's own
      // install (unusual, but possible on a flaky connection), don't
      // fail installation entirely and lose push notification support
      // over it.
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only ever intercept same-origin GETs. Everything NEXUS actually
  // depends on being fresh — /api/* calls, the WebSocket upgrade,
  // OAuth redirects — is either cross-origin (hits the backend
  // directly, see BACKEND_WS_ORIGIN in utils/api.js) or a non-GET
  // method, both of which this check already excludes, so there's no
  // risk of this SW serving a stale API response.
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  // Never intercept API calls even if a future same-origin proxy setup
  // routes them through this origin (see vercel.json's /api/* rewrite)
  // — those must always hit the network.
  if (new URL(request.url).pathname.startsWith("/api/")) {
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached || caches.match("/index.html"));
      // Stale-while-revalidate: serve the cached shell instantly if we
      // have one (fast repeat opens, and what makes offline opens
      // work at all), but still fetch in the background so the next
      // open picks up a new deploy rather than being stuck forever.
      return cached || network;
    })
  );
});

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "NEXUS", body: event.data.text() };
  }

  const { title, body, url } = payload;

  event.waitUntil(
    self.registration.showNotification(title || "NEXUS", {
      body: body || "",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});

