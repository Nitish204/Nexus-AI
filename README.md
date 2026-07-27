# NEXUS — Autonomous AI Developer Workspace

A floating 3D workspace where five AI agents (Product Manager, Backend
Engineer, Frontend Engineer, QA Engineer, DevOps Engineer) collaborate
like a software team to build real, runnable code from a single request.

## What's implemented right now (Phase 0-1, core of 2 & 6)

- **FastAPI backend** (`backend/app`) — full REST API, WebSocket streaming
- **5 working agents** (`backend/app/agents`) — each a subclass of `AgentBase`,
  streaming Claude responses live and writing structured output to Postgres
- **Orchestrator** (`backend/app/services/orchestrator.py`) — decomposes a
  request via the PM agent, then runs engineer agents in dependency order,
  running independent tasks concurrently
- **Shared blackboard DB model** (`backend/app/db/models.py`) — Project,
  Task, AgentMessage, GeneratedFile, GraphEdge, AnalysisResult, Deployment
- **Live event bus + WebSocket gateway** — every agent action streams to
  the browser in real time
- **Static analysis service** (Phase 6) — radon/bandit/ruff wired up
- **3D workspace shell** (`frontend/src/scenes`) — R3F scene with 5 agent
  nodes that pulse/glow when their agent is active, a floating Monaco code
  editor panel, and a command bar (ready for voice transcription to feed into)

## Running it locally

```bash
# 1. Backend
cd backend
cp .env.example .env   # fill in GROQ_API_KEY (get one free at console.groq.com)
pip install -r requirements.txt
# start postgres + redis (see infra/docker-compose.yml), then:
uvicorn app.main:app --reload

# 2. Frontend
cd frontend
npm install
npm run dev
```

Create a project:
```bash
curl -X POST localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "auth-demo"}'
```

Open `http://localhost:5173/?project=<returned_id>`, type a request like
*"Build a Django authentication system with JWT and PostgreSQL"* into the
command bar, and watch the agent nodes light up as they work.

## Roadmap — what's next per phase

| Phase | Status | What it adds |
|---|---|---|
| 0-1 | ✅ done | Foundations, single-agent generation |
| 2 | ✅ done | Multi-agent orchestration |
| 3 | ✅ done | Docker sandbox execution (`app/sandbox/runner.py`) — runs generated Python + QA tests in an isolated, no-network container; on failure the orchestrator feeds the error back to the same agent and retries (`MAX_FIX_ATTEMPTS`), only marking a task FAILED after retries are exhausted |
| 4 | ✅ done | Knowledge graph (`app/services/graph.py`) — AST-parses Python files and regex-parses JS for imports/API routes/table references, stored as `GraphEdge` rows, rebuilt automatically after every task. Exposed at `GET /api/projects/{id}/graph` as `{nodes, links}`, ready for `react-force-graph` or a custom R3F layout |
| 5 | ✅ done | Deployment service (`app/services/deployment.py`) — materializes the virtual file tree, builds via the DevOps agent's Dockerfile. `LocalDockerProvider` works out of the box; `RenderProvider` needs `RENDER_API_KEY` in `.env` for real cloud deploys. Triggered via `POST /api/projects/{id}/deploy`, status streams over WebSocket |
| 6 | ✅ done | Analytics — backend (radon/bandit/ruff) plus a live frontend panel (`AnalyticsPanel.jsx`) showing complexity/security scores and the deploy button |
| 7 | ✅ done | Voice — `useVoiceCommand.js` wraps the browser's native SpeechRecognition API (no external service/key needed), transcribed text hits the same `/command` endpoint typed commands use. Mic button appears automatically in browsers that support it (Chrome/Edge) |
| 8 | 🔄 ongoing | 3D shell — current version renders agent nodes, code panel, analytics panel, voice input. Still open: rendering the Phase-4 graph data as literal 3D nodes/links, and agent-to-agent connection beams during handoffs |

### Notes on Phase 3-5 tradeoffs
- **Sandbox** only gates Python output (`BACKEND_ENGINEER`, `QA_ENGINEER` roles). A JS test runner (Jest in a Node container) is the natural next step using the same `SandboxResult` contract.
- **Deployment**'s `RenderProvider` call shape matches Render's documented service-create endpoint, but Render's real flow is git-based — treat it as a scaffold to adapt once you've connected a repo, not a drop-in production deployer. `LocalDockerProvider` is fully functional today if you just want to prove the "one-click deploy" loop locally.
- Both new services reuse the existing `event_bus`, so no frontend changes were needed beyond one new hook (`useNexusProject.js` now also tracks `deploymentStatus` and `sandboxResults`).

## Design language

Each agent has a fixed, distinct color identity (orange PM, cyan backend,
violet frontend, green QA, yellow DevOps) used consistently across the 3D
nodes, activity feed, and (planned) analytics charts — this is NEXUS's
visual signature, not a generic dashboard palette.
