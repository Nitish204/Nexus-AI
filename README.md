<div align="center">

# NEXUS

**Autonomous multi-agent software engineering, orchestrated.**

A single prompt in. A production-ready application out — planned, built, tested, analyzed, and deployed by a coordinated team of AI agents.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![React Native](https://img.shields.io/badge/PWA-Installable-5A0FC8?logo=pwa&logoColor=white)](docs/adr/0001-pwa-not-native-mobile.md)
[![Docker](https://img.shields.io/badge/Docker-Sandboxed-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-Ready-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

[Overview](#overview) · [Architecture](#architecture) · [Agent Team](#agent-team) · [Security](#security-model) · [Quick Start](#quick-start) · [Roadmap](#roadmap)

</div>

---

## Overview

Most AI coding tools are a single model doing everything — planning, writing, testing, and shipping in one undifferentiated pass. **NEXUS takes a different approach.**

It coordinates a team of specialized AI agents — a Product Manager, Backend Engineer, Frontend Engineer, QA Engineer, and DevOps Engineer — that plan, build, validate, and ship software the way a real engineering team does: in parallel, through shared context, with checks at every stage.

Every task, message, file, and decision flows through a shared blackboard memory, and the entire process streams live over WebSockets into an interactive 3D workspace — so instead of staring at a spinner, you *watch your software get built*.

```
"Build a Django authentication system using JWT and PostgreSQL."
```

That's the input. NEXUS handles decomposition, implementation, static analysis, sandboxed testing, and deployment prep — autonomously, on your infrastructure of choice (Docker, Render, or Kubernetes) and with your choice of LLM (cloud via Groq, or fully local).

---

## Why NEXUS

| | |
|---|---|
| 🧠 **Real division of labor** | Specialized agents instead of one model wearing every hat |
| 🔄 **Parallel, not sequential** | Independent agents work concurrently on backend, frontend, and QA |
| 🗂️ **Shared memory, not lost context** | A blackboard architecture keeps every agent aligned on project state |
| 🧪 **Trust but verify** | Generated code runs in an isolated, hardened Docker sandbox before it ships |
| 📊 **Quality, measured** | Ruff, Bandit, and Radon score every artifact for style, security, and complexity |
| 👁️ **Full transparency** | Live WebSocket streaming into a 3D visualization — nothing happens in a black box |
| 🔒 **Cookie-based sessions, not tokens in local storage** | Session auth never touches JS-reachable storage on the web app, closing the most common XSS-to-account-takeover path |
| 🖥️ **Bring your own LLM** | Point every agent at a local OpenAI-compatible server (Ollama, LM Studio, vLLM) instead of the cloud — no API key, nothing leaves the machine |
| 📱 **On the go** | Installable as a PWA (Add to Home Screen) with Web Push, so you can get notified when a build finishes or fails without a native app — see [ADR 0001](docs/adr/0001-pwa-not-native-mobile.md) for why |

---

## Architecture

```
                         User Prompt
                              │
                              ▼
                   ┌─────────────────────┐
                   │  Product Manager    │
                   │  Agent               │
                   │  (task decomposition)│
                   └──────────┬──────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      ┌───────────────┐ ┌───────────┐ ┌───────────────┐
      │ Backend Agent  │ │ Frontend  │ │   QA Agent     │
      │ APIs · Auth ·  │ │  Agent    │ │  Validation ·  │
      │ DB · Logic     │ │  UI · UX  │ │  Test coverage │
      └───────┬────────┘ └─────┬─────┘ └───────┬────────┘
              │                │                │
              └────────────────┼────────────────┘
                                ▼
                   ┌─────────────────────┐
                   │   Shared Blackboard  │
                   │  (projects · tasks · │
                   │  files · knowledge)  │
                   └──────────┬──────────┘
                                ▼
                   ┌─────────────────────┐
                   │   DevOps Agent        │
                   │  Docker · Sandbox ·   │
                   │  Local / Render / K8s │
                   └──────────┬──────────┘
                                ▼
                     Production Application
```

Agents don't just execute in sequence — they read and write to a shared knowledge graph, so a decision the Backend Agent makes about a data model is immediately visible to the Frontend and QA agents building against it.

**Web ↔ backend traffic is proxied same-origin in production** (via a `vercel.json`-style rewrite from the frontend host to the backend), so the session cookie is genuinely first-party rather than fighting third-party cookie blocking in Safari/Chrome. The WebSocket connects directly to the backend, authenticated by a short-lived, single-purpose token fetched just-in-time — it never depends on the session cookie riding along on the handshake.

---

## Agent Team

| Agent | Role | Responsibility |
|:-----:|------|-----------------|
| 🟧 | **Product Manager** | Interprets requirements, breaks the project into a coordinated task graph |
| 🔵 | **Backend Engineer** | Builds APIs, database schemas, authentication, and business logic |
| 🟣 | **Frontend Engineer** | Builds responsive UI and frontend architecture |
| 🟢 | **QA Engineer** | Validates generated code and runs automated tests |
| 🟡 | **DevOps Engineer** | Handles Docker sandboxing, CI/CD, and deployment (local, Render, or Kubernetes) |

Each agent operates independently but communicates constantly through shared project memory — enabling genuine parallel development instead of a sequential pipeline pretending to be one. An on-demand **AI code review** pass is also available per-file, outside the task pipeline, for a quick severity-scored second opinion on any generated file.

---

## Security Model

Session and platform security got a full pass, not just individual bug fixes — worth documenting explicitly rather than leaving as tribal knowledge:

- **Web sessions are httpOnly-cookie based**, not stored in `localStorage`. JavaScript — including any XSS bug elsewhere in the app — can never read the credential itself.
- **CSRF defense via the double-submit cookie pattern.** A second, JS-readable cookie is paired with the session cookie; every state-changing request must echo its value back as a header, which a cross-site attacker's page cannot do (it can't read another origin's cookies).
- **GitHub OAuth is `state`-protected end to end** — a random value is generated client-side, held in `sessionStorage`, and verified on return before any code exchange happens, closing a login-CSRF hole.
- **Rate limiting** on login, signup, and the security-question/password-reset flow — the last of these is the highest-value brute-force target in the system (a correct guess there is a full account takeover) and is limited accordingly.
- **The sandbox container runs hardened**: no network access, a memory ceiling, a `pids_limit` (fork-bomb protection), all Linux capabilities dropped, and `no-new-privileges` set.
- **The app refuses to boot in production** if `SECRET_KEY` or `JWT_SECRET` are still at their insecure default values — a misconfiguration that would otherwise let anyone forge a valid session token for any user.
- **Non-browser API clients use a Bearer token, not the session cookie**: any client without a shared cookie jar with a browser (a future native wrapper, a CLI, a script) authenticates via a Bearer token in the `Authorization` header instead — the same `get_current_user_id` dependency accepts both paths cleanly. See [ADR 0001](docs/adr/0001-pwa-not-native-mobile.md) for why NEXUS ships as an installable PWA rather than a separate native mobile app today.

Known, accepted limitation: `GET /api/auth/security-question` confirms whether an email is registered (necessary since there's no email-verification step in the reset flow) — rate-limited to blunt enumeration, not eliminated by design.

---

## Observability & Cost Tracking

- **Error tracking**: both the backend (`app/core/observability.py`) and frontend (`frontend/src/lib/sentry.js`) report unhandled exceptions to Sentry when `SENTRY_DSN` / `VITE_SENTRY_DSN` are set. Unset (the default) is a silent no-op — no code changes needed to run without it locally or in CI.
- **Uptime monitoring**: point an external monitor (UptimeRobot, Better Stack, Render/Kubernetes health checks) at `GET /health` for liveness ("is the process up") and `GET /health/ready` for readiness ("can it actually serve a request" — checks Postgres and Redis independently and reports which one is down).
- **LLM cost tracking**: every agent LLM call records its token usage and an estimated USD cost (`app/db/models.TokenUsage`, priced in `app/core/llm_pricing.py`). `GET /api/projects/{id}/analytics/cost` returns the running total and a per-agent-role breakdown; local-provider calls are always $0 (nothing metered leaves the machine), and a model missing from the pricing table is priced with a conservative fallback and flagged `is_estimated: true` rather than silently reported as free.

---

## Testing

```bash
# Backend — pytest against an in-memory SQLite DB, no external services needed
cd backend && python -m pytest

# Frontend — Vitest + React Testing Library
cd frontend && npm test
```

Backend coverage includes every agent's response-parsing (`tests/test_agents*.py`), the shared retry/streaming/cost-tracking machinery in `AgentBase.run()` (`tests/test_agent_run_lifecycle.py`, `tests/test_token_usage.py`), and the orchestrator's dependency resolution and sandbox fix-and-retry loop. Frontend coverage includes the CSRF/credentials logic in `utils/api.js`, push-notification state handling, and component rendering (`Sidebar`).

---

## Feature Highlights

<table>
<tr>
<td width="50%">

**🧠 Orchestration**
- Intelligent task decomposition
- Dependency-aware scheduling
- Concurrent multi-agent execution
- Shared blackboard memory + knowledge graph
- Bring-your-own local LLM (Ollama / LM Studio / vLLM) or Groq cloud

**📊 Code Quality**
- Static analysis via Ruff
- Security scanning via Bandit
- Complexity metrics via Radon
- On-demand AI code review per file

</td>
<td width="50%">

**🧪 Safety**
- Isolated, hardened Docker sandbox execution
- Automated retry on failure
- Structured error feedback loop
- Rate limiting, CSRF protection, hardened auth (see [Security Model](#security-model))

**🌐 Experience**
- Real-time WebSocket event streaming
- Interactive 3D workspace (React Three Fiber)
- Native voice command support + configurable voice greeting
- Live project analytics dashboard
- Mobile companion app (Expo / React Native)

**🚀 Deployment & Extensibility**
- Local Docker, Render, or Kubernetes — pick per environment
- One-click GitHub repo export for any generated project
- Plugin marketplace (integrations, extra agents, themes, templates)

</td>
</tr>
</table>

---

## Tech Stack

<table>
<tr>
<td valign="top" width="20%">

**Backend**
- FastAPI
- SQLModel / SQLAlchemy
- PostgreSQL
- Redis
- WebSockets

</td>
<td valign="top" width="20%">

**Frontend**
- React + Vite
- React Three Fiber
- Three.js
- Monaco Editor

</td>
<td valign="top" width="20%">

**Mobile**
- Installable PWA (`manifest.json` + service worker)
- Web Push (VAPID)
- Offline app-shell cache

</td>
<td valign="top" width="20%">

**AI**
- Groq (cloud) or any local OpenAI-compatible server
- Multi-agent orchestration
- Prompt engineering pipeline

</td>
<td valign="top" width="20%">

**Infrastructure**
- Docker
- Kubernetes
- Render
- Gunicorn

</td>
</tr>
</table>

---

## Quick Start

### 1 · Clone

```bash
git clone https://github.com/your-username/NEXUS.git
cd NEXUS
```

### 2 · Backend

```bash
cd backend
cp .env.example .env   # fill in secrets — see note below
pip install -r requirements.txt
uvicorn app.main:app --reload
```

> **Before deploying to production:** set real, random values for `SECRET_KEY` and `JWT_SECRET`, and set `ENVIRONMENT=production`. The latter switches the session cookie to `SameSite=None; Secure`, which is required once the frontend and backend live on different domains — without it, login will silently fail to persist. See [Security Model](#security-model) for the full list of what production deployment expects.

### 3 · Frontend

```bash
cd frontend
npm install
npm run dev
```

If frontend and backend are on different domains in production, add a same-origin rewrite (e.g. `vercel.json`) proxying `/api/*` to the backend — this keeps the session cookie first-party and avoids third-party cookie blocking in Safari/Chrome. See `frontend/vercel.json` for the Vercel example.

### 4 · Mobile / PWA (optional)

There's no separate mobile app or `mobile/` directory — NEXUS ships as
an installable Progressive Web App instead (see
[ADR 0001](docs/adr/0001-pwa-not-native-mobile.md)). Nothing extra to
build: open the deployed frontend on a phone and use the browser's
"Add to Home Screen" / install prompt. To receive push notifications
when a build finishes, generate VAPID keys and set them in the
backend's `.env`:

```bash
cd backend
python3 scripts/generate_vapid_keys.py
# copy the printed VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY into .env
```

Then tap "Enable notifications" in the app's sidebar once installed.

### 5 · Database

```bash
docker compose up
```

### 6 · Ship something

```bash
curl -X POST localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Authentication System"}'
```

Open `http://localhost:5173`, describe what you want to build, and watch the agents get to work.

---

## Project Structure

```
NEXUS
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes (auth, projects, plugins, github export, code review, deploy)
│   │   ├── agents/         # Agent definitions & orchestration logic
│   │   ├── core/           # Config, security (JWT/cookies), rate limiting
│   │   ├── db/              # SQLModel models & migrations
│   │   ├── services/        # Deployment providers, code review, GitHub export
│   │   └── sandbox/          # Hardened Docker sandbox execution
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── scenes/          # React Three Fiber scenes (the 3D workspace)
│   │   ├── pages/            # AuthPage, etc.
│   │   ├── hooks/             # useNexusProject (WebSocket + API), useVoiceCommand
│   │   ├── components/        # Sidebar, AnalyticsPanel
│   │   ├── lib/                 # Sentry init
│   │   ├── test/                 # Vitest setup
│   │   └── utils/              # Shared cookie-aware API client, push notifications
│   ├── public/
│   │   ├── manifest.json         # PWA manifest
│   │   └── sw.js                  # Service worker: offline app-shell cache + Web Push
│   └── vercel.json              # Same-origin proxy config (production)
│
├── docs/
│   └── adr/                # Architecture decision records (e.g. PWA vs. native mobile)
│
├── infra/
│   ├── docker-compose.yml
│   └── k8s/                # Kubernetes manifests
│
└── README.md
```

---

## Roadmap

| Milestone | Status |
|---|:---:|
| Core orchestration foundation | ✅ |
| Multi-agent collaboration | ✅ |
| Docker sandbox execution (hardened: no network, pids limit, dropped capabilities) | ✅ |
| Shared knowledge graph | ✅ |
| Deployment engine — local Docker | ✅ |
| Static code analysis | ✅ |
| Voice commands + configurable voice greeting | ✅ |
| Interactive 3D visualization | ✅ |
| Cookie-based sessions + CSRF protection | ✅ |
| Rate limiting on auth endpoints | ✅ |
| Local LLM support (Ollama / LM Studio / vLLM) | ✅ |
| GitHub repo generation (one-click export) | ✅ |
| AI-assisted code review (on-demand, per-file) | ✅ |
| Plugin marketplace (integrations, agents, themes, templates) | ✅ |
| Kubernetes deployment | ✅ |
| Installable PWA with offline app-shell + Web Push ([ADR 0001](docs/adr/0001-pwa-not-native-mobile.md)) | ✅ |
| GitHub OAuth `state` (CSRF) protection | ✅ |
| Same-origin proxying for cross-domain cookie reliability | ✅ |
| Error tracking (Sentry) on backend + frontend, `/health` + `/health/ready` for uptime monitoring | ✅ |
| Per-project LLM cost tracking (token usage + USD estimate, by agent role) | ✅ |
| Automated test coverage for every agent's response-parsing + retry logic, and the frontend's API/utility layer | ✅ |
| Set-a-password flow for OAuth-only accounts (so a non-browser client can log in without re-registering) | ⬜ |
| Redis-backed rate limiting (for multi-replica deployments) | ⬜ |
| Public, API-key-authenticated read endpoints (separate from the cookie-based web session) | ⬜ |
| Code-split the frontend bundle (currently a single >1MB chunk) | ⬜ |
| Plugin marketplace: real third-party plugin submission/review flow | ⬜ |
| Native mobile app (Capacitor wrapping the existing frontend) — only if the PWA's limits in ADR 0001 become a real constraint | ⬜ |

---

## Contributing

Contributions are genuinely welcome — this is early-stage and there's a lot of room to shape it.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-idea`)
3. Commit your changes
4. Push and open a Pull Request

---

## License

Released under the [MIT License](LICENSE).

---

<div align="center">

**If NEXUS is useful to you, a ⭐ helps others find it.**

Built by **Vishwakarma Nitish**

</div>
