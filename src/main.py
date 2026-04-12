from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import load_settings
from src.database import create_session_factory
from src.grpc_client import ProjectsGrpcClient

settings = load_settings()
session_factory = create_session_factory(settings)
grpc_client = ProjectsGrpcClient(settings.grpc.projects_service_addr)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await grpc_client.close()


app = FastAPI(title="Deployment Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.server.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


from src.api.deployments import internal_router, router as deployments_router
from src.api.webhooks import router as webhooks_router
from src.api.projects_gateway import router as projects_router

app.include_router(deployments_router)
app.include_router(internal_router)
app.include_router(webhooks_router)
app.include_router(projects_router)
