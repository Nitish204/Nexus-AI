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
a small, ordered list of concrete engineering tasks. Output STRICT JSON
only, no prose, no markdown fences, matching this schema:

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

Keep it to 3-6 tasks. Always include a qa_engineer task to test what the
engineers build, and a devops_engineer task if deployment/infra is implied."""


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
