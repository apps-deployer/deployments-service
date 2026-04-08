CREATE SCHEMA IF NOT EXISTS deployment;
CREATE SCHEMA IF NOT EXISTS utils;

CREATE TABLE IF NOT EXISTS deployment.deployment_runs (
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
);

CREATE INDEX idx_deployment_runs_project_id ON deployment.deployment_runs(project_id);
CREATE INDEX idx_deployment_runs_env_id ON deployment.deployment_runs(env_id);

CREATE TABLE IF NOT EXISTS deployment.jobs (
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
);

CREATE INDEX idx_jobs_run_id ON deployment.jobs(deployment_run_id);

CREATE TABLE IF NOT EXISTS deployment.artifacts (
    id UUID PRIMARY KEY DEFAULT uuidv7(),

    deployment_run_id UUID NOT NULL REFERENCES deployment.deployment_runs(id) ON DELETE CASCADE,

    image VARCHAR(512) NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE(deployment_run_id)
);

CREATE INDEX idx_artifacts_run_id ON deployment.artifacts(deployment_run_id);

CREATE OR REPLACE FUNCTION utils.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN 
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_deployment_runs
BEFORE UPDATE ON deployment.deployment_runs
FOR EACH ROW
EXECUTE FUNCTION utils.update_updated_at();

CREATE TRIGGER trg_update_jobs
BEFORE UPDATE ON deployment.jobs
FOR EACH ROW
EXECUTE FUNCTION utils.update_updated_at();