import logging
import subprocess
import tempfile
from pathlib import Path

import httpx

from src.workers.celery_app import celery, settings

logger = logging.getLogger(__name__)


def _callback(path: str, **json_body):
    url = f"{settings.server.base_url}{path}"
    resp = httpx.put(url, json=json_body)
    resp.raise_for_status()


def _clone_repo(repo_url: str, commit_sha: str, dest: Path):
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(dest)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", commit_sha],
        cwd=str(dest),
        check=True,
        capture_output=True,
    )


def _generate_dockerfile(deploy_config: dict, dest: Path):
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

    lines.append(f"FROM {base_image}")
    lines.append("WORKDIR /app")
    if output_dir and output_dir != ".":
        lines.append(f"COPY --from=build /app/{output_dir} .")
    else:
        lines.append("COPY --from=build /app .")
    if run_cmd:
        lines.append(f"CMD {run_cmd}")

    (dest / "Dockerfile.generated").write_text("\n".join(lines) + "\n")


def _build_and_push(image_tag: str, context: Path):
    dockerfile = context / "Dockerfile.generated"
    subprocess.run(
        ["docker", "build", "-t", image_tag, "-f", str(dockerfile), str(context)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["docker", "push", image_tag],
        check=True,
        capture_output=True,
    )


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
    _callback(f"/internal/jobs/{build_job_id}/status", status="running")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "repo"

            _clone_repo(repo_url, commit_sha, dest)
            _generate_dockerfile(deploy_config, dest)

            image_tag = f"{settings.registry.url}/{project_name}:{commit_sha[:12]}"
            _build_and_push(image_tag, dest)

        _callback(f"/internal/jobs/{build_job_id}/status", status="success")

        url = f"{settings.server.base_url}/internal/deployments/{deployment_run_id}/artifact"
        httpx.post(url, json={"image": image_tag}).raise_for_status()

    except Exception as exc:
        logger.exception("Build failed for run %s", deployment_run_id)
        _callback(
            f"/internal/jobs/{build_job_id}/status",
            status="failed",
            error=str(exc),
        )
        raise
