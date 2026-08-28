"""
NEXUS — On-demand AI code review.

Separate from QAEngineerAgent's review_notes (which only fire as a side
effect of a QA task in an orchestration run). This lets the frontend
request a review of any single file at any time — e.g. a "Review" button
in the file browser — without spinning up a full multi-agent task.
"""
from __future__ import annotations

import json

from json_repair import repair_json
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.db.models import GeneratedFile

settings = get_settings()

REVIEW_SYSTEM_PROMPT = """You are a senior code reviewer. Given a single file's
content, review it for correctness bugs, security issues, performance
problems, and readability/maintainability concerns. Be specific and
reference line-level detail where possible. Output STRICT JSON only:

{
  "summary": "one or two sentence overall verdict",
  "issues": [
    {"severity": "critical|warning|suggestion", "line": 12, "message": "specific issue"}
  ],
  "score": 0-100
}

If the file is clean, return an empty issues list and a high score."""


def _client() -> AsyncOpenAI:
    if settings.llm_provider == "local":
        return AsyncOpenAI(api_key="local-llm-no-key-required", base_url=settings.local_llm_base_url, timeout=120.0)
    return AsyncOpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1", timeout=45.0)


def _model_name() -> str:
    return settings.local_llm_model if settings.llm_provider == "local" else settings.agent_model


async def review_file(file: GeneratedFile) -> dict:
    client = _client()
    resp = await client.chat.completions.create(
        model=_model_name(),
        max_tokens=settings.max_tokens_per_agent_call,
        messages=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": f"File: {file.path}\n\n{file.content}"},
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return json.loads(repair_json(cleaned))
