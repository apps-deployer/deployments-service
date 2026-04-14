import dataclasses
import subprocess
import uuid
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from src.grpc_client import ProjectsGrpcClient
from src.repositories.deployment import DeploymentRepository
from src.schemas import JobType, RunStatus, TriggerType
from src.workers.build import run_build
from src.workers.deploy import run_deploy


class DeploymentServiceError(Exception):
    pass


class NotFoundError(DeploymentServiceError):
    pass


class DeploymentService:
    def __init__(self, session: AsyncSession, grpc_client: ProjectsGrpcClient):
        self.repo = DeploymentRepository(session)
        self.grpc = grpc_client
        self.session = session

    async def create_deployment(
        self,
        project_id: uuid.UUID,
        env_id: uuid.UUID,
        trigger_type: TriggerType,
        commit_sha: str | None = None,
        commit_message: str | None = None,
    ):
        project = await self.grpc.get_project(str(project_id))
        env = await self.grpc.get_env(str(env_id))

        if commit_sha is None:
            commit_sha = _resolve_head(project.repo_url, env.target_branch)

        run = await self.repo.create_run(
            project_id=project_id,
            env_id=env_id,
            trigger_type=trigger_type,
            commit_sha=commit_sha,
            commit_message=commit_message,
        )

        deploy_config = await self.grpc.resolve_deploy_config(str(project_id))
        resolved_vars = await self.grpc.resolve_vars(str(env_id))

        await self.repo.update_run_status(
            run.id, RunStatus.RUNNING, started_at=datetime.now(UTC).replace(tzinfo=None)
        )
        await self.session.commit()

        build_job = await self.repo.get_job_by_run_and_type(run.id, JobType.BUILD)

        run_build.apply_async(
            kwargs=dict(
                deployment_run_id=str(run.id),
                build_job_id=str(build_job.id),
                repo_url=project.repo_url,
                commit_sha=commit_sha,
                deploy_config=dataclasses.asdict(deploy_config),
                env_vars=[{"key": v.key, "value": v.value.decode()} for v in resolved_vars],
                project_name=project.name,
            ),
            queue="build",
        )

        run = await self.repo.get_run(run.id)
        return run

    async def get_deployment(self, run_id: uuid.UUID):
        run = await self.repo.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Deployment run {run_id} not found")
        return run

    async def list_deployments(
        self,
        project_id: uuid.UUID | None = None,
        env_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ):
        return await self.repo.list_runs(project_id, env_id, limit, offset)

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: RunStatus,
        error: str | None = None,
    ):
        job = await self.repo.get_job(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")

        await self.repo.update_job_status(job_id, status, error)

        if status == RunStatus.FAILED:
            await self.repo.update_run_status(
                job.deployment_run_id,
                RunStatus.FAILED,
                finished_at=datetime.now(UTC).replace(tzinfo=None),
            )

        if job.type == JobType.BUILD and status == RunStatus.SUCCESS:
            await self._dispatch_deploy(job.deployment_run_id)

        if job.type == JobType.DEPLOY and status == RunStatus.SUCCESS:
            await self.repo.update_run_status(
                job.deployment_run_id,
                RunStatus.SUCCESS,
                finished_at=datetime.now(UTC).replace(tzinfo=None),
            )

        await self.session.commit()

    async def create_artifact(self, run_id: uuid.UUID, image: str):
        run = await self.repo.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Deployment run {run_id} not found")
        artifact = await self.repo.create_artifact(run_id, image)
        await self.session.commit()
        return artifact

    async def _dispatch_deploy(self, run_id: uuid.UUID):
        run = await self.repo.get_run(run_id)
        if run is None or run.artifact is None:
            return

        from src.auth import generate_service_token
        from src.main import settings
        grpc = self.grpc.with_token(generate_service_token(settings.auth.jwt_secret))

        project = await grpc.get_project(str(run.project_id))
        env = await grpc.get_env(str(run.env_id))
        resolved_vars = await grpc.resolve_vars(str(run.env_id))

        deploy_job = await self.repo.get_job_by_run_and_type(run_id, JobType.DEPLOY)

        run_deploy.apply_async(
            kwargs=dict(
                deployment_run_id=str(run_id),
                deploy_job_id=str(deploy_job.id),
                image=run.artifact.image,
                project_name=project.name,
                env_name=env.name,
                domain_name=env.domain_name,
                env_vars=[{"key": v.key, "value": v.value.decode()} for v in resolved_vars],
            ),
            queue="deploy",
        )


def _resolve_head(repo_url: str, branch: str) -> str:
    result = subprocess.run(
        ["git", "ls-remote", repo_url, f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=True,
    )
    line = result.stdout.strip()
    if not line:
        raise DeploymentServiceError(
            f"Branch '{branch}' not found in {repo_url}"
        )
    return line.split()[0]
