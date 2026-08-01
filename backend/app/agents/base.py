"""
NEXUS — Agent base class.

Every agent (PM, Backend, Frontend, QA, DevOps) is a thin subclass of
this. Shared behavior lives here: how an agent talks to the LLM, how it
streams its reasoning to the event bus, and how it writes results back
to the blackboard (Task, AgentMessage, GeneratedFile tables).

Design principle: agents are stateless between calls. All state that
matters lives in the database, not in the Python object. This means the
orchestrator can crash and resume, and any agent instance is disposable.
"""
from __future__ import annotations

import abc
import logging

from openai import AsyncOpenAI
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.config import get_settings
from app.core.events import event_bus
from app.db.models import AgentMessage, AgentRole, GeneratedFile, Task, TaskStatus

settings = get_settings()
logger = logging.getLogger("nexus.agents")


class AgentBase(abc.ABC):
    role: AgentRole
    system_prompt: str

    def __init__(self, session: AsyncSession):
        self.session = session
        # Groq exposes an OpenAI-compatible endpoint, so the standard
        # openai SDK works unchanged — just point base_url at Groq and
        # use a Groq API key instead of an OpenAI one.
        # Explicit timeout: the SDK's default can be up to 10 minutes,
        # which means a hung network call would sit completely silent
        # (no error, no log, nothing) for a very long time before ever
        # surfacing as a failure. 45s is generous for Groq (typically
        # sub-second to a few seconds) while still failing fast enough
        # to be diagnosable.
        self.client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=45.0,
        )

    # ---- to be implemented by each concrete agent ----
    @abc.abstractmethod
    def build_prompt(self, task: Task, context: str) -> str:
        """Turn a Task + prior context into the user message sent to the LLM."""

    @abc.abstractmethod
    async def handle_response(self, task: Task, raw_text: str) -> None:
        """Parse the LLM's raw output and persist it (e.g. as GeneratedFile rows)."""

    # ---- shared machinery ----
    async def _log(self, task: Task, content: str, message_type: str = "reasoning") -> None:
        msg = AgentMessage(task_id=task.id, role=self.role, content=content, message_type=message_type)
        self.session.add(msg)
        await self.session.commit()
        await event_bus.publish(
            task.project_id,
            "agent_message",
            {"task_id": task.id, "role": self.role.value, "content": content, "message_type": message_type},
        )

    async def _gather_context(self, task: Task) -> str:
        """Pull relevant prior files/messages so the agent isn't starting blind."""
        result = await self.session.exec(
            select(GeneratedFile).where(GeneratedFile.project_id == task.project_id)
        )
        files = result.all()
        if not files:
            return "No files exist yet in this project."
        return "\n".join(f"--- {f.path} ---\n{f.content[:1500]}" for f in files)

    async def run(self, task: Task) -> Task:
        logger.info("[%s] task=%s starting: %s", self.role.value, task.id, task.title)

        task.status = TaskStatus.IN_PROGRESS
        self.session.add(task)
        await self.session.commit()
        await event_bus.publish(
            task.project_id, "task_status", {"task_id": task.id, "status": task.status.value, "role": self.role.value}
        )

        context = await self._gather_context(task)
        prompt = self.build_prompt(task, context)

        await self._log(task, f"Starting: {task.title}", "status")

        try:
            logger.info("[%s] task=%s calling model=%s", self.role.value, task.id, settings.agent_model)
            full_text = ""
            stream = await self.client.chat.completions.create(
                model=settings.agent_model,
                max_tokens=settings.max_tokens_per_agent_call,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if not delta:
                    continue
                full_text += delta
                await event_bus.publish(
                    task.project_id,
                    "agent_stream",
                    {"task_id": task.id, "role": self.role.value, "delta": delta},
                )

            logger.info("[%s] task=%s LLM call complete, %d chars received", self.role.value, task.id, len(full_text))

            if not full_text.strip():
                # A real failure mode worth naming explicitly: the call
                # succeeded (no exception) but returned nothing — e.g. a
                # model name that's silently invalid/deprecated on
                # Groq's side, or the request being rejected in a way
                # that doesn't raise. Without this check it looks
                # identical to a hang from the outside.
                raise ValueError(
                    f"Model '{settings.agent_model}' returned an empty response. "
                    "Verify this model name is still valid at console.groq.com/docs/models."
                )

            await self.handle_response(task, full_text)
            task.status = TaskStatus.IN_REVIEW
            task.result_summary = full_text[:280]
            logger.info("[%s] task=%s completed successfully", self.role.value, task.id)

        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] task=%s FAILED: %s", self.role.value, task.id, exc, exc_info=True)
            task.status = TaskStatus.FAILED
            await self._log(task, f"Error: {exc}", "error")

        self.session.add(task)
        await self.session.commit()
        await event_bus.publish(
            task.project_id, "task_status", {"task_id": task.id, "status": task.status.value, "role": self.role.value}
        )
        return task
