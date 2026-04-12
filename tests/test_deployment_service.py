"""Unit tests for DeploymentService."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas import JobType, RunStatus, TriggerType
from src.services.deployment import DeploymentService, NotFoundError
from tests.conftest import make_job, make_run, USER_ID


@pytest.fixture
def svc(mock_session, mock_grpc, mock_repo):
    service = DeploymentService(session=mock_session, grpc_client=mock_grpc)
    service.repo = mock_repo
    return service


# ── create_deployment ─────────────────────────────────────────────────────────

async def test_create_deployment_calls_grpc_and_dispatches_build(svc, mock_grpc, mock_repo):
    project_id = uuid.uuid4()
    env_id = uuid.uuid4()

    with patch("src.services.deployment.run_build") as mock_build, \
         patch("src.services.deployment._resolve_head", return_value="abc123"):
        mock_build.apply_async = MagicMock()
        await svc.create_deployment(
            project_id=project_id,
            env_id=env_id,
            trigger_type=TriggerType.MANUAL,
            commit_sha="abc123",
        )

    mock_grpc.get_project.assert_called_once_with(str(project_id))
    mock_grpc.get_env.assert_called_once_with(str(env_id))
    mock_grpc.resolve_deploy_config.assert_called_once()
    mock_grpc.resolve_vars.assert_called_once()
    mock_repo.create_run.assert_called_once()
    mock_build.apply_async.assert_called_once()


async def test_create_deployment_resolves_head_when_no_sha(svc, mock_repo):
    with patch("src.services.deployment.run_build") as mock_build, \
         patch("src.services.deployment._resolve_head", return_value="deadbeef") as resolve:
        mock_build.apply_async = MagicMock()
        await svc.create_deployment(
            project_id=uuid.uuid4(),
            env_id=uuid.uuid4(),
            trigger_type=TriggerType.WEBHOOK,
            commit_sha=None,
        )

    resolve.assert_called_once()


# ── get_deployment ────────────────────────────────────────────────────────────

async def test_get_deployment_returns_run(svc, mock_repo):
    run_id = uuid.uuid4()
    result = await svc.get_deployment(run_id)
    mock_repo.get_run.assert_called_once_with(run_id)
    assert result is not None


async def test_get_deployment_raises_not_found(svc, mock_repo):
    mock_repo.get_run = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await svc.get_deployment(uuid.uuid4())


# ── list_deployments ──────────────────────────────────────────────────────────

async def test_list_deployments_returns_empty(svc, mock_repo):
    mock_repo.list_runs = AsyncMock(return_value=([], 0))
    runs, total = await svc.list_deployments()
    assert runs == []
    assert total == 0


async def test_list_deployments_passes_filters(svc, mock_repo):
    project_id = uuid.uuid4()
    env_id = uuid.uuid4()
    await svc.list_deployments(project_id=project_id, env_id=env_id, limit=5, offset=10)
    mock_repo.list_runs.assert_called_once_with(project_id, env_id, 5, 10)


# ── update_job_status ─────────────────────────────────────────────────────────

async def test_update_job_status_failed_marks_run_failed(svc, mock_repo):
    job = make_job(job_type=JobType.BUILD, status=RunStatus.RUNNING)
    mock_repo.get_job = AsyncMock(return_value=job)

    await svc.update_job_status(job.id, RunStatus.FAILED, error="build error")

    mock_repo.update_job_status.assert_called_once_with(job.id, RunStatus.FAILED, "build error")
    mock_repo.update_run_status.assert_called_once()
    _, call_status = mock_repo.update_run_status.call_args.args
    assert call_status == RunStatus.FAILED


async def test_update_job_status_build_success_dispatches_deploy(svc, mock_repo):
    job = make_job(job_type=JobType.BUILD, status=RunStatus.RUNNING)
    mock_repo.get_job = AsyncMock(return_value=job)

    run = make_run()
    run.artifact = MagicMock(image="registry/test:abc123")
    mock_repo.get_run = AsyncMock(return_value=run)
    mock_repo.get_job_by_run_and_type = AsyncMock(return_value=make_job(job_type=JobType.DEPLOY))

    with patch("src.services.deployment.run_deploy") as mock_deploy:
        mock_deploy.apply_async = MagicMock()
        await svc.update_job_status(job.id, RunStatus.SUCCESS)

    mock_deploy.apply_async.assert_called_once()


async def test_update_job_status_deploy_success_marks_run_success(svc, mock_repo):
    job = make_job(job_type=JobType.DEPLOY, status=RunStatus.RUNNING)
    mock_repo.get_job = AsyncMock(return_value=job)

    await svc.update_job_status(job.id, RunStatus.SUCCESS)

    # update_run_status is called with SUCCESS
    calls = mock_repo.update_run_status.call_args_list
    statuses = [c.args[1] for c in calls]
    assert RunStatus.SUCCESS in statuses


async def test_update_job_status_not_found_raises(svc, mock_repo):
    mock_repo.get_job = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await svc.update_job_status(uuid.uuid4(), RunStatus.FAILED)


# ── create_artifact ───────────────────────────────────────────────────────────

async def test_create_artifact_success(svc, mock_repo):
    run_id = uuid.uuid4()
    await svc.create_artifact(run_id, "registry/img:sha")
    mock_repo.create_artifact.assert_called_once_with(run_id, "registry/img:sha")


async def test_create_artifact_run_not_found_raises(svc, mock_repo):
    mock_repo.get_run = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await svc.create_artifact(uuid.uuid4(), "registry/img:sha")
