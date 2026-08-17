<div align="center">

# NEXUS

**Autonomous multi-agent software engineering, orchestrated.**

A single prompt in. A production-ready application out — planned, built, tested, analyzed, and deployed by a coordinated team of AI agents.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Sandboxed-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

[Overview](#overview) · [Architecture](#architecture) · [Agent Team](#agent-team) · [Quick Start](#quick-start) · [Roadmap](#roadmap)

</div>

---

## Overview

Most AI coding tools are a single model doing everything — planning, writing, testing, and shipping in one undifferentiated pass. **NEXUS takes a different approach.**

It coordinates a team of specialized AI agents — a Product Manager, Backend Engineer, Frontend Engineer, QA Engineer, and DevOps Engineer — that plan, build, validate, and ship software the way a real engineering team does: in parallel, through shared context, with checks at every stage.

Every task, message, file, and decision flows through a shared blackboard memory, and the entire process streams live over WebSockets into an interactive 3D workspace — so instead of staring at a spinner, you *watch your software get built*.

```
"Build a Django authentication system using JWT and PostgreSQL."
```

That's the input. NEXUS handles decomposition, implementation, static analysis, sandboxed testing, and deployment prep — autonomously.

---

## Why NEXUS

| | |
|---|---|
| 🧠 **Real division of labor** | Specialized agents instead of one model wearing every hat |
| 🔄 **Parallel, not sequential** | Independent agents work concurrently on backend, frontend, and QA |
| 🗂️ **Shared memory, not lost context** | A blackboard architecture keeps every agent aligned on project state |
| 🧪 **Trust but verify** | Generated code runs in an isolated Docker sandbox before it ships |
| 📊 **Quality, measured** | Ruff, Bandit, and Radon score every artifact for style, security, and complexity |
| 👁️ **Full transparency** | Live WebSocket streaming into a 3D visualization — nothing happens in a black box |

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
                   │  Deployment           │
                   └──────────┬──────────┘
                                ▼
                     Production Application
```

Agents don't just execute in sequence — they read and write to a shared knowledge graph, so a decision the Backend Agent makes about a data model is immediately visible to the Frontend and QA agents building against it.

---

## Agent Team

| Agent | Role | Responsibility |
|:-----:|------|-----------------|
| 🟧 | **Product Manager** | Interprets requirements, breaks the project into a coordinated task graph |
| 🔵 | **Backend Engineer** | Builds APIs, database schemas, authentication, and business logic |
| 🟣 | **Frontend Engineer** | Builds responsive UI and frontend architecture |
| 🟢 | **QA Engineer** | Validates generated code and runs automated tests |
| 🟡 | **DevOps Engineer** | Handles Docker sandboxing, CI/CD, and deployment |

Each agent operates independently but communicates constantly through shared project memory — enabling genuine parallel development instead of a sequential pipeline pretending to be one.

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

**📊 Code Quality**
- Static analysis via Ruff
- Security scanning via Bandit
- Complexity metrics via Radon

</td>
<td width="50%">

**🧪 Safety**
- Isolated Docker sandbox execution
- Automated retry on failure
- Structured error feedback loop

**🌐 Experience**
- Real-time WebSocket event streaming
- Interactive 3D workspace (React Three Fiber)
- Native voice command support
- Live project analytics dashboard

</td>
</tr>
</table>

---

## Tech Stack

<table>
<tr>
<td valign="top" width="25%">

**Backend**
- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis
- WebSockets

</td>
<td valign="top" width="25%">

**Frontend**
- React + Vite
- React Three Fiber
- Three.js
- Monaco Editor

</td>
<td valign="top" width="25%">

**AI**
- Claude API
- Multi-agent orchestration
- Prompt engineering pipeline

</td>
<td valign="top" width="25%">

**Infrastructure**
- Docker
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
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 3 · Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4 · Database

```bash
docker compose up
```

### 5 · Ship something

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
│   ├── app/          # FastAPI application
│   ├── agents/        # Agent definitions & orchestration logic
│   ├── db/            # SQLAlchemy models & migrations
│   ├── services/       # Shared business logic
│   └── sandbox/        # Docker sandbox execution
│
├── frontend/
│   ├── src/
│   ├── scenes/         # React Three Fiber scenes
│   ├── hooks/
│   └── components/
│
├── infra/               # Deployment & infrastructure configs
└── README.md
```

---

## Roadmap

| Milestone | Status |
|---|:---:|
| Core orchestration foundation | ✅ |
| Multi-agent collaboration | ✅ |
| Docker sandbox execution | ✅ |
| Shared knowledge graph | ✅ |
| Deployment engine | ✅ |
| Static code analysis | ✅ |
| Voice commands | ✅ |
| Interactive 3D visualization | 🚧 |
| Local LLM support | ⬜ |
| GitHub repo generation | ⬜ |
| AI-assisted code review | ⬜ |
| Plugin marketplace | ⬜ |
| Kubernetes deployment | ⬜ |
| Mobile companion app | ⬜ |

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
