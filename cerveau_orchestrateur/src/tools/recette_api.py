"""Appel HTTP vers le microservice Agent Recette Exacte."""
from __future__ import annotations

from typing import Any

import httpx
from langsmith import traceable

from src.core.config import get_settings


@traceable(name="api_recette_exacte", run_type="tool")
async def post_recette_exacte(texte: str) -> dict[str, Any]:
    """
    Appelle ``POST /api/v1/recette`` avec ``{"texte": ...}``.

    Retour typique en succès : ``{"status": "success", "result": "..."}``.
    """
    settings = get_settings()
    payload = {"texte": (texte or "").strip()}
    if not payload["texte"]:
        return {"ok": False, "error": "ERROR_RECETTE_TEXTE_VIDE"}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(settings.url_recette_agent, json=payload)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"ERROR_CONNEXION_RECETTE: {exc}"}
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "error": f"ERROR_HTTP_RECETTE: status={exc.response.status_code} body={exc.response.text[:500]}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ERROR_INATTENDUE_RECETTE: {exc}"}

    result = data.get("result", data)
    return {"ok": True, "result": str(result)}
