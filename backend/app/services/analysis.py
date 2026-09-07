"""
NEXUS — Analytics service (Phase 6).

Runs pure-Python static analysis tools against generated files so the
dashboard can show live quality/security scores without needing to
actually execute untrusted code (that's the sandbox service's job).
"""
import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import mi_visit

from app.db.models import AnalysisResult, GeneratedFile


def _complexity_score(source: str) -> float:
    try:
        blocks = cc_visit(source)
        if not blocks:
            return 0.0
        return round(sum(b.complexity for b in blocks) / len(blocks), 2)
    except Exception:
        return 0.0


def _maintainability_index(source: str) -> float:
    try:
        return round(mi_visit(source, multi=True), 2)
    except Exception:
        return 0.0


def _bandit_scan(source: str) -> int:
    """Run bandit against a temp file; return count of flagged issues."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(source)
        path = f.name
    try:
        result = subprocess.run(
            ["bandit", "-f", "json", "-q", path], capture_output=True, text=True, timeout=15
        )
        report = json.loads(result.stdout or "{}")
        return len(report.get("results", []))
    except Exception:
        return 0
    finally:
        Path(path).unlink(missing_ok=True)


def _ruff_scan(source: str) -> int:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(source)
        path = f.name
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format", "json", path], capture_output=True, text=True, timeout=15
        )
        issues = json.loads(result.stdout or "[]")
        return len(issues)
    except Exception:
        return 0
    finally:
        Path(path).unlink(missing_ok=True)


async def analyze_file(file: GeneratedFile) -> AnalysisResult:
    if file.language != "python":
        # Non-Python analysis (JS lint etc.) is a Phase-6 follow-up;
        # for now we return a neutral result so the dashboard still renders.
        return AnalysisResult(project_id=file.project_id, file_path=file.path)

    # Bug fix: _bandit_scan/_ruff_scan call subprocess.run(), which
    # blocks the calling thread until the subprocess exits (up to the
    # 15s timeout). Calling that directly from an `async def` doesn't
    # make it non-blocking — it blocks FastAPI's single-threaded event
    # loop for that whole duration, freezing every other request,
    # WebSocket message, and background task on the entire server, not
    # just this one analysis call. asyncio.to_thread() moves each
    # blocking call onto a worker thread so the event loop stays free;
    # running all three concurrently also means the total wait is
    # roughly max(complexity, bandit, ruff) instead of the sum of all three.
    complexity, security_issues, lint_issues = await asyncio.gather(
        asyncio.to_thread(_complexity_score, file.content),
        asyncio.to_thread(_bandit_scan, file.content),
        asyncio.to_thread(_ruff_scan, file.content),
    )
    maintainability = await asyncio.to_thread(_maintainability_index, file.content)

    return AnalysisResult(
        project_id=file.project_id,
        file_path=file.path,
        complexity_score=complexity,
        security_issues=security_issues,
        lint_issues=lint_issues,
        raw_report={"maintainability_index": maintainability},
    )
