import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth import CurrentUser, get_current_user
from src.schemas import (
    CreateArtifactRequest,
    CreateDeploymentRequest,
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
    _user: dict = Depends(get_current_user),
    project_id: uuid.UUID | None = Query(None),
    env_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    factory, grpc = _get_service()
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        runs, total = await svc.list_deployments(project_id, env_id, limit, offset)
        return DeploymentRunListResponse(
            items=[DeploymentRunResponse.model_validate(r) for r in runs],
            total=total,
        )


@router.get("/{run_id}", response_model=DeploymentRunResponse)
async def get_deployment(run_id: uuid.UUID, _user: dict = Depends(get_current_user)):
    factory, grpc = _get_service()
    async with factory() as session:
        svc = DeploymentService(session, grpc)
        try:
            run = await svc.get_deployment(run_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="Deployment run not found")
        return DeploymentRunResponse.model_validate(run)


# --- Internal endpoints (worker callbacks) ---


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
