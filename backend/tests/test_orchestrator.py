"""
Tests for Orchestrator._next_runnable_tasks — the dependency scheduler.

This is the piece where a bug is easiest to introduce silently (e.g.
comparing to the wrong status, or an off-by-one in dependency checks)
and hardest to notice without a real multi-agent run, so it gets direct
unit coverage rather than relying on end-to-end tests alone.
"""
import pytest

from app.db.models import AgentRole, Task, TaskStatus
from app.services.orchestrator import Orchestrator


async def _make_task(session, project, **kwargs):
    defaults = dict(
        project_id=project.id,
        title="task",
        description="do something",
        assigned_role=AgentRole.BACKEND_ENGINEER,
        status=TaskStatus.PENDING,
    )
    defaults.update(kwargs)
    task = Task(**defaults)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@pytest.mark.asyncio
async def test_task_with_no_dependencies_is_runnable(session, project):
    task = await _make_task(session, project)
    orch = Orchestrator(session)

    runnable = await orch._next_runnable_tasks(project.id)

    assert [t.id for t in runnable] == [task.id]


@pytest.mark.asyncio
async def test_task_blocked_on_incomplete_dependency_is_not_runnable(session, project):
    blocker = await _make_task(session, project, status=TaskStatus.PENDING)
    dependent = await _make_task(session, project, depends_on=[blocker.id])

    orch = Orchestrator(session)
    runnable = await orch._next_runnable_tasks(project.id)

    # only the blocker itself should be runnable; the dependent task
    # must wait until the blocker is DONE
    assert [t.id for t in runnable] == [blocker.id]


@pytest.mark.asyncio
async def test_task_becomes_runnable_once_dependency_is_done(session, project):
    blocker = await _make_task(session, project, status=TaskStatus.DONE)
    dependent = await _make_task(session, project, depends_on=[blocker.id])

    orch = Orchestrator(session)
    runnable = await orch._next_runnable_tasks(project.id)

    assert [t.id for t in runnable] == [dependent.id]


@pytest.mark.asyncio
async def test_non_pending_tasks_are_never_returned_as_runnable(session, project):
    await _make_task(session, project, status=TaskStatus.IN_PROGRESS)
    await _make_task(session, project, status=TaskStatus.DONE)
    await _make_task(session, project, status=TaskStatus.FAILED)

    orch = Orchestrator(session)
    runnable = await orch._next_runnable_tasks(project.id)

    assert runnable == []


@pytest.mark.asyncio
async def test_task_with_multiple_dependencies_waits_for_all(session, project):
    dep_a = await _make_task(session, project, status=TaskStatus.DONE)
    dep_b = await _make_task(session, project, status=TaskStatus.PENDING)
    dependent = await _make_task(session, project, depends_on=[dep_a.id, dep_b.id])

    orch = Orchestrator(session)
    runnable = await orch._next_runnable_tasks(project.id)

    # dependent must NOT appear yet — dep_b isn't done
    assert dependent.id not in [t.id for t in runnable]
    assert dep_b.id in [t.id for t in runnable]
