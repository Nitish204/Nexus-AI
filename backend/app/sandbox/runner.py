"""
NEXUS — Sandbox execution service (Phase 3).

Runs a project's generated Python files + QA-written tests inside an
ephemeral, resource-limited Docker container, and returns structured
pass/fail results. This is what turns the QA agent's tests from "text
that looks like tests" into an actual gate: if execution fails, the
orchestrator feeds the error back to the responsible engineer agent for
a fix-and-retry loop instead of blindly marking the task DONE.

Safety notes:
- No network access inside the sandbox container (network_disabled=True).
- Hard memory limit + wall-clock timeout enforced.
- Container is always removed after the run, win or lose.
- Only files belonging to the project are ever written into the
  container — nothing from the host filesystem is exposed.
"""
from __future__ import annotations

import tarfile
import io
import uuid
from dataclasses import dataclass, field

import docker
from docker.errors import ContainerError, ImageNotFound, APIError

from app.core.config import get_settings
from app.db.models import GeneratedFile

settings = get_settings()


@dataclass
class SandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    error: str = ""
    files_executed: list[str] = field(default_factory=list)


class SandboxRunner:
    """Wraps docker-py to execute a set of Python files (source +
    pytest tests) in one throwaway container per run."""

    def __init__(self) -> None:
        self._client = None  # lazy — don't require a docker daemon at import time

    @property
    def client(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _build_tar(self, files: list[GeneratedFile]) -> bytes:
        """Package project files into a tar stream to inject into the container."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for f in files:
                data = f.content.encode("utf-8")
                info = tarfile.TarInfo(name=f.path)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        buf.seek(0)
        return buf.read()

    async def run_python_tests(self, files: list[GeneratedFile]) -> SandboxResult:
        python_files = [f for f in files if f.language == "python"]
        if not python_files:
            return SandboxResult(success=True, stdout="No Python files to execute.")

        container_name = f"nexus-sandbox-{uuid.uuid4().hex[:10]}"
        container = None
        try:
            container = self.client.containers.create(
                image=settings.docker_image_python,
                name=container_name,
                command="sh -c 'pip install --quiet pytest && python -m pytest -q /workspace 2>&1'",
                working_dir="/workspace",
                mem_limit=settings.sandbox_memory_limit,
                network_disabled=True,
                detach=True,
            )
            container.put_archive("/workspace", self._build_tar(python_files))
            container.start()

            try:
                exit_status = container.wait(timeout=settings.sandbox_timeout_seconds)
                exit_code = exit_status.get("StatusCode", 1)
                logs = container.logs().decode("utf-8", errors="replace")
                return SandboxResult(
                    success=exit_code == 0,
                    stdout=logs,
                    exit_code=exit_code,
                    files_executed=[f.path for f in python_files],
                )
            except Exception:
                container.kill()
                return SandboxResult(
                    success=False,
                    timed_out=True,
                    error=f"Execution exceeded {settings.sandbox_timeout_seconds}s timeout.",
                    files_executed=[f.path for f in python_files],
                )

        except ImageNotFound:
            return SandboxResult(success=False, error=f"Sandbox image {settings.docker_image_python} not found locally — run `docker pull {settings.docker_image_python}`.")
        except (ContainerError, APIError) as exc:
            return SandboxResult(success=False, error=f"Docker error: {exc}")
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass


sandbox_runner = SandboxRunner()
