from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from harness_backend.api.routers.approvals import router as approvals_router
from harness_backend.api.routers.data_admin import router as data_admin_router
from harness_backend.api.routers.health import router as health_router
from harness_backend.api.routers.invoke import router as invoke_router
from harness_backend.api.routers.mcp import router as mcp_router
from harness_backend.api.routers.mcp_reasoning_memory import router as mcp_reasoning_memory_router
from harness_backend.api.routers.monitoring import router as monitoring_router
from harness_backend.api.routers.protocols import router as protocols_router
from harness_backend.api.routers.resume import router as resume_router
from harness_backend.api.routers.training import router as training_router
from harness_backend.api.routers.tools import router as tools_router
from harness_backend.config.settings import SETTINGS
from harness_backend.services.persistence import init_runtime_db
from harness_backend.services.stock_runtime import init_stock_runtime_db


def create_app() -> FastAPI:
    app = FastAPI(title=SETTINGS.app_name, version=SETTINGS.app_version)

    cors_raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if cors_raw in {"", "*"}:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins or ["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    init_runtime_db()
    init_stock_runtime_db()
    app.include_router(health_router)
    app.include_router(invoke_router)
    app.include_router(resume_router)
    app.include_router(approvals_router)
    app.include_router(data_admin_router)
    app.include_router(training_router)
    app.include_router(protocols_router)
    app.include_router(mcp_router)
    app.include_router(mcp_reasoning_memory_router)
    app.include_router(tools_router)
    app.include_router(monitoring_router)
    return app


app = create_app()

