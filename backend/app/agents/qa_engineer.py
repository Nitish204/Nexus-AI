"""QAEngineerAgent — writes tests for what the other engineers built and
flags issues in plain review comments. Test execution itself happens in
the sandbox service (Phase 3), not here — this agent's job is authoring
tests and code review, not running arbitrary code."""

from app.agents.base import AgentBase, parse_agent_json
from app.db.models import AgentRole, GeneratedFile, Task

QA_SYSTEM_PROMPT = """You are the QA Engineer agent inside NEXUS. Given the
existing project files, write tests (pytest for Python, Jest/RTL for
React) covering the most important behavior, and list any bugs or risks
you notice by reading the code. Output STRICT JSON only:

{
  "files": [
    {"path": "tests/test_x.py", "content": "full test file content", "language": "python"}
  ],
  "review_notes": ["specific issue or risk found in existing code", "..."]
}

If you find no issues, return an empty review_notes list. Be specific —
reference file names and line-level concerns, not generic advice."""


class QAEngineerAgent(AgentBase):
    role = AgentRole.QA_ENGINEER
    system_prompt = QA_SYSTEM_PROMPT

    def build_prompt(self, task: Task, context: str) -> str:
        return f"Task: {task.title}\n{task.description}\n\nProject files to test/review:\n{context}"

    async def handle_response(self, task: Task, raw_text: str) -> None:
        data = parse_agent_json(raw_text)
        for f in data["files"]:
            self.session.add(GeneratedFile(
                project_id=task.project_id, path=f["path"], content=f["content"],
                language=f.get("language", "python"), written_by=self.role,
            ))
            await self._log(task, f["content"], "code")
        await self.session.commit()

        notes = data.get("review_notes", [])
        summary = "No issues found." if not notes else "Issues found:\n" + "\n".join(f"- {n}" for n in notes)
        await self._log(task, summary, "status")
