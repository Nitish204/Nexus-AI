"""
BackendEngineerAgent — generates server-side code (APIs, models, auth,
DB migrations) as structured files, output as JSON so the live code
editor can render each file individually as it streams in.
"""
import json

from app.agents.base import AgentBase
from app.db.models import AgentRole, GeneratedFile, Task

BACKEND_SYSTEM_PROMPT = """You are the Backend Engineer agent inside NEXUS.
Given a task description and existing project context, generate the
necessary backend code (Python/Django/FastAPI/SQL as appropriate).
Output STRICT JSON only, no prose outside the JSON, matching:
{
  "files": [
    {"path": "relative/file/path.py", "content": "full file content", "language": "python"}
  ],
  "notes": "one sentence describing what you built and any assumptions made"
}
Requirements:
- Write COMPLETE, runnable code for every file — no placeholders, no
  "# TODO", no "# implementation omitted for brevity", no ellipses.
- Include all necessary imports, error handling, and type hints.
- If the task is large, prioritize finishing fewer files completely
  over covering more files partially.
- Do not summarize or truncate code under any circumstances."""


class BackendEngineerAgent(AgentBase):
    role = AgentRole.BACKEND_ENGINEER
    system_prompt = BACKEND_SYSTEM_PROMPT

    def build_prompt(self, task: Task, context: str) -> str:
        return f"Task: {task.title}\n{task.description}\n\nExisting project files:\n{context}"

    async def handle_response(self, task: Task, raw_text: str) -> None:
        cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(cleaned)

        for f in data["files"]:
            gen_file = GeneratedFile(
                project_id=task.project_id,
                path=f["path"],
                content=f["content"],
                language=f.get("language", "python"),
                written_by=self.role,
            )
            self.session.add(gen_file)
            await self._log(task, f["content"], "code")

        await self.session.commit()
        await self._log(task, data.get("notes", "Backend implementation complete."), "status")
