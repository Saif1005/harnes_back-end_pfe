"""
Enveloppe JSON standard pour le microservice de classification (niveau 1 uniquement).

Contrat recommandé:
{
  "status": "success" | "error",
  "data": {
    "id_article_erp": "...",
    "input_text": "...",
    "level1": {"label": "MP|PDR", "score": 0.0},
    "categorie_principale": "..."
  } | null,
  "error": {"code": "...", "message": "..."} | null,
  "model_info": {"tool": "...", "version": "...", "device": "...", ...}
}
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

TOOL_ID = "pdr_classifier_level1"
DEFAULT_BACKEND_LABEL = "camembert-base"


def _api_version() -> str:
    return os.environ.get("PDR_TOOL_API_VERSION", "3.0.0")


def build_model_info(
    *,
    device: str = "unknown",
    tool: str = TOOL_ID,
    backend: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "tool": tool,
        "version": _api_version(),
        "device": device,
        "backend": backend or os.environ.get("PDR_TOOL_BACKEND_LABEL", DEFAULT_BACKEND_LABEL),
    }
    info.update(extra)
    return info


def success_envelope(data: Dict[str, Any], *, device: str, **model_info_extra: Any) -> Dict[str, Any]:
    return {
        "status": "success",
        "data": data,
        "error": None,
        "model_info": build_model_info(device=device, **model_info_extra),
    }


def error_envelope(
    *,
    code: str,
    message: str,
    device: str = "unknown",
    http_status: int = 400,
    **model_info_extra: Any,
) -> Tuple[Dict[str, Any], int]:
    body: Dict[str, Any] = {
        "status": "error",
        "data": None,
        "error": {"code": code, "message": message},
        "model_info": build_model_info(device=device, **model_info_extra),
    }
    return body, http_status
