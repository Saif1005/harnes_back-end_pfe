from __future__ import annotations

from fastapi import FastAPI

from harness_backend.api.routers.mcp import router as mcp_router


def create_mcp_app() -> FastAPI:
    app = FastAPI(title="harness-mcp-server", version="0.1.0")
    app.include_router(mcp_router)
    return app


app = create_mcp_app()

