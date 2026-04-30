from __future__ import annotations

from fastapi import APIRouter

from harness_backend.config.settings import SETTINGS

router = APIRouter(prefix="/system/protocols", tags=["system"])


@router.get("")
def protocols() -> dict:
    return {
        "api_style": "REST",
        "protocols": [
            {
                "name": "REST API",
                "transport": "HTTP/JSON",
                "entrypoints": ["/invoke", "/resume", "/approvals/pending", "/admin/training/classification"],
            },
            {
                "name": "MCP Bridge (internal)",
                "transport": "in-process envelope",
                "components": ["tools/contracts.py", "tools/adapters/mcp_adapter.py", "tools/registry.py"],
            },
        ],
        "models": {
            "orchestrator": SETTINGS.orchestrator_model,
            "recipe_agent": SETTINGS.recipe_model,
            "classification_primary": SETTINGS.classifier_primary_model,
            "classification_secondary": SETTINGS.classifier_secondary_model,
        },
    }

