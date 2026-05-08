from __future__ import annotations

from fastapi import APIRouter

from harness_backend.api.schemas.responses import HealthResponse
from harness_backend.config.settings import SETTINGS

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service=SETTINGS.app_name, version=SETTINGS.app_version, status="ok")

