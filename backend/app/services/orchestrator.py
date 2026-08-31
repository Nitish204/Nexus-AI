"""
NEXUS — Orchestrator.
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
from app.services.push_notifications import send_push_to_project_owner
from app.services.graph import rebuild_graph_for_project

logger = logging.getLogger("nexus.orchestrator")

AGENT_REGISTRY = {
    AgentRole.PRODUCT_MANAGER: ProductManagerAgent,
    AgentRole.BACKEND_ENGINEER: BackendEngineerAgent,
    AgentRole.FRONTEND_ENGINEER: FrontendEngineerAgent,
    AgentRole.QA_ENGINEER: QAEngineerAgent,
    AgentRole.DEVOPS_ENGINEER: DevOpsEngineerAgent,
}

SANDBOX_GATED_ROLES = {AgentRole.BACKEND_ENGINEER, AgentRole.QA_ENGINEER}

MAX_ITERATIONS = 20
MAX_FIX_ATTEMPTS = 2
DELAY_BETWEEN_TASKS_SECONDS = 4


class Orchestrator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def kick_off(self, project_id: str, request_text: str) -> None:
        logger.info("kick_off starting for project=%s: %r", project_id, request_text[:200])
        try:
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

            for t in runnable:
                await self._run_task(t.id, project_id)
                await asyncio.sleep(DELAY_BETWEEN_TASKS_SECONDS)

        await event_bus.publish(project_id, "orchestration_complete", {"project_id": project_id})

        async with get_session_context() as session:
            project = await session.get(Project, project_id)
            all_tasks = (
                await session.exec(select(Task).where(Task.project_id == project_id))
            ).all()
            failed = [t for t in all_tasks if t.status == TaskStatus.FAILED]
            project_name = project.name if project else "Your project"
            if failed:
                await send_push_to_project_owner(
                    session, project_id,
                    title=f"{project_name}: build finished with errors",
                    body=f"{len(failed)} of {len(all_tasks)} tasks failed — open NEXUS to see what happened.",
                    url=f"/?project={project_id}",
                )
            else:
                await send_push_to_project_owner(
                    session, project_id,
                    title=f"{project_name}: build complete",
                    body=f"All {len(all_tasks)} tasks finished successfully.",
                    url=f"/?project={project_id}",
                )

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
                    break

                if task.assigned_role not in SANDBOX_GATED_ROLES:
                    updated.status = TaskStatus.DONE
                    session.add(updated)
                    await session.commit()
                    break

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

                failure_context = (result.error or result.stdout)[-1500:]
                task.description += (
                    f"\n\n--- PREVIOUS ATTEMPT FAILED (attempt {attempt}) ---\n"
                    f"Fix the following error and regenerate the file(s):\n{failure_context}"
                )
                task.status = TaskStatus.PENDING
                session.add(task)
                await session.commit()

            await rebuild_graph_for_project(session, project_id)

    async def _run_sandbox_gate(self, session: AsyncSession, project_id: str):
        result_files = await session.exec(
            select(GeneratedFile).where(GeneratedFile.project_id == project_id)
        )
        return await sandbox_runner.run_python_tests(result_files.all())
