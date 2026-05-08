"""Appel HTTP vers l'API classification XLM-RoBERTa (MP vs CHIMIE) — niveau 1 uniquement."""
from __future__ import annotations

from typing import Any

import httpx
from langchain_core.tools import tool
from langsmith import traceable

from src.core.config import get_settings


@traceable(name="api_mp_chimie_classification", run_type="tool")
async def post_classification_full(
    id_article: str,
    description: str,
    categorie: str,
) -> dict[str, Any]:
    """
    Appelle l'API ``agent-classification`` (classifieur fine-tuné) et renvoie MP ou CHIMIE.

    Succès :
      ``{"ok": True, "level1": "MP"|"CHIMIE", "categorie_principale": "..."}``

    Erreur :
      ``{"ok": False, "error": "ERROR_..."}``
    """
    settings = get_settings()
    parts = [(description or "").strip()]
    if (categorie or "").strip():
        parts.append(f"Contexte: {(categorie or '').strip()}")
    if (id_article or "").strip():
        parts.append(f"Référence: {(id_article or '').strip()}")
    texte = "\n".join(p for p in parts if p)
    payload = {"description": texte or (description or "").strip()}

    timeout = httpx.Timeout(30.0, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                settings.url_classification_mp_chimie,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"ERROR_CONNEXION_CLASSIFICATION: {exc}"}
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "error": (
                f"ERROR_HTTP_CLASSIFICATION: status={exc.response.status_code} "
                f"body={exc.response.text[:300]}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ERROR_INATTENDUE_CLASSIFICATION: {exc}"}

    if not isinstance(data, dict):
        return {"ok": False, "error": "ERROR_REPONSE_CLASSIFICATION: json_invalide"}

    raw_level1 = data.get("level1")
    if isinstance(raw_level1, dict):
        label = str(raw_level1.get("label", "")).upper()
    else:
        label = str(raw_level1 or "").upper()
    if label not in {"MP", "CHIMIE"}:
        return {"ok": False, "error": f"ERROR_REPONSE_CLASSIFICATION: label_invalide={label!r}"}

    categorie_principale = str(data.get("categorie_principale", "")).strip()
    if not categorie_principale:
        categorie_principale = (
            "Ligne de production (Matière Première)"
            if label == "MP"
            else "Zone / magasin produits chimiques"
        )

    return {
        "ok": True,
        "level1": label,
        "categorie_principale": categorie_principale,
    }


@traceable(name="api_pdr_mp_classification", run_type="tool")
async def post_pdr_mp_classification(
    id_article: str,
    description: str,
    categorie: str,
) -> dict[str, Any]:
    """
    Appelle l'API ``agent-pdr`` (port 8000) et renvoie le label MP/PDR.

    Succès :
      ``{"ok": True, "level1": "MP"|"PDR", "categorie_principale": "..."}``
    """
    settings = get_settings()
    payload = {
        "id_article_erp": (id_article or "").strip(),
        "description_texte": (description or "").strip(),
        "description_categorie": (categorie or "").strip(),
    }
    timeout = httpx.Timeout(30.0, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(settings.url_instance_a, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"ERROR_CONNEXION_PDR: {exc}"}
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "error": (
                f"ERROR_HTTP_PDR: status={exc.response.status_code} "
                f"body={exc.response.text[:300]}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ERROR_INATTENDUE_PDR: {exc}"}

    if not isinstance(data, dict):
        return {"ok": False, "error": "ERROR_REPONSE_PDR: json_invalide"}

    raw_level1 = data.get("level1")
    if isinstance(raw_level1, dict):
        label = str(raw_level1.get("label", "")).upper()
    else:
        label = str(raw_level1 or "").upper()
    if label not in {"MP", "PDR"}:
        return {"ok": False, "error": f"ERROR_REPONSE_PDR: label_invalide={label!r}"}

    categorie_principale = str(data.get("categorie_principale", "")).strip()
    return {
        "ok": True,
        "level1": label,
        "categorie_principale": categorie_principale,
    }


async def post_level1_classification(
    id_article: str,
    description: str,
    categorie: str,
) -> str:
    """
    Compatibilité : retourne « MP », « CHIMIE », ou une chaîne ``ERROR_...``.
    """
    out = await post_classification_full(id_article, description, categorie)
    if not out.get("ok"):
        return str(out.get("error", "ERROR_INCONNU"))
    return str(out.get("level1", ""))


@tool("classify_erp_article")
async def classify_erp_article(id_article: str, description: str, categorie: str) -> str:
    """
    Appelle l'API de classification et retourne le label Niveau 1 (MP/CHIMIE).

    Args:
        id_article: Identifiant ERP de l'article.
        description: Description textuelle de l'article.
        categorie: Zone/machine/contexte de l'article.
    """
    return await post_level1_classification(id_article, description, categorie)
