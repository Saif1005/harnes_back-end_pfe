from __future__ import annotations

from fastapi import APIRouter

from harness_backend.config.settings import SETTINGS
from harness_backend.services.persistence import fetch_recent_tool_runs, fetch_runtime_metrics

router = APIRouter(prefix="/admin/monitoring", tags=["monitoring"])


@router.get("/metrics")
def monitoring_metrics() -> dict:
    return fetch_runtime_metrics()


@router.get("/tool-runs")
def monitoring_tool_runs(limit: int = 50) -> dict:
    return {"items": fetch_recent_tool_runs(limit=limit)}


@router.get("/runtime")
def monitoring_runtime() -> dict:
    return {
        "runtime_db_path": SETTINGS.runtime_db_path,
        "dataset_classification_path": SETTINGS.dataset_classification_path,
        "recipe_correlation_path": SETTINGS.recipe_correlation_path,
        "training_output_dir": SETTINGS.training_output_dir,
        "ollama_base_url": SETTINGS.ollama_base_url,
        "orchestrator_model": SETTINGS.orchestrator_model,
        "recipe_llm_model": SETTINGS.recipe_llm_model,
        "recipe_model": SETTINGS.recipe_model,
        "classification_model_name": SETTINGS.classification_model_name,
        "prediction_model_name": SETTINGS.prediction_model_name,
        "mcp_enabled": SETTINGS.mcp_enabled,
        "mcp_server_url": SETTINGS.mcp_server_url,
    }

