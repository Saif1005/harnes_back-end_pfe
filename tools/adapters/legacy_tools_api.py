from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from harness_backend.config.settings import SETTINGS


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="ignore")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("invalid_json_payload")
    return parsed


def classify_mp_chimie(description: str) -> dict[str, Any]:
    payload = {"description": (description or "").strip()}
    try:
        data = _post_json(SETTINGS.legacy_url_classification_mp_chimie, payload, timeout=20.0)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"classification_mp_chimie_unavailable: {exc}"}
    label = str((data or {}).get("level1", "")).upper()
    if isinstance((data or {}).get("level1"), dict):
        label = str(data["level1"].get("label", "")).upper()
    if label not in {"MP", "CHIMIE"}:
        return {"ok": False, "error": f"classification_mp_chimie_invalid_label: {label}"}
    return {"ok": True, "level1": label, "raw": data}


def classify_pdr_mp(id_article: str, description: str, categorie: str) -> dict[str, Any]:
    payload = {
        "id_article_erp": (id_article or "").strip(),
        "description_texte": (description or "").strip(),
        "description_categorie": (categorie or "").strip(),
    }
    try:
        data = _post_json(SETTINGS.legacy_url_instance_a, payload, timeout=20.0)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"classification_pdr_mp_unavailable: {exc}"}
    label = str((data or {}).get("level1", "")).upper()
    if isinstance((data or {}).get("level1"), dict):
        label = str(data["level1"].get("label", "")).upper()
    if label not in {"MP", "PDR"}:
        return {"ok": False, "error": f"classification_pdr_mp_invalid_label: {label}"}
    return {"ok": True, "level1": label, "raw": data}


def compute_recipe_remote(query: str) -> dict[str, Any]:
    payload = {"texte": (query or "").strip()}
    if not payload["texte"]:
        return {"ok": False, "error": "recipe_empty_query"}
    try:
        data = _post_json(SETTINGS.legacy_url_recette_agent, payload, timeout=60.0)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"recipe_agent_unavailable: {exc}"}
    return {"ok": True, "result": data.get("result", data), "raw": data}

