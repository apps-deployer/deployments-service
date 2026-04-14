import base64
import logging
import os
import time

import httpx
from kubernetes import client, config

from src.workers.celery_app import celery, settings

logger = logging.getLogger(__name__)

NAMESPACE = os.environ.get("K8S_NAMESPACE", "apps-deployer")
JOB_TIMEOUT = 600
JOB_TTL_AFTER_FINISHED = 300


def _callback(path: str, **json_body):
    url = f"{settings.server.base_url}{path}"
    resp = httpx.put(url, json=json_body)
    resp.raise_for_status()


def _load_k8s():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _generate_dockerfile(deploy_config: dict) -> str:
    base_image = deploy_config["base_image"]
    root_dir = deploy_config.get("root_dir") or "."
    output_dir = deploy_config.get("output_dir") or "."
    install_cmd = deploy_config.get("install_cmd") or ""
    build_cmd = deploy_config.get("build_cmd") or ""
    run_cmd = deploy_config.get("run_cmd") or ""

    lines = [
        f"FROM {base_image} AS build",
        "WORKDIR /app",
        f"COPY {root_dir} .",
    ]
    if install_cmd:
        lines.append(f"RUN {install_cmd}")
    if build_cmd:
        lines.append(f"RUN {build_cmd}")

    second_stage = base_image if run_cmd else "nginx:alpine"
    lines.append(f"FROM {second_stage}")
    lines.append("WORKDIR /app")
    if output_dir and output_dir != ".":
        lines.append(f"COPY --from=build /app/{output_dir} .")
    else:
        lines.append("COPY --from=build /app .")
    if run_cmd:
        lines.append(f"CMD {run_cmd}")

    return "\n".join(lines) + "\n"


def _job_name(build_job_id: str) -> str:
    return f"kaniko-{build_job_id[:24]}"


def _create_kaniko_job(
    job_name: str,
    repo_url: str,
    commit_sha: str,
    image_tag: str,
    dockerfile_b64: str,
) -> None:
    batch_v1 = client.BatchV1Api()

    clone_cmd = f"git clone --depth 1 {repo_url} /workspace && cd /workspace && git checkout {commit_sha}"
    write_cmd = 'echo "$DOCKERFILE_B64" | base64 -d > /workspace/Dockerfile.generated'

    job = client.V1Job(
        metadata=client.V1ObjectMeta(name=job_name, namespace=NAMESPACE),
        spec=client.V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=JOB_TTL_AFTER_FINISHED,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "kaniko-build"}),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    init_containers=[
                        client.V1Container(
                            name="git-clone",
                            image="alpine/git:latest",
                            command=["sh", "-c", clone_cmd],
                            volume_mounts=[
                                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                            ],
                        ),
                        client.V1Container(
                            name="write-dockerfile",
                            image="busybox:latest",
                            command=["sh", "-c", write_cmd],
                            env=[client.V1EnvVar(name="DOCKERFILE_B64", value=dockerfile_b64)],
                            volume_mounts=[
                                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                            ],
                        ),
                    ],
                    containers=[
                        client.V1Container(
                            name="kaniko",
                            image="gcr.io/kaniko-project/executor:latest",
                            args=[
                                "--context=/workspace",
                                "--dockerfile=/workspace/Dockerfile.generated",
                                f"--destination={image_tag}",
                                "--cache=false",
                            ],
                            volume_mounts=[
                                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                                client.V1VolumeMount(name="docker-config", mount_path="/kaniko/.docker"),
                            ],
                        ),
                    ],
                    volumes=[
                        client.V1Volume(
                            name="workspace",
                            empty_dir=client.V1EmptyDirVolumeSource(),
                        ),
                        client.V1Volume(
                            name="docker-config",
                            secret=client.V1SecretVolumeSource(
                                secret_name="registry-credentials",
                                items=[client.V1KeyToPath(key=".dockerconfigjson", path="config.json")],
                            ),
                        ),
                    ],
                ),
            ),
        ),
    )

    batch_v1.create_namespaced_job(namespace=NAMESPACE, body=job)


def _wait_for_job(job_name: str) -> bool:
    batch_v1 = client.BatchV1Api()
    deadline = time.time() + JOB_TIMEOUT
    while time.time() < deadline:
        job = batch_v1.read_namespaced_job(name=job_name, namespace=NAMESPACE)
        if job.status.succeeded:
            return True
        if job.status.failed:
            return False
        time.sleep(5)
    raise TimeoutError(f"Kaniko job {job_name} timed out after {JOB_TIMEOUT}s")


@celery.task(name="src.workers.build.run_build")
def run_build(
    deployment_run_id: str,
    build_job_id: str,
    repo_url: str,
    commit_sha: str,
    deploy_config: dict,
    env_vars: list[dict],
    project_name: str,
):
    try:
        _callback(f"/internal/jobs/{build_job_id}/status", status="running")
        _load_k8s()

        dockerfile = _generate_dockerfile(deploy_config)
        dockerfile_b64 = base64.b64encode(dockerfile.encode()).decode()
        image_tag = f"{settings.registry.url}/{project_name}:{commit_sha[:12]}"
        job_name = _job_name(build_job_id)

        _create_kaniko_job(job_name, repo_url, commit_sha, image_tag, dockerfile_b64)

        if not _wait_for_job(job_name):
            raise RuntimeError(f"Kaniko job {job_name} failed")

        _callback(f"/internal/jobs/{build_job_id}/status", status="success")
        httpx.post(
            f"{settings.server.base_url}/internal/deployments/{deployment_run_id}/artifact",
            json={"image": image_tag},
        ).raise_for_status()

    except Exception as exc:
        logger.exception("Build failed for run %s", deployment_run_id)
        _callback(f"/internal/jobs/{build_job_id}/status", status="failed", error=str(exc))
        raise
