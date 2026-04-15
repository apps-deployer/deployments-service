import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DeploymentRun(Base):
    __tablename__ = "deployment_runs"
    __table_args__ = {"schema": "deployment"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    env_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(nullable=False)
    trigger_type: Mapped[str] = mapped_column(nullable=False)
    commit_sha: Mapped[str | None]
    commit_message: Mapped[str | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    jobs: Mapped[list["Job"]] = relationship(back_populates="deployment_run", cascade="all, delete-orphan")
    artifact: Mapped["Artifact | None"] = relationship(back_populates="deployment_run", cascade="all, delete-orphan", uselist=False)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("deployment_run_id", "type"),
        {"schema": "deployment"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    deployment_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment.deployment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    deployment_run: Mapped["DeploymentRun"] = relationship(back_populates="jobs")


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("deployment_run_id"),
        {"schema": "deployment"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    deployment_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployment.deployment_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image: Mapped[str] = mapped_column(nullable=False)
    url: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    deployment_run: Mapped["DeploymentRun"] = relationship(back_populates="artifact")
