"""API endpoint tests for /api/v1/deployments and /internal/ callbacks."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.schemas import RunStatus, TriggerType
from tests.conftest import JWT_SECRET, USER_ID, make_job, make_run


@pytest.fixture
def app():
    """FastAPI app with mocked settings."""
    with patch("src.config.load_settings") as mock_settings:
        settings = MagicMock()
        settings.auth.jwt_secret = JWT_SECRET
        settings.grpc.projects_service_addr = "localhost:50051"
        settings.server.frontend_url = "http://localhost:5173"
        settings.server.base_url = "http://localhost:8000"
        settings.github.webhook_secret = ""
        settings.db.url = "postgresql+asyncpg://postgres:postgres@localhost:5433/deployments_db"
        settings.redis.url = "redis://localhost:6379/0"
        settings.registry.url = "registry.localhost:5000"
        mock_settings.return_value = settings

        from src.main import app as fastapi_app
        return fastapi_app


@pytest.fixture
def token(app):
    from tests.conftest import make_jwt
    return make_jwt()


@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── POST /api/v1/deployments ──────────────────────────────────────────────────

async def test_create_deployment_success(client, auth_headers, mock_grpc, mock_repo):
    project_id = uuid.uuid4()
    env_id = uuid.uuid4()
    run = make_run(project_id=project_id, env_id=env_id, status=RunStatus.RUNNING)
    run.jobs = [make_job(run_id=run.id)]

    with patch("src.main.grpc_client", mock_grpc), \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.services.deployment.run_build") as mock_build:
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session
        mock_build.apply_async = MagicMock()

        with patch("src.services.deployment.DeploymentRepository") as MockRepo:
            instance = MagicMock()
            instance.create_run = AsyncMock(return_value=run)
            instance.get_run = AsyncMock(return_value=run)
            instance.update_run_status = AsyncMock(return_value=run)
            instance.get_job_by_run_and_type = AsyncMock(return_value=make_job(run_id=run.id))
            MockRepo.return_value = instance

            resp = await client.post(
                "/api/v1/deployments",
                json={"project_id": str(project_id), "env_id": str(env_id), "commit_sha": "abc1234"},
                headers=auth_headers,
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == str(project_id)
    assert body["env_id"] == str(env_id)


async def test_create_deployment_requires_auth(client):
    resp = await client.post(
        "/api/v1/deployments",
        json={"project_id": str(uuid.uuid4()), "env_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401 or resp.status_code == 422


# ── GET /api/v1/deployments ───────────────────────────────────────────────────

async def test_list_deployments_empty(client, auth_headers, mock_grpc):
    with patch("src.main.grpc_client", mock_grpc), \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.services.deployment.DeploymentRepository") as MockRepo:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session
        instance = MagicMock()
        instance.list_runs = AsyncMock(return_value=([], 0))
        MockRepo.return_value = instance

        resp = await client.get("/api/v1/deployments", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_deployments_requires_auth(client):
    resp = await client.get("/api/v1/deployments")
    assert resp.status_code == 401 or resp.status_code == 422


# ── GET /api/v1/deployments/{id} ──────────────────────────────────────────────

async def test_get_deployment_not_found(client, auth_headers, mock_grpc):
    with patch("src.main.grpc_client", mock_grpc), \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.services.deployment.DeploymentRepository") as MockRepo:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session
        instance = MagicMock()
        instance.get_run = AsyncMock(return_value=None)
        MockRepo.return_value = instance

        resp = await client.get(f"/api/v1/deployments/{uuid.uuid4()}", headers=auth_headers)

    assert resp.status_code == 404


# ── PUT /internal/jobs/{id}/status ───────────────────────────────────────────

async def test_update_job_status_success(client, mock_grpc):
    job = make_job(status=RunStatus.RUNNING)
    run = make_run()

    with patch("src.main.grpc_client", mock_grpc), \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.services.deployment.DeploymentRepository") as MockRepo:
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session
        instance = MagicMock()
        instance.get_job = AsyncMock(return_value=job)
        instance.update_job_status = AsyncMock(return_value=job)
        instance.update_run_status = AsyncMock(return_value=run)
        instance.get_run = AsyncMock(return_value=run)
        instance.get_job_by_run_and_type = AsyncMock(return_value=job)
        MockRepo.return_value = instance

        resp = await client.put(
            f"/internal/jobs/{job.id}/status",
            json={"status": "success"},
        )

    assert resp.status_code == 204


async def test_update_job_status_not_found(client, mock_grpc):
    with patch("src.main.grpc_client", mock_grpc), \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.services.deployment.DeploymentRepository") as MockRepo:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session
        instance = MagicMock()
        instance.get_job = AsyncMock(return_value=None)
        MockRepo.return_value = instance

        resp = await client.put(
            f"/internal/jobs/{uuid.uuid4()}/status",
            json={"status": "failed", "error": "timeout"},
        )

    assert resp.status_code == 404


# ── POST /internal/deployments/{id}/artifact ──────────────────────────────────

async def test_create_artifact_success(client, mock_grpc):
    run = make_run()
    artifact = MagicMock()
    artifact.id = uuid.uuid4()
    artifact.image = "registry/test:abc123"

    with patch("src.main.grpc_client", mock_grpc), \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.services.deployment.DeploymentRepository") as MockRepo:
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session
        instance = MagicMock()
        instance.get_run = AsyncMock(return_value=run)
        instance.create_artifact = AsyncMock(return_value=artifact)
        MockRepo.return_value = instance

        resp = await client.post(
            f"/internal/deployments/{run.id}/artifact",
            json={"image": "registry/test:abc123"},
        )

    assert resp.status_code == 201
