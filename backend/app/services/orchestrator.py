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

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agents.backend_engineer import BackendEngineerAgent
from app.agents.devops_engineer import DevOpsEngineerAgent
from app.agents.frontend_engineer import FrontendEngineerAgent
from app.agents.product_manager import ProductManagerAgent
from app.agents.qa_engineer import QAEngineerAgent
from app.core.events import event_bus
from app.db.models import AgentRole, GeneratedFile, Task, TaskStatus
from app.sandbox.runner import sandbox_runner
from app.services.graph import rebuild_graph_for_project

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


class Orchestrator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def kick_off(self, project_id: str, request_text: str) -> None:
        """Entry point: user (or voice command) submits a feature request."""
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

    async def run_until_settled(self, project_id: str) -> None:
        for _ in range(MAX_ITERATIONS):
            runnable = await self._next_runnable_tasks(project_id)
            if not runnable:
                break

            # run this wave of unblocked tasks concurrently — this is
            # what lets e.g. QA and DevOps agents work "at the same time"
            # once their dependencies clear, visually shown as multiple
            # agents active simultaneously in the 3D workspace.
            await asyncio.gather(*[self._run_task(t) for t in runnable])

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

    async def _run_task(self, task: Task) -> None:
        agent_cls = AGENT_REGISTRY[task.assigned_role]

        attempt = 0
        while True:
            agent = agent_cls(self.session)
            updated = await agent.run(task)

            if updated.status != TaskStatus.IN_REVIEW:
                # agent itself failed (e.g. bad JSON, API error) — nothing to gate
                break

            if task.assigned_role not in SANDBOX_GATED_ROLES:
                updated.status = TaskStatus.DONE
                self.session.add(updated)
                await self.session.commit()
                break

            # Phase 3: gate completion on real execution, not just the
            # agent's own claim that it's done.
            result = await self._run_sandbox_gate(task)
            await event_bus.publish(
                task.project_id,
                "sandbox_result",
                {"task_id": task.id, "success": result.success, "stdout": result.stdout[-2000:], "error": result.error},
            )

            if result.success:
                updated.status = TaskStatus.DONE
                self.session.add(updated)
                await self.session.commit()
                break

            attempt += 1
            if attempt > MAX_FIX_ATTEMPTS:
                updated.status = TaskStatus.FAILED
                updated.result_summary = f"Sandbox execution failed after {MAX_FIX_ATTEMPTS} fix attempts."
                self.session.add(updated)
                await self.session.commit()
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
            self.session.add(task)
            await self.session.commit()

        # Knowledge graph (Phase 4) stays in sync with whatever files
        # exist after this task settles, success or failure.
        await rebuild_graph_for_project(self.session, task.project_id)

    async def _run_sandbox_gate(self, task: Task):
        result_files = await self.session.exec(
            select(GeneratedFile).where(GeneratedFile.project_id == task.project_id)
        )
        return await sandbox_runner.run_python_tests(result_files.all())
