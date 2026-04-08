import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TriggerType(StrEnum):
    MANUAL = "manual"
    WEBHOOK = "webhook"


class JobType(StrEnum):
    BUILD = "build"
    DEPLOY = "deploy"


# --- Requests ---


class CreateDeploymentRequest(BaseModel):
    project_id: uuid.UUID
    env_id: uuid.UUID
    commit_sha: str | None = None


# --- Responses ---


class ArtifactResponse(BaseModel):
    id: uuid.UUID
    image: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: uuid.UUID
    type: JobType
    status: RunStatus
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DeploymentRunResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    env_id: uuid.UUID
    status: RunStatus
    trigger_type: TriggerType
    commit_sha: str | None
    commit_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    jobs: list[JobResponse] = []
    artifact: ArtifactResponse | None = None

    model_config = {"from_attributes": True}


class DeploymentRunListResponse(BaseModel):
    items: list[DeploymentRunResponse]
    total: int


# --- Internal (worker callbacks) ---


class UpdateJobStatusRequest(BaseModel):
    status: RunStatus
    error: str | None = None


class CreateArtifactRequest(BaseModel):
    image: str
