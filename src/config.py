import os
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DbConfig(BaseModel):
    host: str = "localhost"
    port: int = 5433
    user: str = "postgres"
    password: str = "postgres"
    name: str = "deployments_db"

    @property
    def url(self) -> str:
        from urllib.parse import quote
        return f"postgresql+asyncpg://{quote(self.user, safe='')}:{quote(self.password, safe='')}@{self.host}:{self.port}/{self.name}"


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"


class GrpcConfig(BaseModel):
    projects_service_addr: str = "localhost:50051"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"


class RegistryConfig(BaseModel):
    url: str = "registry.localhost:5000"


class AuthConfig(BaseModel):
    jwt_secret: str = "your_jwt_secret"


class GitHubWebhookConfig(BaseModel):
    webhook_secret: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEPLOY_", env_nested_delimiter="__")

    env: str = "local"
    db: DbConfig = DbConfig()
    redis: RedisConfig = RedisConfig()
    grpc: GrpcConfig = GrpcConfig()
    server: ServerConfig = ServerConfig()
    registry: RegistryConfig = RegistryConfig()
    auth: AuthConfig = AuthConfig()
    github: GitHubWebhookConfig = GitHubWebhookConfig()


def load_settings() -> Settings:
    config_path = os.environ.get("CONFIG_PATH")
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return Settings(**data)
    return Settings()
