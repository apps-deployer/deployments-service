"""Shared fixtures for deployments-service tests."""
import uuid
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.grpc_client import DeployConfig, Env, Project
from src.models import DeploymentRun, Job, Artifact
from src.schemas import JobType, RunStatus, TriggerType


JWT_SECRET = "test-jwt-secret"
USER_ID = str(uuid.uuid4())


def make_jwt(user_id: str = USER_ID, secret: str = JWT_SECRET) -> str:
    import jwt
    from datetime import timedelta
    payload = {
        "sub": user_id,
        "github_login": "testuser",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def make_run(
    project_id: uuid.UUID | None = None,
    env_id: uuid.UUID | None = None,
    status: RunStatus = RunStatus.PENDING,
    jobs: list | None = None,
) -> DeploymentRun:
    run = MagicMock(spec=DeploymentRun)
    run.id = uuid.uuid4()
    run.project_id = project_id or uuid.uuid4()
    run.env_id = env_id or uuid.uuid4()
    run.status = status
    run.trigger_type = TriggerType.MANUAL
    run.commit_sha = "abc1234567890"
    run.commit_message = "test commit"
    run.started_at = None
    run.finished_at = None
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    run.jobs = jobs or []
    run.artifact = None
    return run


def make_job(
    run_id: uuid.UUID | None = None,
    job_type: JobType = JobType.BUILD,
    status: RunStatus = RunStatus.PENDING,
) -> Job:
    job = MagicMock(spec=Job)
    job.id = uuid.uuid4()
    job.deployment_run_id = run_id or uuid.uuid4()
    job.type = job_type
    job.status = status
    job.started_at = None
    job.finished_at = None
    job.error = None
    job.created_at = datetime.now(UTC)
    return job


@pytest.fixture
def mock_grpc():
    grpc = MagicMock()
    grpc.with_token = MagicMock(return_value=grpc)
    grpc.get_project = AsyncMock(return_value=Project(
        id=str(uuid.uuid4()), name="test-project",
        repo_url="https://github.com/test/repo", owner_id=USER_ID,
    ))
    grpc.get_env = AsyncMock(return_value=Env(
        id=str(uuid.uuid4()), name="production", project_id=str(uuid.uuid4()),
        target_branch="main",
    ))
    grpc.resolve_deploy_config = AsyncMock(return_value=DeployConfig(
        id=str(uuid.uuid4()), project_id=str(uuid.uuid4()),
        root_dir=".", output_dir="dist", base_image="node:20-alpine",
        install_cmd="npm install", build_cmd="npm run build", run_cmd="node dist/index.js",
    ))
    grpc.resolve_vars = AsyncMock(return_value=[])
    return grpc


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    run = make_run()
    build_job = make_job(run_id=run.id, job_type=JobType.BUILD)
    deploy_job = make_job(run_id=run.id, job_type=JobType.DEPLOY)
    run.jobs = [build_job, deploy_job]

    repo.create_run = AsyncMock(return_value=run)
    repo.get_run = AsyncMock(return_value=run)
    repo.list_runs = AsyncMock(return_value=([], 0))
    repo.update_run_status = AsyncMock(return_value=run)
    repo.get_job = AsyncMock(return_value=build_job)
    repo.get_job_by_run_and_type = AsyncMock(return_value=build_job)
    repo.update_job_status = AsyncMock(return_value=build_job)
    repo.create_artifact = AsyncMock(return_value=MagicMock(spec=Artifact))
    repo.mark_stale_jobs = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_session(mock_repo):
    session = AsyncMock()
    session.commit = AsyncMock()
    return session
