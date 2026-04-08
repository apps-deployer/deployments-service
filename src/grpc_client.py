import sys
from dataclasses import dataclass
from pathlib import Path

# generated stubs use bare `from projects.v1 import ...` imports
sys.path.insert(0, str(Path(__file__).resolve().parent / "generated"))

import grpc
from projects.v1 import projects_pb2, projects_pb2_grpc
from projects.v1 import envs_pb2, envs_pb2_grpc
from projects.v1 import deploy_configs_pb2, deploy_configs_pb2_grpc
from projects.v1 import vars_pb2, vars_pb2_grpc


@dataclass
class Project:
    id: str
    name: str
    repo_url: str
    owner_id: str


@dataclass
class Env:
    id: str
    name: str
    project_id: str
    target_branch: str
    domain_name: str


@dataclass
class DeployConfig:
    id: str
    project_id: str
    root_dir: str
    output_dir: str
    base_image: str
    install_cmd: str
    build_cmd: str
    run_cmd: str


@dataclass
class ResolvedVar:
    id: str
    key: str
    value: bytes


class ProjectsGrpcClient:
    def __init__(self, addr: str):
        self._channel = grpc.aio.insecure_channel(addr)
        self._projects = projects_pb2_grpc.ProjectServiceStub(self._channel)
        self._envs = envs_pb2_grpc.EnvServiceStub(self._channel)
        self._deploy_configs = deploy_configs_pb2_grpc.DeployConfigServiceStub(self._channel)
        self._vars = vars_pb2_grpc.VarServiceStub(self._channel)
        self._token: str | None = None

    def with_token(self, token: str | None) -> "ProjectsGrpcClient":
        """Return self with token set for subsequent calls."""
        self._token = token
        return self

    def _metadata(self) -> list[tuple[str, str]] | None:
        if self._token:
            return [("authorization", f"Bearer {self._token}")]
        return None

    async def close(self):
        await self._channel.close()

    async def get_project(self, project_id: str) -> Project:
        resp = await self._projects.GetProject(
            projects_pb2.GetProjectRequest(id=project_id),
            metadata=self._metadata(),
        )
        return Project(
            id=resp.id,
            name=resp.name,
            repo_url=resp.repo_url,
            owner_id=resp.owner_id,
        )

    async def get_env(self, env_id: str) -> Env:
        resp = await self._envs.GetEnv(
            envs_pb2.GetEnvRequest(id=env_id),
            metadata=self._metadata(),
        )
        return Env(
            id=resp.id,
            name=resp.name,
            project_id=resp.project_id,
            target_branch=resp.target_branch,
            domain_name=resp.domain_name,
        )

    async def get_env_by_git(self, repo_url: str, target_branch: str) -> Env:
        resp = await self._envs.GetEnvByGit(
            envs_pb2.GetEnvByGitRequest(repo_url=repo_url, target_branch=target_branch),
            metadata=self._metadata(),
        )
        return Env(
            id=resp.id,
            name=resp.name,
            project_id=resp.project_id,
            target_branch=resp.target_branch,
            domain_name=resp.domain_name,
        )

    async def resolve_deploy_config(self, project_id: str) -> DeployConfig:
        resp = await self._deploy_configs.ResolveDeployConfig(
            deploy_configs_pb2.GetDeployConfigRequest(project_id=project_id),
            metadata=self._metadata(),
        )
        return DeployConfig(
            id=resp.id,
            project_id=resp.project_id,
            root_dir=resp.root_dir,
            output_dir=resp.output_dir,
            base_image=resp.base_image,
            install_cmd=resp.install_cmd,
            build_cmd=resp.build_cmd,
            run_cmd=resp.run_cmd,
        )

    async def resolve_vars(self, env_id: str) -> list[ResolvedVar]:
        resp = await self._vars.ResolveVars(
            vars_pb2.ResolveVarsRequest(env_id=env_id),
            metadata=self._metadata(),
        )
        return [
            ResolvedVar(id=v.id, key=v.key, value=v.value)
            for v in resp.vars
        ]
