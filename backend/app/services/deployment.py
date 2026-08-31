"""
NEXUS — Deployment service (Phase 5).
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
from app.services.push_notifications import send_push_to_project_owner

settings = get_settings()


def _materialize_project(files: list[GeneratedFile]) -> Path:
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
    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    async def deploy(self, project_root: Path, deployment: Deployment) -> Deployment:
        dockerfile = project_root / "Dockerfile"
        if not dockerfile.exists():
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


class KubernetesProvider(DeployProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    async def deploy(self, project_root: Path, deployment: Deployment) -> Deployment:
        dockerfile = project_root / "Dockerfile"
        if not dockerfile.exists():
            deployment.status = "failed"
            deployment.log = "No Dockerfile found — the DevOps agent task must run before deployment."
            return deployment

        try:
            from kubernetes import client as k8s_client, config as k8s_config
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()

            name = f"nexus-{deployment.project_id[:8]}"
            image_tag = f"{name}:latest"

            import docker as docker_sdk
            docker_client = docker_sdk.from_env()
            docker_client.images.build(path=str(project_root), tag=image_tag, rm=True)

            apps_api = k8s_client.AppsV1Api()
            core_api = k8s_client.CoreV1Api()

            deployment_manifest = k8s_client.V1Deployment(
                metadata=k8s_client.V1ObjectMeta(name=name, labels={"app": name}),
                spec=k8s_client.V1DeploymentSpec(
                    replicas=1,
                    selector=k8s_client.V1LabelSelector(match_labels={"app": name}),
                    template=k8s_client.V1PodTemplateSpec(
                        metadata=k8s_client.V1ObjectMeta(labels={"app": name}),
                        spec=k8s_client.V1PodSpec(containers=[
                            k8s_client.V1Container(
                                name=name, image=image_tag,
                                ports=[k8s_client.V1ContainerPort(container_port=8000)],
                            )
                        ]),
                    ),
                ),
            )
            apps_api.create_namespaced_deployment(namespace="default", body=deployment_manifest)

            service_manifest = k8s_client.V1Service(
                metadata=k8s_client.V1ObjectMeta(name=f"{name}-svc"),
                spec=k8s_client.V1ServiceSpec(
                    selector={"app": name},
                    ports=[k8s_client.V1ServicePort(port=80, target_port=8000)],
                    type="LoadBalancer",
                ),
            )
            core_api.create_namespaced_service(namespace="default", body=service_manifest)

            deployment.status = "live"
            deployment.url = f"k8s://service/{name}-svc (check `kubectl get svc {name}-svc` for the external IP)"
            deployment.log = f"Applied Deployment '{name}' and Service '{name}-svc' to the 'default' namespace."
        except ImportError:
            deployment.status = "failed"
            deployment.log = "The 'kubernetes' python package isn't installed — add it to requirements.txt."
        except Exception as exc:  # noqa: BLE001
            deployment.status = "failed"
            deployment.log = f"Kubernetes deploy error: {exc}"
        return deployment


PROVIDERS: dict[str, type[DeployProvider]] = {
    "render": RenderProvider,
    "local": LocalDockerProvider,
    "kubernetes": KubernetesProvider,
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

    if updated.status == "live":
        await send_push_to_project_owner(
            session, project_id,
            title="Deployment live",
            body=f"Your deployment finished — {updated.url or 'check NEXUS for details'}.",
            url=f"/?project={project_id}",
        )
    elif updated.status == "failed":
        await send_push_to_project_owner(
            session, project_id,
            title="Deployment failed",
            body=updated.log[:150] if updated.log else "Open NEXUS to see what went wrong.",
            url=f"/?project={project_id}",
        )

    return updated
