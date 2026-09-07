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
import asyncio
import json
import logging

from json_repair import repair_json
from openai import AsyncOpenAI, APIStatusError
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.core.config import get_settings
from app.core.events import event_bus
from app.core.safe_path import UnsafeGeneratedPath, safe_relative_path
from app.db.models import AgentMessage, AgentRole, GeneratedFile, Task, TaskStatus
from datetime import datetime, timezone

settings = get_settings()
logger = logging.getLogger("nexus.agents")


def parse_agent_json(raw_text: str) -> dict:
    """
    Every agent asks the LLM for strict JSON (files + notes), but LLMs
    routinely produce near-JSON instead. Strict parsing is tried first,
    and json_repair is only used as a fallback.
    """
    cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Strict JSON parse failed (%s), attempting repair...", exc)
        repaired = repair_json(cleaned)
        return json.loads(repaired)


class AgentBase(abc.ABC):
    role: AgentRole
    system_prompt: str

    def __init__(self, session: AsyncSession):
        self.session = session
        # Provider switch: "local" points the same OpenAI-compatible
        # client at a local server (Ollama/LM Studio/vLLM) instead of
        # Groq — no code path changes, no API key needed, nothing
        # leaves the machine. Falls back to Groq if misconfigured.
        if settings.llm_provider == "local":
            self.client = AsyncOpenAI(
                api_key="local-llm-no-key-required",
                base_url=settings.local_llm_base_url,
                timeout=120.0,  # local inference is slower than a cloud API, especially on CPU
            )
            self.model_name = settings.local_llm_model
        else:
            self.client = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=45.0,
            )
            self.model_name = settings.agent_model

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

    async def _write_generated_file(
        self, project_id: str, path: str, content: str, language: str
    ) -> GeneratedFile | None:
        """
        Create-or-update a GeneratedFile by (project_id, path).

        Every concrete agent previously did `self.session.add(GeneratedFile(...))`
        unconditionally on every call to handle_response — always inserting a
        new row, never checking whether a file at that path already existed
        for the project. This is guaranteed to fire repeatedly in normal
        operation: the orchestrator's sandbox fix-and-retry loop
        (SANDBOX_GATED_ROLES in services/orchestrator.py) sets a task back to
        PENDING and re-runs the *same* agent on the *same* task when
        generated code fails its tests, which calls handle_response again for
        the same file path. Every retry was permanently duplicating rows —
        which then get fed back into every subsequent agent's context
        (_gather_context selects *all* files for the project), inflated the
        file/quality counts shown in the UI, and were all written to disk
        during deploy/sandbox/export, wasting the versioning already defined
        on the model (GeneratedFile.version existed but was never used).

        This now looks up the existing row for (project_id, path) first: if
        found, its content/language/version/updated_at are updated in place;
        otherwise a new row is created at version 1. Also the single place
        where an agent-authored path is validated with safe_relative_path()
        before it ever reaches the database — rejecting it here, at the
        source, is more robust than only sanitizing it later in each
        downstream consumer (sandbox, deploy, GitHub export).

        Returns the written GeneratedFile, or None if `path` was rejected as
        unsafe (the caller should skip logging/streaming that file in that case).
        """
        try:
            safe_path = safe_relative_path(path)
        except UnsafeGeneratedPath as exc:
            logger.warning(
                "[%s] project=%s rejected unsafe generated file path %r: %s",
                self.role.value, project_id, path, exc,
            )
            return None

        existing = (
            await self.session.exec(
                select(GeneratedFile).where(
                    GeneratedFile.project_id == project_id,
                    GeneratedFile.path == safe_path,
                )
            )
        ).first()

        if existing:
            existing.content = content
            existing.language = language
            existing.written_by = self.role
            existing.version += 1
            existing.updated_at = datetime.now(timezone.utc)
            self.session.add(existing)
            return existing

        new_file = GeneratedFile(
            project_id=project_id, path=safe_path, content=content,
            language=language, written_by=self.role,
        )
        self.session.add(new_file)
        return new_file

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

        max_rate_limit_retries = 1
        for attempt in range(max_rate_limit_retries + 1):
            try:
                logger.info("[%s] task=%s calling model=%s (attempt %d)", self.role.value, task.id, self.model_name, attempt + 1)
                full_text = ""
                stream = await self.client.chat.completions.create(
                    model=self.model_name,
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
                    raise ValueError(
                        f"Model '{self.model_name}' returned an empty response. "
                        "Verify this model name is still valid for your configured provider."
                    )

                await self.handle_response(task, full_text)
                task.status = TaskStatus.IN_REVIEW
                task.result_summary = full_text[:280]
                logger.info("[%s] task=%s completed successfully", self.role.value, task.id)
                break  # success — leave the retry loop

            except APIStatusError as exc:
                if exc.status_code in (429, 413):
                    logger.warning(
                        "[%s] task=%s hit rate limit, status=%d (attempt %d): %s",
                        self.role.value, task.id, exc.status_code, attempt + 1, exc,
                    )
                    if attempt < max_rate_limit_retries:
                        await self._log(task, "Hit the provider's rate limit — waiting 25s and retrying once...", "status")
                        await asyncio.sleep(25)
                        continue
                    logger.error("[%s] task=%s FAILED: rate limit persisted after retry", self.role.value, task.id)
                    task.status = TaskStatus.FAILED
                    await self._log(
                        task,
                        "Failed: the LLM provider's rate limit was exceeded and persisted after one retry. "
                        "Try a smaller/more specific request, space out commands, or upgrade your plan.",
                        "error",
                    )
                else:
                    logger.error("[%s] task=%s FAILED: %s", self.role.value, task.id, exc, exc_info=True)
                    task.status = TaskStatus.FAILED
                    await self._log(task, f"Error: {exc}", "error")
                break

            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] task=%s FAILED: %s", self.role.value, task.id, exc, exc_info=True)
                task.status = TaskStatus.FAILED
                await self._log(task, f"Error: {exc}", "error")
                break

        self.session.add(task)
        await self.session.commit()
        await event_bus.publish(
            task.project_id, "task_status", {"task_id": task.id, "status": task.status.value, "role": self.role.value}
        )
        return task
