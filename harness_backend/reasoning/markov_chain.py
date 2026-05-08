from __future__ import annotations

import re
from typing import Any

"""Modèle de Markov discret sur les phases de la chaîne industrielle (ERP / production)."""

PHASE_ORDER: tuple[str, ...] = (
    "classification_run",
    "stock_check",
    "recipe_compute",
    "prediction_regression",
)


def markov_suggest_tools(query: str, executed: set[str], max_extra: int = 2) -> list[str]:
    """
    Voisinage Markovien: ordre nominal classification → stock → recette → prévision,
    adapté par mots-clés dans la requête (priorité locale sur la chaîne).
    """
    q = (query or "").lower()
    seq = list(PHASE_ORDER)
    if any(k in q for k in ("recette", "tonne", "produire", "kraft", "fluting", "testliner")):
        seq = ["recipe_compute", "stock_check", "prediction_regression", "classification_run"]
    elif any(k in q for k in ("class", "mp", "pdr", "chimie", "classer")):
        seq = ["classification_run", "stock_check", "prediction_regression", "recipe_compute"]
    elif any(k in q for k in ("stock", "inventaire", "disponible", "magasin")):
        seq = ["stock_check", "prediction_regression", "classification_run", "recipe_compute"]
    elif any(k in q for k in ("prevision", "prévision", "prediction", "tendance")):
        seq = ["prediction_regression", "stock_check", "classification_run", "recipe_compute"]

    out: list[str] = []
    for t in seq:
        if t in executed:
            continue
        out.append(t)
        if len(out) >= max_extra:
            break
    return out


def markov_phase_label(executed: set[str]) -> str:
    for p in PHASE_ORDER:
        if p not in executed:
            return f"pending:{p}"
    return "terminal"


def query_signals_production_order(query: str) -> bool:
    q = (query or "").lower()
    if re.search(r"\b(commande|confirmer|valider\s+production)\b", q, re.IGNORECASE):
        return True
    return bool(re.search(r"\b(\d+(?:[.,]\d+)?)\s*(t\b|tonne|tonnes|kg)\b", q, re.IGNORECASE))
