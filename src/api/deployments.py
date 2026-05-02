import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth import CurrentUser, generate_service_token, get_current_user, require_service
from src.schemas import (
    CreateArtifactRequest,
    CreateDeploymentRequest,
    CreateInternalDeploymentRequest,
    DeploymentRunListResponse,
    DeploymentRunResponse,
    TriggerType,
    UpdateArtifactRequest,
    UpdateJobStatusRequest,
)
from src.services.deployment import DeploymentService, NotFoundError

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])
internal_router = APIRouter(prefix="/internal", tags=["internal"])


def _get_service():
    from src.main import session_factory, grpc_client
    return session_factory, grpc_client


# --- Public endpoints ---


@router.post("", response_model=DeploymentRunResponse, status_code=201)
async def create_deployment(body: CreateDeploymentRequest, user: CurrentUser = Depends(get_current_user)):
    factory, grpc = _get_service()
    grpc = grpc.with_token(user.token)
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        run = await svc.create_deployment(
            project_id=body.project_id,
            env_id=body.env_id,
            trigger_type=TriggerType.MANUAL,
            commit_sha=body.commit_sha,
        )
        return DeploymentRunResponse.model_validate(run)


@router.get("", response_model=DeploymentRunListResponse)
async def list_deployments(
    user: CurrentUser = Depends(get_current_user),
    project_id: uuid.UUID | None = Query(None),
    env_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    factory, grpc = _get_service()
    user_grpc = grpc.with_token(user.token)
    project_ids = None
    if project_id is not None:
        try:
            await user_grpc.get_project(str(project_id))
        except Exception:
            raise HTTPException(status_code=404, detail="Project not found")
    else:
        projects = await user_grpc.list_projects()
        project_ids = [uuid.UUID(p.id) for p in projects]
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        runs, total = await svc.list_deployments(project_id, env_id, limit, offset, project_ids)
        return DeploymentRunListResponse(
            items=[DeploymentRunResponse.model_validate(r) for r in runs],
            total=total,
        )


@router.get("/{run_id}", response_model=DeploymentRunResponse)
async def get_deployment(run_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)):
    factory, grpc = _get_service()
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        try:
            run = await svc.get_deployment(run_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="Deployment run not found")
        try:
            await grpc.with_token(user.token).get_project(str(run.project_id))
        except Exception:
            raise HTTPException(status_code=404, detail="Deployment run not found")
        return DeploymentRunResponse.model_validate(run)


# --- Internal endpoints (worker callbacks) ---


@internal_router.post("/deployments", response_model=DeploymentRunResponse, status_code=201)
async def create_internal_deployment(
    body: CreateInternalDeploymentRequest,
    _token: str = Depends(require_service),
):
    factory, grpc = _get_service()
    from src.main import settings
    grpc = grpc.with_token(generate_service_token(settings.auth.jwt_secret))
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        run = await svc.create_deployment(
            project_id=body.project_id,
            env_id=body.env_id,
            trigger_type=body.trigger_type,
            commit_sha=body.commit_sha,
            commit_message=body.commit_message,
        )
        return DeploymentRunResponse.model_validate(run)


@internal_router.put("/jobs/{job_id}/status", status_code=204)
async def update_job_status(job_id: uuid.UUID, body: UpdateJobStatusRequest):
    factory, grpc = _get_service()
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        try:
            await svc.update_job_status(job_id, body.status, body.error)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="Job not found")


@internal_router.post("/cleanup", status_code=200)
async def cleanup_stale_jobs():
    factory, grpc = _get_service()
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        count = await svc.cleanup_stale_jobs()
        return {"cleaned": count}


@internal_router.post(
    "/deployments/{run_id}/artifact", status_code=201
)
async def create_artifact(run_id: uuid.UUID, body: CreateArtifactRequest):
    factory, grpc = _get_service()
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        try:
            await svc.create_artifact(run_id, body.image)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="Deployment run not found")


@internal_router.patch("/deployments/{run_id}/artifact", status_code=204)
async def update_artifact_url(run_id: uuid.UUID, body: UpdateArtifactRequest):
    factory, grpc = _get_service()
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        try:
            await svc.update_artifact_url(run_id, body.url)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="Deployment run not found")
