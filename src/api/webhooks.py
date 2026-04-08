import hashlib
import hmac
import uuid

from fastapi import APIRouter, HTTPException, Request

from src.auth import generate_service_token
from src.schemas import TriggerType
from src.services.deployment import DeploymentService

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _get_service():
    from src.main import session_factory, grpc_client, settings
    return session_factory, grpc_client, settings


def _verify_github_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


@router.post("/github", status_code=201)
async def github_push(request: Request):
    factory, grpc, settings = _get_service()

    if settings.github.webhook_secret:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_github_signature(body, signature, settings.github.webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()

    ref = payload.get("ref", "")
    if not ref.startswith("refs/heads/"):
        return {"status": "ignored", "reason": "not a branch push"}

    branch = ref.removeprefix("refs/heads/")
    repo_url = payload.get("repository", {}).get("clone_url", "")
    head_commit = payload.get("head_commit") or {}
    commit_sha = head_commit.get("id")
    commit_message = head_commit.get("message")

    if not repo_url or not commit_sha:
        raise HTTPException(status_code=400, detail="Missing repo URL or commit SHA")

    # Use service token for service-to-service gRPC calls
    grpc.with_token(generate_service_token(settings.auth.jwt_secret))

    async with factory() as session:
        svc = DeploymentService(session, grpc)

        try:
            env = await grpc.get_env_by_git(repo_url, branch)
        except Exception:
            return {"status": "ignored", "reason": "no matching environment"}

        run = await svc.create_deployment(
            project_id=uuid.UUID(env.project_id),
            env_id=uuid.UUID(env.id),
            trigger_type=TriggerType.WEBHOOK,
            commit_sha=commit_sha,
            commit_message=commit_message,
        )

    return {"status": "accepted", "deployment_run_id": str(run.id)}
