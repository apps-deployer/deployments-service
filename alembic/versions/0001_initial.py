"""Initial deployment schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS deployment")
    op.execute("CREATE SCHEMA IF NOT EXISTS utils")

    op.execute(
        """
        CREATE TABLE deployment.deployment_runs (
            id UUID PRIMARY KEY DEFAULT uuidv7(),
            project_id UUID NOT NULL,
            env_id UUID NOT NULL,
            status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')),
            trigger_type VARCHAR(32) NOT NULL CHECK (trigger_type IN ('manual', 'webhook')),
            commit_sha VARCHAR(64),
            commit_message TEXT,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_deployment_runs_project_id ON deployment.deployment_runs(project_id)")
    op.execute("CREATE INDEX idx_deployment_runs_env_id ON deployment.deployment_runs(env_id)")

    op.execute(
        """
        CREATE TABLE deployment.jobs (
            id UUID PRIMARY KEY DEFAULT uuidv7(),
            deployment_run_id UUID NOT NULL REFERENCES deployment.deployment_runs(id) ON DELETE CASCADE,
            type VARCHAR(32) NOT NULL CHECK (type IN ('build', 'deploy')),
            status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'running', 'success', 'failed')),
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            UNIQUE(deployment_run_id, type)
        )
        """
    )
    op.execute("CREATE INDEX idx_jobs_run_id ON deployment.jobs(deployment_run_id)")

    op.execute(
        """
        CREATE TABLE deployment.artifacts (
            id UUID PRIMARY KEY DEFAULT uuidv7(),
            deployment_run_id UUID NOT NULL REFERENCES deployment.deployment_runs(id) ON DELETE CASCADE,
            image VARCHAR(512) NOT NULL,
            url TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            UNIQUE(deployment_run_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_artifacts_run_id ON deployment.artifacts(deployment_run_id)")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION utils.update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_update_deployment_runs
        BEFORE UPDATE ON deployment.deployment_runs
        FOR EACH ROW
        EXECUTE FUNCTION utils.update_updated_at()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_update_jobs
        BEFORE UPDATE ON deployment.jobs
        FOR EACH ROW
        EXECUTE FUNCTION utils.update_updated_at()
        """
    )

    op.execute('GRANT USAGE ON SCHEMA deployment TO "deployments-service"')
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA deployment TO "deployments-service"')
    op.execute(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA deployment '
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "deployments-service"'
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_update_jobs ON deployment.jobs")
    op.execute("DROP TRIGGER IF EXISTS trg_update_deployment_runs ON deployment.deployment_runs")
    op.execute("DROP TABLE IF EXISTS deployment.artifacts")
    op.execute("DROP TABLE IF EXISTS deployment.jobs")
    op.execute("DROP TABLE IF EXISTS deployment.deployment_runs")
    op.execute("DROP FUNCTION IF EXISTS utils.update_updated_at()")
    op.execute("DROP SCHEMA IF EXISTS deployment")
    op.execute("DROP SCHEMA IF EXISTS utils")
