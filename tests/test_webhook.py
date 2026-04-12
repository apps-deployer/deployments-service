"""Tests for GitHub push webhook handler."""
import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.grpc_client import DeployConfig, Env
from tests.conftest import JWT_SECRET, make_run


WEBHOOK_SECRET = "test-webhook-secret"


def make_signature(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def push_payload(
    repo_url: str = "https://github.com/test/repo.git",
    branch: str = "main",
    commit_sha: str = "abc1234567890",
    commit_message: str = "fix: something",
) -> dict:
    return {
        "ref": f"refs/heads/{branch}",
        "repository": {"clone_url": repo_url},
        "head_commit": {"id": commit_sha, "message": commit_message},
    }


def _make_settings(webhook_secret: str = WEBHOOK_SECRET):
    settings = MagicMock()
    settings.auth.jwt_secret = JWT_SECRET
    settings.grpc.projects_service_addr = "localhost:50051"
    settings.server.frontend_url = "http://localhost:5173"
    settings.server.base_url = "http://localhost:8000"
    settings.github.webhook_secret = webhook_secret
    settings.db.url = "postgresql+asyncpg://postgres:postgres@localhost:5433/deployments_db"
    settings.redis.url = "redis://localhost:6379/0"
    settings.registry.url = "registry.localhost:5000"
    return settings


@pytest.fixture
def app_with_webhook_secret():
    with patch("src.config.load_settings") as mock_settings:
        mock_settings.return_value = _make_settings()
        from src.main import app as fastapi_app
        return fastapi_app


@pytest.fixture
async def client(app_with_webhook_secret):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_webhook_secret), base_url="http://test"
    ) as ac:
        yield ac


# ── Signature verification ────────────────────────────────────────────────────

async def test_valid_signature_accepted(client):
    """A webhook with correct HMAC-SHA256 signature passes verification."""
    payload = push_payload()
    body = json.dumps(payload).encode()

    env = Env(id=str(uuid.uuid4()), name="production", project_id=str(uuid.uuid4()),
               target_branch="main", domain_name="")

    with patch("src.main.grpc_client") as mock_grpc, \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.main.settings", _make_settings()), \
         patch("src.services.deployment.run_build") as mock_build:

        mock_grpc.with_token = MagicMock(return_value=mock_grpc)
        mock_grpc.get_env_by_git = AsyncMock(return_value=env)
        mock_grpc.get_project = AsyncMock(return_value=MagicMock(
            name="test", repo_url="https://github.com/test/repo.git"
        ))
        mock_grpc.get_env = AsyncMock(return_value=env)
        mock_grpc.resolve_deploy_config = AsyncMock(return_value=DeployConfig(
            id=str(uuid.uuid4()), project_id=str(uuid.uuid4()),
            root_dir=".", output_dir="dist", base_image="node:20-alpine",
            install_cmd="npm install", build_cmd="npm run build", run_cmd="node dist/index.js",
        ))
        mock_grpc.resolve_vars = AsyncMock(return_value=[])
        mock_build.apply_async = MagicMock()

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session

        run = make_run()

        with patch("src.services.deployment.DeploymentRepository") as MockRepo:
            instance = MagicMock()
            instance.create_run = AsyncMock(return_value=run)
            instance.get_run = AsyncMock(return_value=run)
            instance.update_run_status = AsyncMock(return_value=run)
            instance.get_job_by_run_and_type = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
            MockRepo.return_value = instance

            resp = await client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": make_signature(body),
                    "X-GitHub-Event": "push",
                },
            )

    assert resp.status_code == 201


async def test_invalid_signature_rejected(client):
    """A webhook with wrong HMAC signature is rejected."""
    payload = push_payload()
    body = json.dumps(payload).encode()

    with patch("src.main.settings", _make_settings()):
        resp = await client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=badbadbad",
                "X-GitHub-Event": "push",
            },
        )

    assert resp.status_code == 401


async def test_wrong_secret_rejected(client):
    """A webhook signed with the wrong secret is rejected."""
    payload = push_payload()
    body = json.dumps(payload).encode()
    wrong_sig = make_signature(body, secret="wrong-secret")

    with patch("src.main.settings", _make_settings()):
        resp = await client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": wrong_sig,
            },
        )

    assert resp.status_code == 401


# ── Non-push events ───────────────────────────────────────────────────────────

async def test_tag_push_is_ignored(client):
    """Pushes to tags (refs/tags/...) are silently ignored."""
    payload = {
        "ref": "refs/tags/v1.0.0",
        "repository": {"clone_url": "https://github.com/test/repo.git"},
        "head_commit": {"id": "abc123", "message": "release"},
    }
    body = json.dumps(payload).encode()

    with patch("src.main.settings", _make_settings()):
        resp = await client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": make_signature(body),
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── No matching environment ───────────────────────────────────────────────────

async def test_push_no_matching_env_is_ignored(client):
    """Push to branch with no matching environment returns 200 ignored."""
    payload = push_payload(branch="feature/xyz")
    body = json.dumps(payload).encode()

    with patch("src.main.grpc_client") as mock_grpc, \
         patch("src.main.session_factory") as mock_factory, \
         patch("src.main.settings", _make_settings()):

        mock_grpc.with_token = MagicMock(return_value=mock_grpc)
        mock_grpc.get_env_by_git = AsyncMock(side_effect=Exception("not found"))

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session

        resp = await client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": make_signature(body),
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
