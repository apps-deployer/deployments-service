import uuid
from datetime import datetime, UTC, timedelta

from sqlalchemy import func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.models import Artifact, DeploymentRun, Job
from src.schemas import JobType, RunStatus, TriggerType


class DeploymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(
        self,
        project_id: uuid.UUID,
        env_id: uuid.UUID,
        trigger_type: TriggerType,
        commit_sha: str | None = None,
        commit_message: str | None = None,
    ) -> DeploymentRun:
        run = DeploymentRun(
            project_id=project_id,
            env_id=env_id,
            status=RunStatus.PENDING,
            trigger_type=trigger_type,
            commit_sha=commit_sha,
            commit_message=commit_message,
        )
        self.session.add(run)
        await self.session.flush()

        for job_type in (JobType.BUILD, JobType.DEPLOY):
            job = Job(
                deployment_run_id=run.id,
                type=job_type,
                status=RunStatus.PENDING,
            )
            self.session.add(job)

        await self.session.flush()
        return run

    async def get_run(self, run_id: uuid.UUID) -> DeploymentRun | None:
        stmt = (
            select(DeploymentRun)
            .where(DeploymentRun.id == run_id)
            .options(joinedload(DeploymentRun.jobs), joinedload(DeploymentRun.artifact))
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_runs(
        self,
        project_id: uuid.UUID | None = None,
        env_id: uuid.UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[DeploymentRun], int]:
        base = select(DeploymentRun)
        count_base = select(func.count(DeploymentRun.id))

        if project_id is not None:
            base = base.where(DeploymentRun.project_id == project_id)
            count_base = count_base.where(DeploymentRun.project_id == project_id)
        if env_id is not None:
            base = base.where(DeploymentRun.env_id == env_id)
            count_base = count_base.where(DeploymentRun.env_id == env_id)

        total = (await self.session.execute(count_base)).scalar_one()

        stmt = (
            base
            .options(joinedload(DeploymentRun.jobs), joinedload(DeploymentRun.artifact))
            .order_by(DeploymentRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        runs = list(result.unique().scalars().all())
        return runs, total

    async def update_run_status(
        self,
        run_id: uuid.UUID,
        status: RunStatus,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> DeploymentRun | None:
        run = await self.session.get(DeploymentRun, run_id)
        if run is None:
            return None
        run.status = status
        if started_at:
            run.started_at = started_at
        if finished_at:
            run.finished_at = finished_at
        await self.session.flush()
        return run

    async def get_job(self, job_id: uuid.UUID) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_job_by_run_and_type(
        self, run_id: uuid.UUID, job_type: JobType
    ) -> Job | None:
        stmt = select(Job).where(Job.deployment_run_id == run_id, Job.type == job_type)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: RunStatus,
        error: str | None = None,
    ) -> Job | None:
        job = await self.session.get(Job, job_id)
        if job is None:
            return None
        job.status = status
        now = datetime.now(UTC).replace(tzinfo=None)
        if status == RunStatus.RUNNING:
            job.started_at = now
        elif status in (RunStatus.SUCCESS, RunStatus.FAILED):
            job.finished_at = now
            if error:
                job.error = error
        await self.session.flush()
        return job

    async def mark_stale_jobs(
        self,
        pending_timeout_minutes: int = 5,
        running_timeout_minutes: int = 60,
    ) -> int:
        """Mark stale PENDING/RUNNING jobs as FAILED. Returns count of affected jobs."""
        now = datetime.now(UTC).replace(tzinfo=None)
        pending_cutoff = now - timedelta(minutes=pending_timeout_minutes)
        running_cutoff = now - timedelta(minutes=running_timeout_minutes)

        stmt = select(Job).where(
            or_(
                and_(Job.status == RunStatus.PENDING, Job.created_at < pending_cutoff),
                and_(Job.status == RunStatus.RUNNING, Job.started_at < running_cutoff),
            )
        )
        result = await self.session.execute(stmt)
        stale_jobs = list(result.scalars().all())

        affected_run_ids: set[uuid.UUID] = set()
        for job in stale_jobs:
            job.status = RunStatus.FAILED
            job.error = "Timed out: worker crashed or task was never dispatched"
            job.finished_at = now
            affected_run_ids.add(job.deployment_run_id)

        for run_id in affected_run_ids:
            run = await self.session.get(DeploymentRun, run_id)
            if run and run.status in (RunStatus.PENDING, RunStatus.RUNNING):
                run.status = RunStatus.FAILED
                run.finished_at = now

        await self.session.flush()
        return len(stale_jobs)

    async def create_artifact(
        self, run_id: uuid.UUID, image: str
    ) -> Artifact:
        artifact = Artifact(deployment_run_id=run_id, image=image)
        self.session.add(artifact)
        await self.session.flush()
        return artifact

    async def update_artifact_url(self, run_id: uuid.UUID, url: str) -> Artifact | None:
        stmt = select(Artifact).where(Artifact.deployment_run_id == run_id)
        result = await self.session.execute(stmt)
        artifact = result.scalar_one_or_none()
        if artifact is None:
            return None
        artifact.url = url
        await self.session.flush()
        return artifact
