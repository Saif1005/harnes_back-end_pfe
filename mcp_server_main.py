from __future__ import annotations

from fastapi import FastAPI

from harness_backend.api.routers.mcp import router as mcp_router
from harness_backend.api.routers.mcp_reasoning_memory import router as mcp_reasoning_memory_router
from harness_backend.services.persistence import init_runtime_db


def create_mcp_app() -> FastAPI:
    app = FastAPI(title="harness-mcp-server", version="0.1.0")
    init_runtime_db()
    app.include_router(mcp_router)
    app.include_router(mcp_reasoning_memory_router)
    return app


app = create_mcp_app()

