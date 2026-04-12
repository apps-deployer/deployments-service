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
from projects.v1 import frameworks_pb2, frameworks_pb2_grpc


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
class DeployConfigRaw:
    id: str
    project_id: str
    framework_id: str
    root_dir_override: str
    output_dir_override: str
    base_image_override: str
    install_cmd_override: str
    build_cmd_override: str
    run_cmd_override: str


@dataclass
class Var:
    id: str
    key: str


@dataclass
class ResolvedVar:
    id: str
    key: str
    value: bytes


@dataclass
class Framework:
    id: str
    name: str
    root_dir: str
    output_dir: str
    base_image: str
    install_cmd: str
    build_cmd: str
    run_cmd: str


class ProjectsGrpcClient:
    def __init__(self, addr: str):
        self._channel = grpc.aio.insecure_channel(addr)
        self._projects = projects_pb2_grpc.ProjectServiceStub(self._channel)
        self._envs = envs_pb2_grpc.EnvServiceStub(self._channel)
        self._deploy_configs = deploy_configs_pb2_grpc.DeployConfigServiceStub(self._channel)
        self._vars = vars_pb2_grpc.VarServiceStub(self._channel)
        self._frameworks = frameworks_pb2_grpc.FrameworkServiceStub(self._channel)
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

    # --- Projects ---

    async def get_project(self, project_id: str) -> Project:
        resp = await self._projects.GetProject(
            projects_pb2.GetProjectRequest(id=project_id),
            metadata=self._metadata(),
        )
        return Project(id=resp.id, name=resp.name, repo_url=resp.repo_url, owner_id=resp.owner_id)

    async def list_projects(self, limit: int = 100, offset: int = 0) -> list[Project]:
        resp = await self._projects.ListProjects(
            projects_pb2.ListProjectsRequest(limit=limit, offset=offset),
            metadata=self._metadata(),
        )
        return [Project(id=p.id, name=p.name, repo_url=p.repo_url, owner_id=p.owner_id) for p in resp.projects]

    async def create_project(self, name: str, repo_url: str, deploy_config_template_id: str = "") -> Project:
        resp = await self._projects.CreateProject(
            projects_pb2.CreateProjectRequest(
                name=name,
                repo_url=repo_url,
                deploy_config_template_id=deploy_config_template_id,
            ),
            metadata=self._metadata(),
        )
        return Project(id=resp.id, name=resp.name, repo_url=resp.repo_url, owner_id=resp.owner_id)

    async def update_project(self, project_id: str, name: str, repo_url: str) -> None:
        await self._projects.UpdateProject(
            projects_pb2.UpdateProjectRequest(id=project_id, name=name, repo_url=repo_url),
            metadata=self._metadata(),
        )

    async def delete_project(self, project_id: str) -> None:
        await self._projects.DeleteProject(
            projects_pb2.DeleteProjectRequest(id=project_id),
            metadata=self._metadata(),
        )

    # --- Environments ---

    async def get_env(self, env_id: str) -> Env:
        resp = await self._envs.GetEnv(
            envs_pb2.GetEnvRequest(id=env_id),
            metadata=self._metadata(),
        )
        return Env(id=resp.id, name=resp.name, project_id=resp.project_id,
                   target_branch=resp.target_branch, domain_name=resp.domain_name)

    async def get_env_by_git(self, repo_url: str, target_branch: str) -> Env:
        resp = await self._envs.GetEnvByGit(
            envs_pb2.GetEnvByGitRequest(repo_url=repo_url, target_branch=target_branch),
            metadata=self._metadata(),
        )
        return Env(id=resp.id, name=resp.name, project_id=resp.project_id,
                   target_branch=resp.target_branch, domain_name=resp.domain_name)

    async def list_envs(self, project_id: str, limit: int = 100, offset: int = 0) -> list[Env]:
        resp = await self._envs.ListEnvs(
            envs_pb2.ListEnvsRequest(project_id=project_id, limit=limit, offset=offset),
            metadata=self._metadata(),
        )
        return [Env(id=e.id, name=e.name, project_id=e.project_id,
                    target_branch=e.target_branch, domain_name=e.domain_name) for e in resp.envs]

    async def create_env(self, name: str, project_id: str, target_branch: str, domain_name: str = "") -> Env:
        resp = await self._envs.CreateEnv(
            envs_pb2.CreateEnvRequest(
                name=name, project_id=project_id,
                target_branch=target_branch, domain_name=domain_name,
            ),
            metadata=self._metadata(),
        )
        return Env(id=resp.id, name=resp.name, project_id=resp.project_id,
                   target_branch=resp.target_branch, domain_name=resp.domain_name)

    async def update_env(self, env_id: str, name: str, target_branch: str, domain_name: str = "") -> None:
        await self._envs.UpdateEnv(
            envs_pb2.UpdateEnvRequest(id=env_id, name=name, target_branch=target_branch, domain_name=domain_name),
            metadata=self._metadata(),
        )

    async def delete_env(self, env_id: str) -> None:
        await self._envs.DeleteEnv(
            envs_pb2.DeleteEnvRequest(id=env_id),
            metadata=self._metadata(),
        )

    # --- Deploy Configs ---

    async def resolve_deploy_config(self, project_id: str) -> DeployConfig:
        resp = await self._deploy_configs.ResolveDeployConfig(
            deploy_configs_pb2.GetDeployConfigRequest(project_id=project_id),
            metadata=self._metadata(),
        )
        return DeployConfig(
            id=resp.id, project_id=resp.project_id,
            root_dir=resp.root_dir, output_dir=resp.output_dir,
            base_image=resp.base_image, install_cmd=resp.install_cmd,
            build_cmd=resp.build_cmd, run_cmd=resp.run_cmd,
        )

    async def get_deploy_config(self, project_id: str) -> DeployConfigRaw:
        resp = await self._deploy_configs.GetDeployConfig(
            deploy_configs_pb2.GetDeployConfigRequest(project_id=project_id),
            metadata=self._metadata(),
        )
        return DeployConfigRaw(
            id=resp.id, project_id=resp.project_id, framework_id=resp.framework_id,
            root_dir_override=resp.root_dir_override, output_dir_override=resp.output_dir_override,
            base_image_override=resp.base_image_override, install_cmd_override=resp.install_cmd_override,
            build_cmd_override=resp.build_cmd_override, run_cmd_override=resp.run_cmd_override,
        )

    async def update_deploy_config(
        self, config_id: str, framework_id: str = "",
        root_dir_override: str = "", output_dir_override: str = "",
        base_image_override: str = "", install_cmd_override: str = "",
        build_cmd_override: str = "", run_cmd_override: str = "",
    ) -> None:
        await self._deploy_configs.UpdateDeployConfig(
            deploy_configs_pb2.UpdateDeployConfigRequest(
                id=config_id, framework_id=framework_id,
                root_dir_override=root_dir_override, output_dir_override=output_dir_override,
                base_image_override=base_image_override, install_cmd_override=install_cmd_override,
                build_cmd_override=build_cmd_override, run_cmd_override=run_cmd_override,
            ),
            metadata=self._metadata(),
        )

    # --- Variables ---

    async def list_project_vars(self, project_id: str, limit: int = 100, offset: int = 0) -> list[Var]:
        resp = await self._vars.ListProjectVars(
            vars_pb2.ListProjectVarsRequest(project_id=project_id, limit=limit, offset=offset),
            metadata=self._metadata(),
        )
        return [Var(id=v.id, key=v.key) for v in resp.vars]

    async def create_project_var(self, project_id: str, key: str, value: str) -> Var:
        resp = await self._vars.CreateProjectVar(
            vars_pb2.CreateProjectVarRequest(project_id=project_id, key=key, value=value),
            metadata=self._metadata(),
        )
        return Var(id=resp.id, key=resp.key)

    async def update_project_var(self, var_id: str, value: str) -> None:
        await self._vars.UpdateProjectVar(
            vars_pb2.UpdateVarRequest(id=var_id, value=value),
            metadata=self._metadata(),
        )

    async def delete_project_var(self, var_id: str) -> None:
        await self._vars.DeleteProjectVar(
            vars_pb2.DeleteVarRequest(id=var_id),
            metadata=self._metadata(),
        )

    async def list_env_vars(self, env_id: str, limit: int = 100, offset: int = 0) -> list[Var]:
        resp = await self._vars.ListEnvVars(
            vars_pb2.ListEnvVarsRequest(env_id=env_id, limit=limit, offset=offset),
            metadata=self._metadata(),
        )
        return [Var(id=v.id, key=v.key) for v in resp.vars]

    async def create_env_var(self, env_id: str, key: str, value: str) -> Var:
        resp = await self._vars.CreateEnvVar(
            vars_pb2.CreateEnvVarRequest(env_id=env_id, key=key, value=value),
            metadata=self._metadata(),
        )
        return Var(id=resp.id, key=resp.key)

    async def update_env_var(self, var_id: str, value: str) -> None:
        await self._vars.UpdateEnvVar(
            vars_pb2.UpdateVarRequest(id=var_id, value=value),
            metadata=self._metadata(),
        )

    async def delete_env_var(self, var_id: str) -> None:
        await self._vars.DeleteEnvVar(
            vars_pb2.DeleteVarRequest(id=var_id),
            metadata=self._metadata(),
        )

    async def resolve_vars(self, env_id: str) -> list[ResolvedVar]:
        resp = await self._vars.ResolveVars(
            vars_pb2.ResolveVarsRequest(env_id=env_id),
            metadata=self._metadata(),
        )
        return [ResolvedVar(id=v.id, key=v.key, value=v.value) for v in resp.vars]

    # --- Frameworks ---

    async def list_frameworks(self, limit: int = 100, offset: int = 0) -> list[Framework]:
        resp = await self._frameworks.ListFrameworks(
            frameworks_pb2.ListFrameworksRequest(limit=limit, offset=offset),
            metadata=self._metadata(),
        )
        return [
            Framework(
                id=f.id, name=f.name, root_dir=f.root_dir, output_dir=f.output_dir,
                base_image=f.base_image, install_cmd=f.install_cmd,
                build_cmd=f.build_cmd, run_cmd=f.run_cmd,
            )
            for f in resp.frameworks
        ]
