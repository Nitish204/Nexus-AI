# ADR 0001: Ship NEXUS on mobile as an installable PWA, not a native app

Status: Accepted
Date: 2026-09-22

## Context

NEXUS needs to be usable on a phone: at minimum, checking on a running
build and getting notified when it finishes or fails (see
`app/services/push_notifications.py`, `frontend/src/utils/push.js`).
The question is whether that means a real native iOS/Android app (React
Native, Capacitor, Swift/Kotlin, ...) or a web app installed as a PWA.

## Decision

PWA. `frontend/public/manifest.json` + `frontend/public/sw.js` already
make NEXUS installable (`display: "standalone"`, home-screen icon,
theme color) and able to receive Web Push (`app/api/push.py`,
`pywebpush` on the backend). This ADR keeps it that way rather than
adding a native/Capacitor build target, and documents the specific
gaps so they're a known trade-off rather than an oversight.

## Why

- **NEXUS's core product is inherently online and desktop-shaped.**
  The actual work — an LLM agent streaming generated code over a
  WebSocket into a Monaco editor (`@monaco-editor/react`), running
  sandboxed builds, browsing a multi-file project — needs a live
  backend connection and a reasonably large screen to be useful at
  all. There's no offline "core loop" to preserve the way there is for
  a notes app or a game, which is exactly the situation a PWA is
  suited to and a native rewrite would mostly not improve.
- **The realistic mobile use case is narrow: monitor + get notified.**
  Checking whether a build finished, reading agent messages, tapping a
  push notification to jump back in — all of this is well within what
  a PWA does today. It does not need native-only capabilities like
  background audio, deep OS integration, or offline-first data sync.
- **One codebase, one deploy pipeline.** NEXUS already ships as a
  single React/Vite frontend (`frontend/`) deployed to Vercel/Cloudflare
  Pages and a single FastAPI backend. A native app would mean a second
  UI codebase (or a Capacitor wrapper with its own build/signing/store
  pipeline) to keep in sync with every change to the agent workflow —
  a real, ongoing cost for a product this early.
- **Web Push already covers the notification requirement** on Android
  and, as of recent iOS/Safari versions, on an installed (home-screen)
  PWA on iOS too — the actual gap that used to force native apps into
  existence for "just send me a push when it's done" no longer applies
  here.

## What this explicitly gives up (revisit if these become real needs)

- **No offline editing/authoring.** `sw.js` caches the app shell
  (HTML/CSS/JS/icons) so an installed NEXUS opens to a real screen
  instead of a blank tab when briefly offline, and falls back
  gracefully — but it does not cache `/api/*` responses or generated
  project files, and it never will under this decision: showing
  possibly-stale generated code as if it were current, or queuing
  "commands" to an LLM agent for later replay, would be actively
  misleading rather than a convenience.
- **No background execution.** An agent run only progresses while a
  tab/PWA window is open (or, once push fires, while the backend's own
  orchestrator loop is running server-side — see
  `app/services/orchestrator.py`, which runs independently of any
  client being connected at all). There's no on-device background task
  keeping something alive.
- **No app-store presence.** Some users specifically look for a tool
  in the App/Play Store before trying it — a PWA is invisible there.
  Revisit if organic/store discovery becomes a meaningful acquisition
  channel.
- **iOS PWA install friction.** iOS still requires the "Add to Home
  Screen" flow rather than a store install, which is a real, measurable
  drop-off point compared to a store listing.

## Revisit this decision if

- The product grows a genuine offline or background-processing need
  (not just "would be nice") — e.g. on-device inference, background
  sync of large generated projects.
- App-store discoverability becomes a primary growth channel.
- A capability PWAs fundamentally can't reach (e.g. certain
  background execution modes, deeper filesystem access for exporting
  large projects) becomes a hard product requirement.

At that point, Capacitor wrapping the existing frontend is the
lower-cost next step before a full native rewrite, since it reuses
this same React codebase.
