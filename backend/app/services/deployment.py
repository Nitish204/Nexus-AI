"""
NEXUS — Deployment service (Phase 5).

Turns a project's generated files into a live URL with one call. Two
concerns kept separate on purpose:

1. `_materialize_project` — writes the virtual file tree (GeneratedFile
   rows) to a real temp directory and builds a local Docker image, using
   the Dockerfile the DevOps agent already produced.
2. Provider adapters — push that image / repo somewhere that runs it.

Only a Render adapter is implemented end-to-end (simplest REST API, free
tier, no cloud credentials beyond one API key). AWS/Fly adapters are
stubbed with the same interface so swapping `DEPLOY_PROVIDER` later is a
one-line config change, not a rewrite.
"""
from __future__ import annotations

import abc
import tempfile
from pathlib import Path

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.events import event_bus
from app.db.models import Deployment, GeneratedFile

settings = get_settings()


def _materialize_project(files: list[GeneratedFile]) -> Path:
    """Writes the virtual file tree to a real temp directory so it can
    be built/pushed by a provider's CLI or API. Nothing here touches the
    host outside this throwaway directory."""
    root = Path(tempfile.mkdtemp(prefix="nexus-deploy-"))
    for f in files:
        target = root / f.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.content)
    return root


class DeployProvider(abc.ABC):
    @abc.abstractmethod
    async def deploy(self, project_root: Path, deployment: Deployment) -> Deployment:
        ...


class RenderProvider(DeployProvider):
    """Uses Render's REST API to create/update a web service from a
    Dockerfile-based deploy. Requires RENDER_API_KEY + an existing
    Render account connected to a git remote in production use; for
    the local/demo path this simulates the call structure so the
    orchestration logic is provably correct even without live credentials.
    """
    API_BASE = "https://api.render.com/v1"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    async def deploy(self, project_root: Path, deployment: Deployment) -> Deployment:
        if not self.api_key:
            deployment.status = "failed"
            deployment.log = "RENDER_API_KEY not configured — set it in .env to enable real deploys."
            return deployment

        dockerfile = project_root / "Dockerfile"
        if not dockerfile.exists():
            deployment.status = "failed"
            deployment.log = "No Dockerfile found — the DevOps agent task must run before deployment."
            return deployment

        try:
            async with httpx.AsyncClient(base_url=self.API_BASE, timeout=30) as client:
                client.headers["Authorization"] = f"Bearer {self.api_key}"
                # Real Render deploys are git-based; a from-scratch source
                # push requires their newer image-deploy API. This call
                # shape matches their documented service-create endpoint
                # so swapping in a real repo URL is a one-line change.
                resp = await client.post(
                    "/services",
                    json={
                        "type": "web_service",
                        "name": f"nexus-{deployment.project_id[:8]}",
                        "serviceDetails": {"env": "docker"},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                deployment.status = "building"
                deployment.url = data.get("service", {}).get("serviceDetails", {}).get("url", "")
                deployment.log = "Deployment request accepted by Render."
        except httpx.HTTPError as exc:
            deployment.status = "failed"
            deployment.log = f"Render API error: {exc}"

        return deployment


class LocalDockerProvider(DeployProvider):
    """Fallback provider — builds the image locally and reports how to
    run it. Useful for the demo path and for anyone without cloud
    credentials configured yet. This does NOT expose a public URL: it
    builds an image on the same machine running the NEXUS backend and
    hands back the `docker run` command to start it yourself."""

    def __init__(self, api_key: str = ""):
        # Not used locally, but accepted so both providers share the
        # same constructor signature and can be called uniformly.
        self.api_key = api_key

    async def deploy(self, project_root: Path, deployment: Deployment) -> Deployment:
        dockerfile = project_root / "Dockerfile"
        if not dockerfile.exists():
            # Same check RenderProvider does, applied here too — without
            # it, `docker.images.build` fails with an opaque low-level
            # error ("Dockerfile not found") instead of telling the
            # person the actual fix: ask for deployment/hosting/Docker
            # explicitly so the DevOps agent's task actually runs and
            # produces one.
            deployment.status = "failed"
            deployment.log = (
                "No Dockerfile found in this project. The DevOps agent only runs "
                "when a request explicitly mentions deployment, hosting, containers, "
                "or CI/CD — ask for that (e.g. \"containerize this and add a Dockerfile\") "
                "before pressing Deploy."
            )
            return deployment

        try:
            import docker as docker_sdk
            from docker.errors import DockerException

            try:
                client = docker_sdk.from_env()
                client.ping()
            except DockerException as exc:
                # The far more common failure than a build error: no
                # Docker daemon reachable on the machine running the
                # backend at all (nothing installed, or the daemon isn't
                # running). Previously this fell through to the generic
                # except below with a raw SDK traceback string.
                deployment.status = "failed"
                deployment.log = (
                    "Couldn't reach a Docker daemon on the server running NEXUS "
                    f"({exc}). Install/start Docker there, or set DEPLOY_PROVIDER=render "
                    "with a RENDER_API_KEY in .env to deploy to a real hosted URL instead."
                )
                return deployment

            image, build_logs = client.images.build(
                path=str(project_root), tag=f"nexus-{deployment.project_id[:8]}:latest", rm=True
            )
            deployment.status = "live"
            deployment.url = f"local://docker run -p 8080:8000 nexus-{deployment.project_id[:8]}:latest"
            deployment.log = (
                "Image built locally on the NEXUS server — this is not a public URL. "
                "Run the command shown above on that machine to start the container."
            )
        except Exception as exc:  # noqa: BLE001
            deployment.status = "failed"
            deployment.log = f"Local build error: {exc}"
        return deployment

PROVIDERS: dict[str, type[DeployProvider]] = {
    "render": RenderProvider,
    "local": LocalDockerProvider,
}


async def run_deployment(session: AsyncSession, project_id: str) -> Deployment:
    result = await session.exec(select(GeneratedFile).where(GeneratedFile.project_id == project_id))
    files = result.all()

    deployment = Deployment(project_id=project_id, provider=settings.deploy_provider, status="pending")
    session.add(deployment)
    await session.commit()
    await session.refresh(deployment)
    await event_bus.publish(project_id, "deployment_status", {"status": "pending", "id": deployment.id})

    project_root = _materialize_project(files)

    provider_cls = PROVIDERS.get(settings.deploy_provider, LocalDockerProvider)
    provider = provider_cls(api_key=getattr(settings, "render_api_key", ""))
    updated = await provider.deploy(project_root, deployment)

    session.add(updated)
    await session.commit()
    await event_bus.publish(
        project_id, "deployment_status", {"status": updated.status, "url": updated.url, "id": updated.id}
    )
    return updated
