"""
NEXUS — Orchestrator.

This is the "team lead" that turns a raw request into finished work:

1. Runs the PM agent to decompose the request into Task rows.
2. Repeatedly scans for tasks whose dependencies are all DONE and whose
   own status is PENDING, and runs the matching engineer agent on them.
3. Stops when every task is DONE or FAILED, or a safety iteration cap
   is hit (guards against a dependency cycle spinning forever).

Deliberately simple (poll-based, not a full DAG scheduler) so it's easy
to reason about and debug in early phases. Swappable later for
langgraph or a Celery-based scheduler without touching agent code.
"""
import asyncio
import logging

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.backend_engineer import BackendEngineerAgent
from app.agents.devops_engineer import DevOpsEngineerAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.product_manager import ProductManagerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.core.events import event_bus
from app.db.models import AgentRole, GeneratedFile, Project, Task, TaskStatus
from app.db.session import get_session_context
from app.sandbox.runner import sandbox_runner
from app.services.graph import rebuild_graph_for_project

logger = logging.getLogger("nexus.orchestrator")

AGENT_REGISTRY = {
    AgentRole.PRODUCT_MANAGER: ProductManagerAgent,
    AgentRole.BACKEND_ENGINEER: BackendEngineerAgent,
    AgentRole.FRONTEND_ENGINEER: FrontendEngineerAgent,
    AgentRole.QA_ENGINEER: QAEngineerAgent,
    AgentRole.DEVOPS_ENGINEER: DevOpsEngineerAgent,
}

# Roles whose output is Python and therefore sandbox-testable. Frontend/
# DevOps artifacts (JS, Dockerfiles) skip execution gating for now —
# Phase 3 only covers the Python path; a JS test runner is a natural
# follow-up using the same SandboxResult contract.
SANDBOX_GATED_ROLES = {AgentRole.BACKEND_ENGINEER, AgentRole.QA_ENGINEER}

MAX_ITERATIONS = 20
MAX_FIX_ATTEMPTS = 2  # self-correction retries before giving up and marking FAILED

# Small pause between one agent finishing and the next one starting.
# Groq's free tier caps total token usage per minute across ALL agent
# calls combined — running agents back-to-back with zero gap clusters
# spending right at the start of each per-minute window and makes
# hitting that ceiling more likely. Spacing calls out lets the budget
# recover between them instead.
DELAY_BETWEEN_TASKS_SECONDS = 4


class Orchestrator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def kick_off(self, project_id: str, request_text: str) -> None:
        """Entry point: user (or voice command) submits a feature request."""
        logger.info("kick_off starting for project=%s: %r", project_id, request_text[:200])
        try:
            # Rename the project from its first real request instead of
            # leaving it as a generic default placeholder — this is
            # what the sidebar's history list actually displays. Only
            # does this while name_is_default is still True, so a name
            # the user set manually (even before their first command)
            # is never silently overwritten.
            project = await self.session.get(Project, project_id)
            if project and project.name_is_default:
                project.name = request_text[:60] + ("..." if len(request_text) > 60 else "")
                project.name_is_default = False
                self.session.add(project)
                await self.session.commit()

            pm_task = Task(
                project_id=project_id,
                title="Decompose feature request",
                description=request_text,
                assigned_role=AgentRole.PRODUCT_MANAGER,
                status=TaskStatus.PENDING,
            )
            self.session.add(pm_task)
            await self.session.commit()
            await self.session.refresh(pm_task)

            pm_agent = ProductManagerAgent(self.session)
            await pm_agent.run(pm_task)

            await self.run_until_settled(project_id)
            logger.info("kick_off finished for project=%s", project_id)

        except Exception as exc:  # noqa: BLE001
            # Last-resort safety net: this is the outermost boundary of
            # the whole background task. Anything that escapes here
            # previously vanished completely — no log, no DB update, no
            # event — because FastAPI's BackgroundTasks doesn't surface
            # exceptions anywhere visible on its own.
            logger.error("kick_off CRASHED for project=%s: %s", project_id, exc, exc_info=True)
            await event_bus.publish(
                project_id, "orchestration_error", {"project_id": project_id, "error": str(exc)}
            )

    async def run_until_settled(self, project_id: str) -> None:
        for iteration in range(MAX_ITERATIONS):
            runnable = await self._next_runnable_tasks(project_id)
            logger.info(
                "run_until_settled project=%s iteration=%d runnable=%s",
                project_id, iteration, [(t.id, t.assigned_role.value) for t in runnable],
            )
            if not runnable:
                logger.info("run_until_settled project=%s: no more runnable tasks, stopping", project_id)
                break

            # Run this wave of unblocked tasks ONE AT A TIME, with a
            # short pause between each — agents "take turns" rather than
            # all hitting Groq's API at once. This trades a bit of
            # wall-clock speed for staying comfortably under the
            # free-tier per-minute token budget shared across every
            # agent call, which is what was causing frequent 429s when
            # e.g. Backend and DevOps both became runnable together and
            # fired simultaneously.
            #
            # Each task still gets its own database session (see
            # _run_task) — that fix from the concurrent-session bug
            # stays in place regardless of whether tasks run one at a
            # time or in parallel.
            for t in runnable:
                await self._run_task(t.id, project_id)
                # Brief pause before the next agent's turn. Worst case
                # this adds one small unnecessary pause right at the
                # very end of a run (we don't know a task is the last
                # one until the *next* iteration comes back empty) —
                # harmless, a few seconds of idle time, not worth the
                # extra complexity to avoid.
                await asyncio.sleep(DELAY_BETWEEN_TASKS_SECONDS)

        await event_bus.publish(project_id, "orchestration_complete", {"project_id": project_id})

    async def _next_runnable_tasks(self, project_id: str) -> list[Task]:
        result = await self.session.exec(
            select(Task).where(Task.project_id == project_id, Task.status == TaskStatus.PENDING)
        )
        pending = result.all()

        done_result = await self.session.exec(
            select(Task.id).where(Task.project_id == project_id, Task.status == TaskStatus.DONE)
        )
        done_ids = set(done_result.all())

        return [t for t in pending if all(dep in done_ids for dep in t.depends_on)]

    async def _run_task(self, task_id: str, project_id: str) -> None:
        # Own session for this task's lifetime. Tasks now run
        # sequentially (see run_until_settled), but this pattern is kept
        # regardless — it's what made concurrent execution safe before,
        # and costs nothing running sequentially either.
        async with get_session_context() as session:
            task = await session.get(Task, task_id)
            if task is None:
                logger.error("_run_task: task_id=%s not found (project=%s)", task_id, project_id)
                return

            agent_cls = AGENT_REGISTRY[task.assigned_role]

            attempt = 0
            while True:
                agent = agent_cls(session)
                updated = await agent.run(task)

                if updated.status != TaskStatus.IN_REVIEW:
                    # agent itself failed (e.g. bad JSON, API error) — nothing to gate
                    break

                if task.assigned_role not in SANDBOX_GATED_ROLES:
                    updated.status = TaskStatus.DONE
                    session.add(updated)
                    await session.commit()
                    break

                # Phase 3: gate completion on real execution, not just the
                # agent's own claim that it's done.
                result = await self._run_sandbox_gate(session, project_id)
                await event_bus.publish(
                    project_id,
                    "sandbox_result",
                    {"task_id": task.id, "success": result.success, "stdout": result.stdout[-2000:], "error": result.error},
                )

                if result.success:
                    updated.status = TaskStatus.DONE
                    session.add(updated)
                    await session.commit()
                    break

                attempt += 1
                if attempt > MAX_FIX_ATTEMPTS:
                    updated.status = TaskStatus.FAILED
                    updated.result_summary = f"Sandbox execution failed after {MAX_FIX_ATTEMPTS} fix attempts."
                    session.add(updated)
                    await session.commit()
                    break

                # feed the failure back to the same agent as extra task
                # description context and retry — this is the "fix and
                # retest" loop.
                failure_context = (result.error or result.stdout)[-1500:]
                task.description += (
                    f"\n\n--- PREVIOUS ATTEMPT FAILED (attempt {attempt}) ---\n"
                    f"Fix the following error and regenerate the file(s):\n{failure_context}"
                )
                task.status = TaskStatus.PENDING
                session.add(task)
                await session.commit()

            # Knowledge graph (Phase 4) stays in sync with whatever files
            # exist after this task settles, success or failure.
            await rebuild_graph_for_project(session, project_id)

    async def _run_sandbox_gate(self, session: AsyncSession, project_id: str):
        result_files = await session.exec(
            select(GeneratedFile).where(GeneratedFile.project_id == project_id)
        )
        return await sandbox_runner.run_python_tests(result_files.all())
