from __future__ import annotations

from typing import Final

from harness_backend.services.legacy_compat import route_fallback_heuristic

ROUTE_RULES: Final[dict[str, tuple[str, ...]]] = {
    "recipe_worker": ("recette", "tonne", "produire", "kraft", "fluting", "testliner"),
    "classification_worker": ("classification", "classer", "mp", "chimie", "pdr", "upload"),
    "stock_worker": ("stock", "disponible", "inventaire", "capacity", "capacité", "prevision", "prediction"),
}


def detect_route(query: str) -> str:
    text = query.lower().strip()
    for route, keywords in ROUTE_RULES.items():
        if any(keyword in text for keyword in keywords):
            return route
    legacy_route = route_fallback_heuristic(text)
    if legacy_route == "classification":
        return "classification_worker"
    if legacy_route == "recette":
        return "recipe_worker"
    return "synthesizer"

