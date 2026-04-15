import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


# --- Projects gateway schemas ---


class ProjectResponse(BaseModel):
    id: str
    name: str
    repo_url: str
    owner_id: str


class ProjectsListResponse(BaseModel):
    items: list[ProjectResponse]


class CreateProjectRequest(BaseModel):
    name: str
    repo_url: str
    framework_id: str = ""


class UpdateProjectRequest(BaseModel):
    name: str
    repo_url: str


class EnvResponse(BaseModel):
    id: str
    name: str
    project_id: str
    target_branch: str
    domain_name: str


class EnvsListResponse(BaseModel):
    items: list[EnvResponse]


class CreateEnvRequest(BaseModel):
    name: str
    target_branch: str
    domain_name: str = ""


class UpdateEnvRequest(BaseModel):
    name: str
    target_branch: str
    domain_name: str = ""


class VarResponse(BaseModel):
    id: str
    key: str


class VarsListResponse(BaseModel):
    items: list[VarResponse]


class CreateVarRequest(BaseModel):
    key: str
    value: str


class UpdateVarRequest(BaseModel):
    value: str


class DeployConfigResponse(BaseModel):
    id: str
    project_id: str
    framework_id: str
    root_dir_override: str
    output_dir_override: str
    base_image_override: str
    install_cmd_override: str
    build_cmd_override: str
    run_cmd_override: str


class UpdateDeployConfigRequest(BaseModel):
    framework_id: str = ""
    root_dir_override: str = ""
    output_dir_override: str = ""
    base_image_override: str = ""
    install_cmd_override: str = ""
    build_cmd_override: str = ""
    run_cmd_override: str = ""


class FrameworkResponse(BaseModel):
    id: str
    name: str
    root_dir: str
    output_dir: str
    base_image: str
    install_cmd: str
    build_cmd: str
    run_cmd: str


class FrameworksListResponse(BaseModel):
    items: list[FrameworkResponse]


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
    url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateArtifactRequest(BaseModel):
    url: str


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
