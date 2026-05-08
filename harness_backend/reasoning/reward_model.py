from __future__ import annotations

from typing import Any

from harness_backend.core.state import HarnessState
from harness_backend.reasoning.markov_chain import query_signals_production_order


def score_action_intent(action: str, query: str, trace: list[dict[str, Any]]) -> float:
    """
    Récompense a priori sur l'alignement action ↔ intention opérateur (direction du graphe).
    Complète le score d'état après exécution (voir ``score_incumbent_state``).
    """
    q = (query or "").lower()
    score = 0.05
    executed = {str(t.get("action")) for t in trace if t.get("action") and t.get("action") != "FINISH"}

    if action in executed and action != "FINISH":
        score -= 0.45

    if action == "classification_run" and any(k in q for k in ("class", "mp", "pdr", "chimie", "classer")):
        score += 0.35
    if action == "stock_check" and any(k in q for k in ("stock", "inventaire", "disponible", "magasin")):
        score += 0.32
    if action == "recipe_compute" and any(
        k in q for k in ("recette", "tonne", "produire", "kraft", "fluting", "testliner", "article")
    ):
        score += 0.38
    if action == "prediction_regression" and any(k in q for k in ("prevision", "prévision", "prediction", "tendance")):
        score += 0.3
    if action == "FINISH" and len(trace) >= 1:
        score += 0.22
    if action == "recipe_compute" and query_signals_production_order(query):
        score += 0.12
    return float(score)


def score_incumbent_state(state: HarnessState) -> float:
    """Récompense sur l'état courant (résultats d'outils déjà agrégés)."""
    score = 0.0
    for r in state.get("tool_results") or []:
        if not isinstance(r, dict):
            continue
        if r.get("ok"):
            score += 0.12
        else:
            score -= 0.18
        name = str(r.get("tool_name", ""))
        data = r.get("data") if isinstance(r.get("data"), dict) else {}
        if name == "classification_run" and (data or {}).get("label"):
            score += 0.12
        if name == "stock_check" and (data or {}).get("totals_kg"):
            score += 0.1
        if name == "recipe_compute" and (data or {}).get("recipe_items"):
            score += 0.18
        if name == "prediction_regression" and (data or {}).get("forecast_next_kg"):
            score += 0.08
    return max(0.0, min(1.0, score))
