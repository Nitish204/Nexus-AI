"""
ProductManagerAgent — the front door of NEXUS.

Takes a raw request (typed or voice-transcribed, e.g. "Build a Django
authentication system with JWT and PostgreSQL") and decomposes it into
concrete Task rows assigned to the right engineering agents, with
dependency ordering so e.g. frontend work waits on the backend API.
"""
import json

from sqlmodel import select

from app.agents.base import AgentBase
from app.db.models import AgentRole, Task, TaskStatus

PM_SYSTEM_PROMPT = """You are the Product Manager agent inside NEXUS, an
autonomous AI developer workspace. Given a feature request, break it into
the SMALLEST list of concrete engineering tasks that actually satisfies
it — do not add roles or scope the person didn't ask for. Output STRICT
JSON only, no prose, no markdown fences, matching this schema:

{
  "tasks": [
    {
      "title": "short imperative title",
      "description": "what exactly needs to be built, specific enough for an engineer to act on without asking questions",
      "assigned_role": "backend_engineer | frontend_engineer | qa_engineer | devops_engineer",
      "depends_on_titles": ["title of another task in this list, if any"]
    }
  ]
}

Scope rules — follow these strictly:
- A simple script, CLI tool, algorithm, single-file program, or "just
  the code for X" request (e.g. "build a simple to-do list in python")
  gets exactly ONE backend_engineer task and NOTHING else. No
  frontend_engineer, no devops_engineer, and skip qa_engineer too unless
  the request explicitly asks for tests. The person wants to see their
  requested code, not a scaffold.
- Only add a frontend_engineer task if the request explicitly implies a
  UI (web page, app screen, "with a frontend", etc.) — a CLI or plain
  script is never a frontend task.
- Only add a devops_engineer task if the request explicitly mentions
  deployment, hosting, containers, Docker, or CI/CD. Never add one by
  default, and never add one "just in case."
- Only add a qa_engineer task if the request explicitly asks for tests,
  or the project already has meaningful existing code worth testing.
- When in doubt, do less. A 1-task plan is correct far more often than
  a 5-task plan. Match the size of the plan to the size of the ask."""


class ProductManagerAgent(AgentBase):
    role = AgentRole.PRODUCT_MANAGER
    system_prompt = PM_SYSTEM_PROMPT

    def build_prompt(self, task: Task, context: str) -> str:
        return f"Feature request:\n{task.description}\n\nExisting project context:\n{context}"

    async def handle_response(self, task: Task, raw_text: str) -> None:
        cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)

        title_to_id: dict[str, str] = {}
        created: list[Task] = []

        for item in data["tasks"]:
            new_task = Task(
                project_id=task.project_id,
                title=item["title"],
                description=item["description"],
                assigned_role=AgentRole(item["assigned_role"]),
                status=TaskStatus.PENDING,
            )
            self.session.add(new_task)
            created.append(new_task)
            title_to_id[item["title"]] = new_task.id

        await self.session.commit()

        # second pass: wire up dependencies now that all tasks have IDs
        for item, new_task in zip(data["tasks"], created):
            deps = [title_to_id[t] for t in item.get("depends_on_titles", []) if t in title_to_id]
            if deps:
                new_task.depends_on = deps
                self.session.add(new_task)
        await self.session.commit()

        await self._log(
            task,
            f"Decomposed request into {len(created)} tasks: " + ", ".join(t.title for t in created),
            "status",
        )
