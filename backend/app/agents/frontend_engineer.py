"""FrontendEngineerAgent — generates UI code (React components, styles)
that consume whatever API the BackendEngineerAgent has already produced."""
import json

from app.agents.base import AgentBase
from app.db.models import AgentRole, GeneratedFile, Task

FRONTEND_SYSTEM_PROMPT = """You are the Frontend Engineer agent inside NEXUS.
Given a task and the existing backend files as context, generate React
components that integrate with the described API. Output STRICT JSON only:

{
  "files": [
    {"path": "relative/file/path.jsx", "content": "full file content", "language": "javascript"}
  ],
  "notes": "one sentence summary"
}

Write complete, working components — functional, hooks-based, no class
components. Reference actual endpoint paths/fields seen in the backend
context rather than inventing new ones."""


class FrontendEngineerAgent(AgentBase):
    role = AgentRole.FRONTEND_ENGINEER
    system_prompt = FRONTEND_SYSTEM_PROMPT

    def build_prompt(self, task: Task, context: str) -> str:
        return f"Task: {task.title}\n{task.description}\n\nExisting project files (esp. backend APIs):\n{context}"

    async def handle_response(self, task: Task, raw_text: str) -> None:
        cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)
        for f in data["files"]:
            self.session.add(GeneratedFile(
                project_id=task.project_id, path=f["path"], content=f["content"],
                language=f.get("language", "javascript"), written_by=self.role,
            ))
            await self._log(task, f["content"], "code")
        await self.session.commit()
        await self._log(task, data.get("notes", "Frontend implementation complete."), "status")
