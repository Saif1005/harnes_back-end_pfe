from __future__ import annotations

from fastapi import FastAPI

from harness_backend.api.routers.approvals import router as approvals_router
from harness_backend.api.routers.health import router as health_router
from harness_backend.api.routers.invoke import router as invoke_router
from harness_backend.api.routers.mcp import router as mcp_router
from harness_backend.api.routers.protocols import router as protocols_router
from harness_backend.api.routers.resume import router as resume_router
from harness_backend.api.routers.training import router as training_router
from harness_backend.config.settings import SETTINGS


def create_app() -> FastAPI:
    app = FastAPI(title=SETTINGS.app_name, version=SETTINGS.app_version)
    app.include_router(health_router)
    app.include_router(invoke_router)
    app.include_router(resume_router)
    app.include_router(approvals_router)
    app.include_router(training_router)
    app.include_router(protocols_router)
    app.include_router(mcp_router)
    return app


app = create_app()

