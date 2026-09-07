"""DevOpsEngineerAgent — generates containerization and CI/CD artifacts.
Actual cloud deployment (Phase 5) is triggered separately by the
DeploymentService, which consumes the Dockerfile this agent produces."""

from app.agents.base import AgentBase, parse_agent_json
from app.db.models import AgentRole, Task

DEVOPS_SYSTEM_PROMPT = """You are the DevOps Engineer agent inside NEXUS.
Given the existing project files, produce containerization and CI/CD
artifacts appropriate to the stack you see (Dockerfile, docker-compose.yml,
.github/workflows/ci.yml). Output STRICT JSON only:

{
  "files": [
    {"path": "Dockerfile", "content": "full file content", "language": "dockerfile"}
  ],
  "notes": "one sentence describing the deployment approach chosen"
}

Keep images minimal and production-sensible (multi-stage builds where it
matters, no dev dependencies in the final image)."""


class DevOpsEngineerAgent(AgentBase):
    role = AgentRole.DEVOPS_ENGINEER
    system_prompt = DEVOPS_SYSTEM_PROMPT

    def build_prompt(self, task: Task, context: str) -> str:
        return f"Task: {task.title}\n{task.description}\n\nProject files to containerize/deploy:\n{context}"

    async def handle_response(self, task: Task, raw_text: str) -> None:
        data = parse_agent_json(raw_text)
        for f in data["files"]:
            written = await self._write_generated_file(
                task.project_id, f["path"], f["content"], f.get("language", "dockerfile")
            )
            if written is not None:
                await self._log(task, f["content"], "code")
        await self.session.commit()
        await self._log(task, data.get("notes", "DevOps artifacts generated."), "status")
