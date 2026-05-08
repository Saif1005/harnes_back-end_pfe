"""Graphe LangGraph : routage conditionnel (classification / recette / humain) puis synthèse."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches

import json
from typing import Any, Literal

import pandas as pd
from sklearn.linear_model import Ridge
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from src.agent.prompts import (
    SYSTEM_PROMPT_HUMAN,
    SYSTEM_PROMPT_ORCHESTRATEUR_ROUTER,
)
from src.core.config import get_settings
from src.core.state import AgentState
from src.tools.classification_api import post_classification_full, post_pdr_mp_classification
from src.core.database import SessionLocal
from src.models.entities import WarehouseStockSnapshot
from src.tools.recette_api import post_recette_exacte

settings = get_settings()
LOGGER = logging.getLogger(__name__)
StateUpdate = dict[str, Any]
CONSUMED_CONFIRMATION_TOKENS: set[str] = set()
TOKEN_LOCK = asyncio.Lock()
INVENTORY_LOCK = asyncio.Lock()
INVENTORY_CACHE: dict[str, float] | None = None
DASHBOARD_CACHE: dict[str, object] | None = None
INVENTORY_LABEL_CACHE: dict[str, str] | None = None
RECIPE_RATIO_CACHE: dict[str, dict[str, Any]] | None = None
STOCK_PREDICTION_HISTORY: list[dict[str, Any]] = []

llm = ChatOllama(
    base_url=settings.ollama_base_url,
    model=settings.ollama_model,
    temperature=0.0,
)


def _normalize_col_name(col: str) -> str:
    return re.sub(r"\s+", " ", (col or "").strip().lower())


def _pick_column(columns: list[str], patterns: tuple[str, ...]) -> str | None:
    normalized = {_normalize_col_name(c): c for c in columns}
    for pattern in patterns:
        for col_norm, original in normalized.items():
            if pattern in col_norm:
                return original
    return None


def _to_float(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    raw = raw.replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _normalize_key(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", raw)


# Correspondance article production -> libellé recette canonique.
# Objectif: un opérateur peut écrire un alias ("kraft pour sacs")
# et le moteur recette reçoit un libellé stable.
ARTICLE_ALIAS_MAP: dict[str, str] = {
    "kraft pour sacs": "Kraft pour sacs",
    "kraft for sacs": "Kraft pour sacs",
    "cannelure": "Cannelure (Fluting)",
    "fluting": "Cannelure (Fluting)",
    "cannelure fluting": "Cannelure (Fluting)",
    "testliner": "TestLiner",
    "testliner colore": "TestLiner Coloré",
    "testliner coloree": "TestLiner Coloré",
    "sotikraft": "SotiKraft",
    "sotikraft colore": "SotiKraft Coloré (KraftLiner)",
    "sotikraft coloree": "SotiKraft Coloré (KraftLiner)",
    "kraftliner": "SotiKraft Coloré (KraftLiner)",
}


# Correspondance manuelle métier (ingrédient recette -> libellés stock usine probables).
# Le matching normalisé est appliqué ensuite (minuscules, espaces).
INGREDIENT_ALIAS_MAP: dict[str, list[str]] = {
    "biocide": ["sanikem 522", "biocide", "autre_marque"],
    "antimousse afranil": ["afranil ltd anti-mousse", "antimousse", "anti-mousse"],
    "agent de retention": ["produit de retention", "retention", "nalco core shell"],
    "polymere krofta": ["polymer", "krofta", "intrabond", "carbofloc"],
    "amidon cationique": ["amidon", "cationique", "carbofloc"],
    "amidon oxyde": ["amidon oxyde", "amidon", "oxyde"],
    "waste paper ratio": ["vieux papier", "waste paper", "papier recycle"],
    "prestige": ["prestige"],
    # variantes EN issues de la base recette
    "starch cationic ratio": ["amidon cationique", "starch cationic", "cationic starch", "carbofloc"],
    "starch oxidized ratio": ["amidon oxyde", "starch oxidized", "oxidized starch"],
    "waste paper ratio": ["vieux papier", "waste paper", "papier recycle"],
    "retention aids ratio": ["agent de retention", "retention", "produit de retention"],
    "krofta polymer ratio": ["polymere krofta", "polymer", "krofta", "intrabond"],
    "prestige cleaning aids ratio (prestige)": ["prestige", "cleaning aids", "aides nettoyage"],
    "defoamer ratio (defoamer 1 (afranil))": ["antimousse afranil", "defoamer", "anti-mousse", "afranil"],
    "sizing kraft (agent collage asa)": ["agent collage asa", "sizing kraft", "asa"],
    "standard pulp ratio": ["pate standard", "standard pulp", "pulp"],
    "flocon pulp ratio": ["pate flocon", "flocon pulp", "pulp"],
}


INGREDIENT_DISPLAY_MAP: dict[str, str] = {
    "fiber ratio": "Vieux papier",
    "waste paper ratio": "Vieux papier",
    "starch cationic ratio": "Amidon cationique",
    "starch oxidized ratio": "Amidon oxyde",
    "biocide ratio": "Biocide",
    "defoamer ratio (defoamer 1 (afranil))": "Antimousse afranil",
    "retention aids ratio": "Agent de retention",
    "krofta polymer ratio": "Polymere krofta",
    "prestige cleaning aids ratio (prestige)": "Prestige",
    "pulp ratio": "Pate papier",
    "standard pulp ratio": "Pate standard",
    "flocon pulp ratio": "Pate flocon",
    "sizing kraft (agent collage asa)": "Agent collage ASA",
}


def _canonical_ingredient_name(raw_ingredient: str) -> str:
    raw = str(raw_ingredient or "").strip()
    if not raw:
        return ""
    norm = _normalize_key(raw)
    mapped = INGREDIENT_DISPLAY_MAP.get(norm)
    if mapped:
        return mapped
    return raw


def _parse_recipe_items(raw_text: str) -> list[dict[str, Any]]:
    """
    Parse les lignes du format recette :
      '1 - amidon cationique : 123.000 kg'
      '1 - waste paper ratio : 12.040 tonnes'
    """
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^\s*\d+\s*-\s*(.+?)\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*(kg|tonne|tonnes|t)\b",
        re.IGNORECASE,
    )
    for line in (raw_text or "").splitlines():
        m = pattern.search(line.strip())
        if not m:
            continue
        ingredient = _canonical_ingredient_name(str(m.group(1)).strip())
        value = _to_float(m.group(2))
        unit_raw = str(m.group(3) or "kg").strip().lower()
        is_tonnes = unit_raw in {"tonne", "tonnes", "t"}
        required_kg = value * 1000.0 if is_tonnes else value
        if ingredient and required_kg > 0:
            items.append(
                {
                    "ingredient": ingredient,
                    "required_value": value,
                    "required_unit": "tonnes" if is_tonnes else "kg",
                    "required_kg": required_kg,
                }
            )
    return items


def _format_recipe_table(recipe_items: list[dict[str, Any]]) -> str:
    if not recipe_items:
        return ""
    lines = [
        "Table recette (valeurs issues du tool recette):",
        "| Ingrédient | Quantité requise |",
        "|---|---|",
    ]
    for item in recipe_items[:20]:
        ingredient = str(item.get("ingredient", "")).strip() or "-"
        req_kg = float(item.get("required_kg", 0.0) or 0.0)
        if req_kg >= 1000:
            qty = f"{req_kg/1000.0:.3f} t ({req_kg:.2f} kg)"
        else:
            qty = f"{req_kg:.2f} kg"
        lines.append(f"| {ingredient} | {qty} |")
    return "\n".join(lines)


def _format_stock_alert_lines(alerts: list[dict[str, Any]]) -> str:
    if not alerts:
        return "Alertes stock: aucune alerte."
    lines = ["Alertes stock (issues du contrôle inventaire):"]
    for a in alerts[:20]:
        ingredient = str(a.get("ingredient", "-"))
        required = float(a.get("required_kg", 0.0) or 0.0)
        available = float(a.get("available_kg", 0.0) or 0.0)
        missing = float(a.get("missing_kg", 0.0) or 0.0)
        lines.append(
            f"- {ingredient}: requis={required:.2f} kg, disponible={available:.2f} kg, manquant={missing:.2f} kg"
        )
    return "\n".join(lines)


def _find_inventory_match(ingredient: str, inventory: dict[str, float]) -> tuple[str | None, float]:
    if not inventory:
        return None, 0.0
    inv_keys = list(inventory.keys())
    normalized_to_original = {_normalize_key(k): k for k in inv_keys}
    ing_norm = _normalize_key(ingredient)

    # Match exact normalisé
    if ing_norm in normalized_to_original:
        key = normalized_to_original[ing_norm]
        return key, float(inventory.get(key, 0.0))

    inv_norm_keys = list(normalized_to_original.keys())

    def _ingredient_forms(base: str) -> list[str]:
        forms = [base]
        # Retirer parenthèses et suffixe "ratio" pour matcher des libellés stock plus courts.
        no_paren = re.sub(r"\([^)]*\)", " ", base).strip()
        no_ratio = re.sub(r"\bratio\b", " ", no_paren).strip()
        cleaned = re.sub(r"\s+", " ", no_ratio).strip()
        if cleaned:
            forms.append(cleaned)
        if " " in cleaned:
            parts = [p for p in cleaned.split(" ") if len(p) >= 4]
            if parts:
                forms.extend(parts)
        return list(dict.fromkeys([f for f in forms if f]))

    def _pick_best(candidates: list[str]) -> tuple[str | None, float]:
        if not candidates:
            return None, 0.0
        # Favoriser d'abord la plus grande disponibilité réelle.
        best_norm = max(
            candidates,
            key=lambda n: float(inventory.get(normalized_to_original.get(n, ""), 0.0)),
        )
        key = normalized_to_original[best_norm]
        return key, float(inventory.get(key, 0.0))

    # 1) Dictionnaire manuel métier (priorité haute)
    alias_candidates = INGREDIENT_ALIAS_MAP.get(ing_norm, [])
    alias_matches: list[str] = []
    for alias in alias_candidates:
        alias_norm = _normalize_key(alias)
        for inv_norm in inv_norm_keys:
            if alias_norm and (alias_norm in inv_norm or inv_norm in alias_norm):
                alias_matches.append(inv_norm)
    alias_matches = list(dict.fromkeys(alias_matches))
    key, qty = _pick_best(alias_matches)
    if key is not None:
        return key, qty

    # 2) Inclusion simple (utile quand les libellés stock sont plus longs)
    inclusion_matches: list[str] = []
    for form in _ingredient_forms(ing_norm):
        for inv_norm in inv_norm_keys:
            if form in inv_norm or inv_norm in form:
                inclusion_matches.append(inv_norm)
    inclusion_matches = list(dict.fromkeys(inclusion_matches))
    key, qty = _pick_best(inclusion_matches)
    if key is not None:
        return key, qty

    # 3) Match flou renforcé : top candidats puis meilleur ratio
    close_norm = get_close_matches(ing_norm, inv_norm_keys, n=5, cutoff=0.52)
    if close_norm:
        best_norm = max(close_norm, key=lambda c: SequenceMatcher(None, ing_norm, c).ratio())
        key = normalized_to_original[best_norm]
        return key, float(inventory.get(key, 0.0))

    return None, 0.0


def _infer_ingredient_stock_label(ingredient: str) -> str:
    """Best-effort ingredient family inference when exact stock key is unavailable."""
    key = _normalize_key(ingredient)
    chimie_markers = (
        "biocide",
        "defoamer",
        "afranil",
        "retention",
        "cleaning",
        "aids",
        "asa",
        "agent collage",
        "anti mousse",
        "antimousse",
    )
    pdr_markers = ("pdr", "piece de rechange", "pièce de rechange", "maintenance")
    if any(m in key for m in pdr_markers):
        return "PDR"
    if any(m in key for m in chimie_markers):
        return "CHIMIE"
    return "MP"


def _available_by_label_fallback(ingredient: str, inventory: dict[str, float]) -> tuple[str, float]:
    """
    If ingredient->article matching fails, use classified stock totals by label
    from INVENTORY_LABEL_CACHE.
    """
    target_label = _infer_ingredient_stock_label(ingredient)
    labels = dict(INVENTORY_LABEL_CACHE or {})
    totals_by_label: dict[str, float] = {"MP": 0.0, "CHIMIE": 0.0, "PDR": 0.0}
    for article, qty in (inventory or {}).items():
        lbl = str(labels.get(str(article), "")).upper()
        if lbl in totals_by_label:
            totals_by_label[lbl] += float(qty or 0.0)
    total = float(totals_by_label.get(target_label, 0.0) or 0.0)
    if total > 0.0:
        return target_label, total
    # If only one family has stock > 0, use it as ultimate fallback.
    positive_labels = [k for k, v in totals_by_label.items() if float(v or 0.0) > 0.0]
    if len(positive_labels) == 1:
        only = positive_labels[0]
        return only, float(totals_by_label.get(only, 0.0) or 0.0)
    return target_label, 0.0


def _build_stock_alerts(recipe_items: list[dict[str, Any]], inventory: dict[str, float]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for item in recipe_items:
        ingredient = str(item.get("ingredient", "")).strip()
        required = float(item.get("required_kg", 0.0))
        if not ingredient or required <= 0:
            continue
        matched_key, available = _find_inventory_match(ingredient, inventory)
        if (not matched_key or available <= 0.0) and inventory:
            fallback_label, fallback_available = _available_by_label_fallback(ingredient, inventory)
            if fallback_available > 0.0:
                matched_key = matched_key or f"__LABEL__:{fallback_label}"
                available = fallback_available
        missing = max(0.0, required - available)
        if missing > 0:
            alerts.append(
                {
                    "ingredient": ingredient,
                    "matched_inventory_key": matched_key or "",
                    "required_kg": required,
                    "available_kg": available,
                    "missing_kg": missing,
                    "severity": "critical" if available <= 0 else "warning",
                }
            )
    return alerts


def _estimate_production_capacity(
    recipe_items: list[dict[str, Any]], inventory: dict[str, float], requested_tonnage: float
) -> dict[str, Any]:
    effective_tonnage = requested_tonnage if requested_tonnage > 0 else 1.0
    per_ingredient: list[dict[str, Any]] = []
    for item in recipe_items:
        ingredient = str(item.get("ingredient") or "").strip()
        required_kg = float(item.get("required_kg", 0.0) or 0.0)
        if not ingredient or required_kg <= 0:
            continue
        required_per_ton_kg = required_kg / effective_tonnage
        if required_per_ton_kg <= 0:
            continue
        matched_key, available_kg = _find_inventory_match(ingredient, inventory)
        if (not matched_key or available_kg <= 0.0) and inventory:
            fallback_label, fallback_available = _available_by_label_fallback(ingredient, inventory)
            if fallback_available > 0.0:
                matched_key = matched_key or f"__LABEL__:{fallback_label}"
                available_kg = fallback_available
        possible_tons = available_kg / required_per_ton_kg
        per_ingredient.append(
            {
                "ingredient": ingredient,
                "matched_inventory_key": matched_key or "",
                "available_kg": available_kg,
                "required_per_ton_kg": required_per_ton_kg,
                "possible_tons": max(0.0, possible_tons),
            }
        )
    if not per_ingredient:
        return {}
    limiting = min(per_ingredient, key=lambda x: float(x.get("possible_tons", 0.0)))
    max_tons = float(limiting.get("possible_tons", 0.0) or 0.0)
    full_orders = int(max_tons // effective_tonnage)
    return {
        "requested_tonnage": requested_tonnage,
        "max_producible_tonnage": max_tons,
        "full_orders_possible": max(0, full_orders),
        "limiting_ingredient": str(limiting.get("ingredient") or ""),
        "limiting_available_kg": float(limiting.get("available_kg", 0.0) or 0.0),
        "limiting_required_per_ton_kg": float(limiting.get("required_per_ton_kg", 0.0) or 0.0),
    }


def _apply_consumption(
    inventory: dict[str, float], recipe_items: list[dict[str, Any]]
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    updated = {k: float(v) for k, v in (inventory or {}).items()}
    movements: list[dict[str, Any]] = []
    for item in recipe_items:
        ingredient = str(item.get("ingredient", "")).strip()
        required = float(item.get("required_kg", 0.0))
        if not ingredient or required <= 0:
            continue
        matched_key, available = _find_inventory_match(ingredient, updated)
        # Fallback: consume from the biggest article inside inferred label bucket.
        if (not matched_key or available <= 0.0) and updated:
            fallback_label, _fallback_available = _available_by_label_fallback(ingredient, updated)
            labels = dict(INVENTORY_LABEL_CACHE or {})
            candidates = [
                k for k, v in updated.items() if str(labels.get(str(k), "")).upper() == fallback_label and float(v or 0.0) > 0.0
            ]
            if candidates:
                matched_key = max(candidates, key=lambda k: float(updated.get(k, 0.0) or 0.0))
                available = float(updated.get(matched_key, 0.0) or 0.0)
        target_key = matched_key or ingredient
        before = float(updated.get(target_key, 0.0))
        after = max(0.0, before - required)
        updated[target_key] = after
        movements.append(
            {
                "ingredient": ingredient,
                "inventory_key": target_key,
                "consumed_kg": required,
                "stock_before_kg": before,
                "stock_after_kg": after,
            }
        )
    return updated, movements


def _refresh_dashboard(
    dashboard: dict[str, Any],
    updated_inventory: dict[str, float],
    movements: list[dict[str, Any]],
    inventory_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    next_dashboard = dict(dashboard or {})
    top_n = max(1, int(settings.inventory_dashboard_top_n))
    top_sorted = sorted(updated_inventory.items(), key=lambda kv: float(kv[1]), reverse=True)
    next_dashboard["top_items"] = [
        {"article": str(name), "stock_total": float(stock)} for name, stock in top_sorted[:top_n]
    ]
    next_dashboard["unique_articles"] = int(len(updated_inventory))
    next_dashboard["last_consumption"] = movements
    labels = dict(inventory_labels or {})
    final_totals = {"MP": 0.0, "CHIMIE": 0.0, "PDR": 0.0, "UNKNOWN": 0.0}
    for article, qty in updated_inventory.items():
        lbl = str(labels.get(str(article), "UNKNOWN")).upper()
        if lbl not in final_totals:
            lbl = "UNKNOWN"
        final_totals[lbl] += float(qty or 0.0)
    next_dashboard["final_totals_kg"] = final_totals
    return next_dashboard


def _stock_totals_from_dashboard(dashboard: dict[str, Any]) -> dict[str, float]:
    totals = dict((dashboard or {}).get("final_totals_kg") or {})
    return {
        "MP": float(totals.get("MP", 0.0) or 0.0),
        "CHIMIE": float(totals.get("CHIMIE", 0.0) or 0.0),
        "PDR": float(totals.get("PDR", 0.0) or 0.0),
    }


class StockPredictionService:
    """Encapsulates stock prediction history and autonomous ML inference."""

    def __init__(self, history: list[dict[str, Any]]) -> None:
        self.history = history
        self.models: dict[str, Ridge] = {}
        self.trained_points = 0
        self.trained_at: str | None = None

    def record_point(self, dashboard: dict[str, Any], reason: str, force: bool = False) -> None:
        totals = _stock_totals_from_dashboard(dashboard)
        if not any(v > 0 for v in totals.values()):
            return
        now = datetime.now(timezone.utc).isoformat()
        entry = {"at": now, "reason": reason, **totals}
        if self.history:
            last = self.history[-1]
            if (
                not force
                and
                float(last.get("MP", 0.0)) == totals["MP"]
                and float(last.get("CHIMIE", 0.0)) == totals["CHIMIE"]
                and float(last.get("PDR", 0.0)) == totals["PDR"]
            ):
                return
        self.history.append(entry)
        if len(self.history) > 120:
            del self.history[:-120]

    @staticmethod
    def _linear_next(values: list[float]) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        n = float(len(values))
        xs = [float(i) for i in range(len(values))]
        sum_x = sum(xs)
        sum_y = sum(values)
        sum_x2 = sum(x * x for x in xs)
        sum_xy = sum(x * y for x, y in zip(xs, values))
        denom = (n * sum_x2) - (sum_x * sum_x)
        if abs(denom) < 1e-9:
            slope = 0.0
        else:
            slope = ((n * sum_xy) - (sum_x * sum_y)) / denom
        intercept = (sum_y - (slope * sum_x)) / n
        next_x = n
        return max(0.0, float((slope * next_x) + intercept))

    @staticmethod
    def _to_training_xy(values: list[float]) -> tuple[list[list[float]], list[float]]:
        xs: list[list[float]] = []
        ys: list[float] = []
        for i in range(1, len(values)):
            xs.append([float(i), float(values[i - 1])])
            ys.append(float(values[i]))
        return xs, ys

    def _train_models_if_needed(self, history: list[dict[str, Any]]) -> bool:
        if len(history) < 4:
            return False
        if self.trained_points == len(history) and self.models:
            return False
        trained_models: dict[str, Ridge] = {}
        for label in ("MP", "CHIMIE", "PDR"):
            values = [float(p.get(label, 0.0) or 0.0) for p in history]
            xs, ys = self._to_training_xy(values)
            if len(xs) < 3 or len(ys) < 3:
                continue
            model = Ridge(alpha=1.0)
            model.fit(xs, ys)
            trained_models[label] = model
        if trained_models:
            self.models = trained_models
            self.trained_points = len(history)
            self.trained_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def _ml_next(self, label: str, values: list[float]) -> float:
        if not values:
            return 0.0
        if len(values) < 4:
            return self._linear_next(values)
        model = self.models.get(label)
        if model is None:
            return self._linear_next(values)
        try:
            next_x = [float(len(values)), float(values[-1])]
            pred = float(model.predict([next_x])[0])
            return max(0.0, pred)
        except Exception:  # noqa: BLE001
            return self._linear_next(values)

    def build_prediction(self) -> dict[str, Any]:
        min_train_points = 4
        history = self.history[-30:]
        if len(history) < 3:
            return {}
        retrained = self._train_models_if_needed(history)
        current_totals = {
            "MP": float(history[-1].get("MP", 0.0) or 0.0),
            "CHIMIE": float(history[-1].get("CHIMIE", 0.0) or 0.0),
            "PDR": float(history[-1].get("PDR", 0.0) or 0.0),
        }
        out: dict[str, Any] = {
            "model": "ridge_regression_lag1",
            "history_points": len(history),
            "horizon_steps": 1,
            "current_totals_kg": current_totals,
            "predicted_totals_kg": {},
            "projected_delta_kg": {},
            "depletion_risk": {},
            "confidence_score": {},
            "trained_points": int(self.trained_points),
            "trained_at": self.trained_at or "",
            "auto_retrained": bool(retrained),
            "training_min_points": min_train_points,
            "training_pending_points": max(0, min_train_points - len(history)),
            "training_status": "trained" if self.models else "collecting_history",
        }
        for label in ("MP", "CHIMIE", "PDR"):
            values = [float(p.get(label, 0.0) or 0.0) for p in history]
            predicted = self._ml_next(label, values)
            current = float(values[-1] if values else 0.0)
            trend = predicted - current
            mean = sum(values) / float(len(values)) if values else 0.0
            var = sum((v - mean) ** 2 for v in values) / float(max(1, len(values)))
            stdev = var ** 0.5
            volatility_ratio = stdev / max(1.0, abs(mean))
            confidence = max(0.1, min(0.99, 1.0 - min(1.0, volatility_ratio)))
            risk = "stable"
            if predicted <= 0.0 and current > 0.0:
                risk = "critical"
            elif trend < -0.02 * max(current, 1.0):
                risk = "down"
            elif trend > 0.02 * max(current, 1.0):
                risk = "up"
            out["predicted_totals_kg"][label] = round(predicted, 3)
            out["projected_delta_kg"][label] = round(trend, 3)
            out["depletion_risk"][label] = risk
            out["confidence_score"][label] = round(float(confidence), 3)
        return out


STOCK_PREDICTOR = StockPredictionService(STOCK_PREDICTION_HISTORY)


def _record_stock_prediction_point(dashboard: dict[str, Any], reason: str, force: bool = False) -> None:
    STOCK_PREDICTOR.record_point(dashboard, reason, force=force)


def _build_stock_prediction() -> dict[str, Any]:
    return STOCK_PREDICTOR.build_prediction()


def _build_confirmation_token(state: AgentState, recipe_items: list[dict[str, Any]]) -> str:
    """
    Token déterministe pour une commande recette donnée.
    Évite de confirmer une mauvaise commande et permet de bloquer les doublons.
    """
    normalized_items = sorted(
        [
            f"{_normalize_key(str(item.get('ingredient', '')))}:{float(item.get('required_kg', 0.0)):.3f}"
            for item in recipe_items
        ]
    )
    signature = "|".join(
        [
            str(state.get("id_article_erp", "")).strip().lower(),
            _normalize_key(str(state.get("description", ""))),
            _normalize_key(str(state.get("question_operateur", ""))),
            ";".join(normalized_items),
        ]
    )
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    return f"prod_{digest[:16]}"


def _load_inventory_rows() -> tuple[list[dict[str, Any]], dict[str, object]]:
    """
    Charge l'Excel et prépare une base consolidée par article (quantité totale).
    """
    excel_path = settings.inventory_excel_path
    df: Any = pd.read_excel(excel_path)

    designation_col = _pick_column(
        list(df.columns),
        ("designation", "libelle", "description", "article", "item", "produit"),
    )
    stock_col = _pick_column(
        list(df.columns),
        ("stock", "qte", "quantite", "quantity", "disponible", "solde"),
    )
    id_col = _pick_column(
        list(df.columns),
        ("id article", "id_article", "code article", "code", "reference", "ref", "erp"),
    )
    categorie_col = _pick_column(
        list(df.columns),
        ("categorie", "famille", "machine", "zone", "atelier"),
    )

    if not designation_col or not stock_col:
        raise ValueError(
            "Colonnes introuvables pour la consolidation du stock. "
            f"Colonnes détectées={list(df.columns)!r}, "
            f"designation_col={designation_col!r}, stock_col={stock_col!r}"
        )

    cols = [designation_col, stock_col]
    if id_col:
        cols.append(id_col)
    if categorie_col:
        cols.append(categorie_col)

    work: Any = df[cols].copy()
    work[designation_col] = work[designation_col].apply(lambda x: str(x).strip())
    work = work[work[designation_col] != ""]
    work["__stock_num__"] = work[stock_col].apply(_to_float)

    agg_spec: dict[str, str] = {"__stock_num__": "sum"}
    if id_col:
        agg_spec[id_col] = "first"
    if categorie_col:
        agg_spec[categorie_col] = "first"
    grouped: Any = work.groupby(designation_col, dropna=True).agg(agg_spec).reset_index()
    grouped = grouped.sort_values("__stock_num__", ascending=False)

    max_items = max(1, int(settings.inventory_classification_max_items))
    records: list[dict[str, Any]] = []
    for _, row in grouped.head(max_items).iterrows():
        article = str(row.get(designation_col, "")).strip()
        if not article:
            continue
        records.append(
            {
                "article": article,
                "quantity": float(row.get("__stock_num__", 0.0) or 0.0),
                "id_article_erp": str(row.get(id_col, "")).strip() if id_col else "",
                "categorie": str(row.get(categorie_col, "")).strip() if categorie_col else "",
            }
        )

    base_dashboard: dict[str, object] = {
        "source_excel": excel_path,
        "rows_read": int(len(df)),
        "rows_after_cleaning": int(len(work)),
        "unique_articles_raw": int(len(grouped)),
        "items_selected_for_classification": int(len(records)),
        "designation_column": designation_col,
        "stock_column": stock_col,
        "id_column": id_col or "",
        "categorie_column": categorie_col or "",
    }
    return records, base_dashboard


def _load_inventory_rows_from_db() -> tuple[list[dict[str, Any]], dict[str, object]]:
    """Charge l'inventaire réel depuis la base warehouse_stock_snapshots si disponible."""
    db = SessionLocal()
    try:
        rows = db.query(WarehouseStockSnapshot).all()
        if not rows:
            return [], {}
        records: list[dict[str, Any]] = []
        latest_snapshot_date = ""
        latest_source_file = ""
        for row in rows:
            if row.snapshot_date and str(row.snapshot_date) > latest_snapshot_date:
                latest_snapshot_date = str(row.snapshot_date)
                latest_source_file = str(row.source_file or "")
            records.append(
                {
                    "article": str(row.description or "").strip(),
                    "quantity": float(row.stock_quantity_kg or 0.0),
                    "id_article_erp": str(row.id_article_erp or "").strip(),
                    "categorie": str(row.categorie or "").strip(),
                    "stage1_label": str(row.stage1_mp_pdr or "").upper() or "UNKNOWN",
                    "final_label": str(row.final_label or "").upper() or "UNKNOWN",
                }
            )
        dashboard: dict[str, object] = {
            "source": "warehouse_db_snapshot",
            "latest_snapshot_date": latest_snapshot_date,
            "latest_source_file": latest_source_file,
            "rows_read": len(records),
        }
        return records, dashboard
    finally:
        db.close()


@traceable(name="stock_stage12_classification", run_type="chain")
async def _classify_stock_record(record: dict[str, Any], sem: asyncio.Semaphore) -> dict[str, Any]:
    async with sem:
        article = str(record.get("article", "")).strip()
        id_article = str(record.get("id_article_erp", "")).strip()
        categorie = str(record.get("categorie", "")).strip()
        quantity = float(record.get("quantity", 0.0) or 0.0)
        if not article:
            return {**record, "stage1_label": "UNKNOWN", "final_label": "UNKNOWN", "error": "EMPTY_ARTICLE"}

        stage1 = await post_pdr_mp_classification(
            id_article=id_article,
            description=article,
            categorie=categorie,
        )
        if not stage1.get("ok"):
            return {
                **record,
                "stage1_label": "UNKNOWN",
                "final_label": "UNKNOWN",
                "error": str(stage1.get("error", "PDR_CLASSIFICATION_FAILED")),
            }

        stage1_label = str(stage1.get("level1", "UNKNOWN")).upper()
        final_label = stage1_label
        stage2_error = ""

        # 2e classification seulement si stage1=MP
        if stage1_label == "MP":
            stage2 = await post_classification_full(
                id_article=id_article,
                description=article,
                categorie=categorie,
            )
            if stage2.get("ok"):
                stage2_label = str(stage2.get("level1", "MP")).upper()
                final_label = stage2_label if stage2_label in {"MP", "CHIMIE"} else "MP"
            else:
                final_label = "MP"
                stage2_error = str(stage2.get("error", "MP_CHIMIE_CLASSIFICATION_FAILED"))

        return {
            **record,
            "quantity": quantity,
            "stage1_label": stage1_label,
            "final_label": final_label,
            "stage2_error": stage2_error,
            "error": "",
        }


@traceable(name="stock_build_from_real_data", run_type="chain")
async def _build_stock_from_real_data() -> tuple[dict[str, float], dict[str, object], dict[str, str]]:
    db_records, db_dashboard = await asyncio.to_thread(_load_inventory_rows_from_db)
    if db_records:
        classified = db_records
        base_dashboard = dict(db_dashboard)
        concurrency = 0
    else:
        records, base_dashboard = await asyncio.to_thread(_load_inventory_rows)
        concurrency = max(1, int(settings.inventory_classification_concurrency))
        sem = asyncio.Semaphore(concurrency)
        classified = await asyncio.gather(*[_classify_stock_record(r, sem) for r in records])

    inventory: dict[str, float] = {}
    inventory_labels: dict[str, str] = {}
    stage1_totals = {"MP": 0.0, "PDR": 0.0, "UNKNOWN": 0.0}
    final_totals = {"MP": 0.0, "CHIMIE": 0.0, "PDR": 0.0, "UNKNOWN": 0.0}
    errors = 0

    for row in classified:
        article = str(row.get("article", "")).strip()
        qty = float(row.get("quantity", 0.0) or 0.0)
        stage1_label = str(row.get("stage1_label", "UNKNOWN")).upper()
        final_label = str(row.get("final_label", "UNKNOWN")).upper()
        if stage1_label not in stage1_totals:
            stage1_label = "UNKNOWN"
        if final_label not in final_totals:
            final_label = "UNKNOWN"
        stage1_totals[stage1_label] += qty
        final_totals[final_label] += qty
        if row.get("error"):
            errors += 1
        if article:
            inventory[article] = inventory.get(article, 0.0) + qty
            inventory_labels[article] = final_label

    top_n = max(1, int(settings.inventory_dashboard_top_n))
    top_sorted = sorted(inventory.items(), key=lambda kv: float(kv[1]), reverse=True)
    top_items = [{"article": name, "stock_total": float(stock)} for name, stock in top_sorted[:top_n]]

    dashboard: dict[str, object] = {
        **base_dashboard,
        "pipeline": "warehouse_db_snapshot" if db_records else "agent-pdr(MP/PDR) -> agent-classification(MP/CHIMIE for MP only)",
        "concurrency": concurrency,
        "classified_items": int(len(classified)),
        "classification_errors": int(errors),
        "stage1_totals_kg": stage1_totals,
        "final_totals_kg": final_totals,
        "unique_articles": int(len(inventory)),
        "top_items": top_items,
    }
    return inventory, dashboard, inventory_labels


@traceable(name="node_load_inventory", run_type="chain")
async def node_load_inventory(state: AgentState) -> StateUpdate:
    """
    Étape 1 — Ingestion & Structuration (chaîne réelle usine) :
    1) agent-pdr classe MP/PDR avec quantité,
    2) agent-classification reclasse les MP en MP/CHIMIE,
    puis consolidation de la base personnalisée ``stock``.
    """
    global INVENTORY_CACHE, DASHBOARD_CACHE, INVENTORY_LABEL_CACHE
    LOGGER.info("node_load_inventory:start")
    async with INVENTORY_LOCK:
        if INVENTORY_CACHE is None or DASHBOARD_CACHE is None:
            try:
                inventory, dashboard, inventory_labels = await _build_stock_from_real_data()
                INVENTORY_CACHE = dict(inventory)
                DASHBOARD_CACHE = dict(dashboard)
                INVENTORY_LABEL_CACHE = dict(inventory_labels)
                _record_stock_prediction_point(DASHBOARD_CACHE, reason="inventory_loaded")
                LOGGER.info(
                    "node_load_inventory:loaded unique_articles=%s classified_items=%s",
                    dashboard.get("unique_articles"),
                    dashboard.get("classified_items"),
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("node_load_inventory:error")
                return {
                    "inventory": {},
                    "inventory_dashboard": {
                        "source_excel": settings.inventory_excel_path,
                        "error": str(exc),
                    },
                }
        else:
            LOGGER.info(
                "node_load_inventory:cache_hit unique_articles=%s",
                DASHBOARD_CACHE.get("unique_articles"),
            )
        return {
            "inventory": dict(INVENTORY_CACHE),
            "inventory_dashboard": dict(DASHBOARD_CACHE),
        }


def _parse_route_json(text: str) -> tuple[str, str]:
    """Extrait ``route`` et ``thought`` depuis une réponse modèle (JSON)."""
    raw = (text or "").strip()
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(raw[start : end + 1])
            route = str(obj.get("route", "human")).lower().strip()
            thought = str(obj.get("thought", "")).strip()
            if route in {"classification", "recette", "workflow", "human"}:
                return route, thought
    except Exception:  # noqa: BLE001
        pass
    return "human", ""


def _looks_like_recipe_request(question: str) -> bool:
    q = (question or "").lower().strip()
    if not q:
        return False
    recipe_keywords = (
        "recette",
        "produire",
        "production",
        "tonne",
        "tonnes",
        "tonnage",
        "kg",
        "dosage",
        "quantite",
        "quantité",
        "kraft",
        "sac",
        "pm0",
    )
    if any(k in q for k in recipe_keywords):
        return True
    # Ex: "14.6 tonnes de kraft pour sacs"
    return bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(t|tonne|tonnes|kg)\b", q))


def _looks_like_classification_request(question: str) -> bool:
    q = (question or "").lower().strip()
    if not q:
        return False
    if any(re.search(p, q) for p in (r"\bmp\b", r"\bpdr\b", r"\bchimie\b")):
        return True
    return any(
        k in q
        for k in (
            "classification",
            "classer",
            "classe",
            "matiere premiere",
            "matière première",
            "piece de rechange",
            "pièce de rechange",
            "type article",
        )
    )


def _extract_material_candidates(question: str) -> list[str]:
    """
    Extrait une liste simple de matières depuis la question opérateur.
    Exemples supportés:
      - "classe : biocide, amidon, afranil"
      - "matières suivantes: biocide - antimousse - polymere"
    """
    q = str(question or "").strip()
    if not q:
        return []
    lower_q = q.lower()

    # Cas "mono matière" explicite: on évite tout split agressif.
    if "cet article:" in lower_q:
        candidate = q.split(":", 1)[1].strip() if ":" in q else q
        candidate = re.sub(
            r"\b(est[- ]ce|selon sa nature|nature|mp/pdr/chimie|mp|pdr|chimie|\?)\b.*$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip(" .:-\"'")
        return [candidate] if candidate else []
    if "la matière" in lower_q or "la matiere" in lower_q:
        quoted = re.search(r"\"([^\"]+)\"", q)
        if quoted:
            candidate = quoted.group(1).strip(" .:-\"'")
            return [candidate] if candidate else []

    # Cas "liste matières": split sur virgule/point-virgule/retour ligne/tiret de liste uniquement.
    cleaned = re.sub(r"[\n;]+", ",", q)
    cleaned = re.sub(r"\s+-\s+", ",", cleaned)
    cleaned = cleaned.split(":", 1)[1] if ":" in cleaned else cleaned
    parts = [p.strip(" .:-\"'") for p in re.split(r",", cleaned)]
    blacklist = {
        "je", "veux", "veut", "classer", "classe", "classification", "matiere", "matières",
        "suivante", "suivantes", "selon", "nature", "natures", "pour", "de", "la", "le", "les",
        "mp", "pdr", "chimie", "ou",
    }
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        low = p.lower()
        if low in blacklist:
            continue
        if any(
            phrase in low
            for phrase in (
                "workflow complet",
                "controle de stock",
                "contrôle de stock",
                "donner la recette",
                "produire ",
            )
        ):
            continue
        if len(low) <= 2:
            continue
        out.append(p)
    # Déduplication en conservant l'ordre
    dedup: list[str] = []
    seen: set[str] = set()
    for p in out:
        k = _normalize_key(p)
        if k in seen:
            continue
        seen.add(k)
        dedup.append(p)
    return dedup[:20]


def _route_fallback_heuristic(question: str) -> str:
    q = (question or "").lower()
    
    # 0.  KILL SWITCH (Bouclier de sécurité pour les achats et l'admin)
    # Si la question contient ces mots, on force la route "human" immédiatement.
    mots_interdits = [r"\bcommande\b", r"\bcommander\b", r"\bfournisseur\b", r"\bacheter\b", r"\bachats?\b"]
    if any(re.search(pattern, q) for pattern in mots_interdits):
        return "human"

    explicit_classification = bool(re.search(r"\bclass(er|e|ification)\b", q))
    explicit_workflow = bool(re.search(r"\bworkflow\b", q) or re.search(r"\bcomplet\b", q))
    classification_list_style = explicit_classification and any(sep in q for sep in [":", ",", "-"])

    # Workflow combiné demandé explicitement.
    if explicit_workflow and ("class" in q and _looks_like_recipe_request(q)):
        return "workflow"

    # 1. Priorité classification si l'opérateur demande explicitement "classer ..."
    if classification_list_style or _looks_like_classification_request(q):
        return "classification"

    # 2. Recette (langage naturel)
    if _looks_like_recipe_request(q):
        return "recette"

    return "human"


@traceable(name="node_router", run_type="chain")
async def router_node(state: AgentState) -> StateUpdate:
    """Choisit la route vers classification, recette ou réponse générale."""
    q = (state.get("question_operateur") or "").strip()
    
    #  LE LASER : On encadre la question avec un ordre psychologique fort pour le LLM
    message_laser = (
        "Analyse cette question opérateur en mode ReAct et choisis la route outil.\n"
        "Ne réponds que par JSON valide.\n\n"
        f"QUESTION: \"{q}\""
        if q
        else "(question vide)"
    )

    # ---  DEBUG (À REGARDER DANS LES LOGS DOCKER) ---
    print(f"\n[DEBUG ROUTEUR] Message envoyé au LLM : \n{message_laser}")
    
    resp = await llm.ainvoke(
        [SYSTEM_PROMPT_ORCHESTRATEUR_ROUTER, HumanMessage(content=message_laser)]
    )
    content = str(resp.content if hasattr(resp, "content") else resp)
    
    # ---  DEBUG (À REGARDER DANS LES LOGS DOCKER) ---
    print(f"[DEBUG ROUTEUR] Réponse brute de Mistral 7B : {content}\n")
    
    route, _thought = _parse_route_json(content)

    # Priorité explicite utilisateur: "workflow complet" ne doit jamais tomber en classification simple.
    q_low = q.lower()
    if ("workflow" in q_low or "complet" in q_low) and ("class" in q_low and _looks_like_recipe_request(q_low)):
        route = "workflow"
    
    # --- SÉCURITÉ ALGORITHMIQUE (Fallback) ---
    if route == "human":
        fb = _route_fallback_heuristic(q)
        if fb != "human":
            route = fb
            
    print(f"[DEBUG ROUTEUR] Route finale choisie : {route}\n")
    return {"route_intent": route}


def route_after_router(
    state: AgentState,
) -> Literal["node_classification", "node_recette_exacte", "node_workflow_complet", "node_human"]:
    r = (state.get("route_intent") or "human").strip().lower()
    if r == "workflow":
        return "node_workflow_complet"
    if r == "classification":
        return "node_classification"
    if r == "recette":
        return "node_recette_exacte"
    return "node_human"


def route_after_load_inventory(
    state: AgentState,
) -> Literal["router", "node_classification", "node_recette_exacte", "node_workflow_complet", "node_human"]:
    """Si `route_intent` est déjà fixé (ex. preferred_route API), sauter le routeur LLM."""
    r = (state.get("route_intent") or "").strip().lower()
    if r == "workflow":
        return "node_workflow_complet"
    if r == "classification":
        return "node_classification"
    if r == "recette":
        return "node_recette_exacte"
    if r == "human":
        return "node_human"
    return "router"


@traceable(name="node_classification", run_type="chain")
async def node_classification(state: AgentState) -> StateUpdate:
    """Classification intelligente: support mono-article et liste de matières en langage naturel."""
    question = str(state.get("question_operateur") or "")
    materials = _extract_material_candidates(question)
    # Fallback mono-item sur description article si aucune matière explicite détectée.
    if not materials:
        fallback_desc = str(state.get("description") or "").strip()
        materials = [fallback_desc] if fallback_desc else []

    if not materials:
        return {
            "statut_classification": "INCONNU",
            "categorie_cible": "INCONNUE",
            "resultat_agent_brut": "Aucune matière à classifier détectée dans la requête.",
        }

    rows: list[dict[str, str]] = []
    mp_count = 0
    chimie_count = 0
    pdr_count = 0
    errors = 0
    first_label = "INCONNU"
    first_cat = "INCONNUE"

    for idx, material in enumerate(materials):
        stage1 = await post_pdr_mp_classification(
            state.get("id_article_erp", ""),
            material,
            state.get("categorie", ""),
        )
        if not stage1.get("ok"):
            rows.append(
                {
                    "matiere": material,
                    "stage1": "INCONNU",
                    "stage2": "N/A",
                    "final": "INCONNU",
                    "usage": "INCONNU",
                    "error": str(stage1.get("error", "ERREUR_CLASSIFICATION")),
                }
            )
            errors += 1
            continue

        stage1_label = str(stage1.get("level1", "INCONNU")).upper()
        final_label = stage1_label
        stage2_label = "N/A"
        if stage1_label == "MP":
            stage2 = await post_classification_full(
                state.get("id_article_erp", ""),
                material,
                state.get("categorie", ""),
            )
            if stage2.get("ok"):
                stage2_label = str(stage2.get("level1", "MP")).upper()
                final_label = stage2_label if stage2_label in {"MP", "CHIMIE"} else "MP"
            else:
                stage2_label = "ERROR"
                final_label = "MP"

        if final_label == "MP":
            mp_count += 1
        elif final_label == "CHIMIE":
            chimie_count += 1
        elif final_label == "PDR":
            pdr_count += 1

        usage = "UTILISABLE_PRODUCTION" if final_label in {"MP", "CHIMIE"} else "HORS_RECETTE"
        rows.append(
            {
                "matiere": material,
                "stage1": stage1_label,
                "stage2": stage2_label,
                "final": final_label,
                "usage": usage,
                "error": "",
            }
        )
        if idx == 0:
            first_label = final_label
            first_cat = str(stage1.get("categorie_principale", "") or "INCONNUE")

    lines = [
        "Classification intelligente (mode auto):",
        "| Matière | MP/PDR | MP/CHIMIE | Final | Usage production Cannelure |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['matiere']} | {row['stage1']} | {row['stage2']} | {row['final']} | {row['usage']} |"
        )
    lines.append("")
    lines.append(
        f"Résumé: MP={mp_count}, CHIMIE={chimie_count}, PDR={pdr_count}, erreurs={errors}."
    )
    brut = "\n".join(lines)

    return {
        "statut_classification": first_label,
        "categorie_cible": first_cat,
        "resultat_agent_brut": brut,
    }


def _libelle_article_recette(state: AgentState) -> str:
    """Le CSV recettes est indexé par libellé (ex. « dispersant synthetique »), pas par code ERP."""
    q = str(state.get("question_operateur") or "").strip()
    if q:
        inferred = _extract_article_from_question(q)
        if inferred:
            return inferred
        # Permet de prioriser le libellé réellement demandé dans la phrase opérateur,
        # même si le champ "description" UI garde une ancienne valeur.
        m = re.search(
            r"(?:article\s+de|article)\s+(.+?)(?:\s*(?:,|\.|$))",
            q,
            flags=re.IGNORECASE,
        )
        if m:
            candidate = str(m.group(1) or "").strip(" -:;\"'()[]")
            if candidate and len(candidate) >= 3:
                candidate_norm = _normalize_key(candidate)
                mapped = ARTICLE_ALIAS_MAP.get(candidate_norm)
                if mapped:
                    return mapped
                return candidate

    desc = (state.get("description") or "").strip()
    if desc:
        desc_norm = _normalize_key(desc)
        mapped = ARTICLE_ALIAS_MAP.get(desc_norm)
        if mapped:
            return mapped
        return desc
    return (state.get("id_article_erp") or "").strip()


def _extract_requested_tonnage(question: str) -> float:
    q = str(question or "").strip().lower()
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*(tonne|tonnes|t)\b", q)
    if not m:
        return 0.0
    return max(0.0, _to_float(m.group(1)))


class RecipeCatalogService:
    """Centralized recipe-base access and article resolution logic."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] | None = None

    def load_ratio_cache(self) -> dict[str, dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        cache: dict[str, dict[str, Any]] = {}
        try:
            df = pd.read_csv(settings.recipe_correlation_csv_path)
            for _, row in df.iterrows():
                article = str(row.get("family_pf") or "").strip()
                ingredient = str(row.get("ingredient") or "").strip()
                ratio = float(row.get("ratio_kg_per_ton") or 0.0)
                if not article or not ingredient or ratio <= 0:
                    continue
                article_norm = _normalize_key(article)
                ing_norm = _normalize_key(ingredient)
                article_bucket = cache.setdefault(
                    article_norm,
                    {"article_display": article, "ingredients": {}},
                )
                article_bucket["article_display"] = article_bucket.get("article_display") or article
                ingredients = article_bucket.setdefault("ingredients", {})
                ing_bucket = ingredients.setdefault(
                    ing_norm,
                    {"ingredient_display": ingredient, "ratios": []},
                )
                ing_bucket["ingredient_display"] = ing_bucket.get("ingredient_display") or ingredient
                ing_bucket["ratios"].append(ratio)
        except Exception:  # noqa: BLE001
            LOGGER.exception("recipe_cache: impossible de charger %s", settings.recipe_correlation_csv_path)
            self._cache = {}
            return self._cache

        resolved: dict[str, dict[str, Any]] = {}
        for article_norm, article_payload in cache.items():
            ingredients = dict(article_payload.get("ingredients") or {})
            rows: list[dict[str, Any]] = []
            for ing_norm, ing_payload in ingredients.items():
                values = list(ing_payload.get("ratios") or [])
                if not values:
                    continue
                median = float(pd.Series(values).median())
                rows.append(
                    {
                        "ingredient_norm": ing_norm,
                        "ingredient_display": str(ing_payload.get("ingredient_display") or ing_norm),
                        "ratio_kg_per_ton": median,
                    }
                )
            resolved[article_norm] = {
                "article_norm": article_norm,
                "article_display": str(article_payload.get("article_display") or article_norm),
                "rows": sorted(rows, key=lambda x: float(x.get("ratio_kg_per_ton", 0.0)), reverse=True),
            }
        self._cache = resolved
        return self._cache

    def resolve_article_payload(self, article: str) -> dict[str, Any] | None:
        cache = self.load_ratio_cache()
        article_norm = _normalize_key(article)
        if article_norm in cache:
            return dict(cache[article_norm])
        mapped = ARTICLE_ALIAS_MAP.get(article_norm)
        if mapped:
            mapped_norm = _normalize_key(mapped)
            if mapped_norm in cache:
                return dict(cache[mapped_norm])
        candidates = list(cache.keys())
        close = get_close_matches(article_norm, candidates, n=1, cutoff=0.6)
        if close:
            return dict(cache[close[0]])
        for cand in candidates:
            if article_norm and (article_norm in cand or cand in article_norm):
                return dict(cache[cand])
        return None

    def extract_article_from_question(self, question: str) -> str:
        q = str(question or "").strip()
        if not q:
            return ""
        q_norm = _normalize_key(q)
        for alias_norm, canonical in ARTICLE_ALIAS_MAP.items():
            if alias_norm and alias_norm in q_norm:
                return canonical
        cache = self.load_ratio_cache()
        best_article = ""
        best_score = 0.0
        for article_norm, payload in cache.items():
            if not article_norm:
                continue
            score = 0.0
            if article_norm in q_norm:
                score = float(len(article_norm))
            else:
                ratio = SequenceMatcher(None, article_norm, q_norm).ratio()
                if ratio >= 0.62:
                    score = ratio * 100.0
            if score > best_score:
                best_score = score
                best_article = str(payload.get("article_display") or article_norm)
        return best_article

    def fallback_recipe_from_csv(self, article: str, requested_tonnage: float) -> tuple[str, list[dict[str, Any]]]:
        if requested_tonnage <= 0:
            requested_tonnage = 1.0
        payload = self.resolve_article_payload(article)
        rows = list((payload or {}).get("rows") or [])
        if not rows:
            return "", []
        article_display = str((payload or {}).get("article_display") or article)
        items: list[dict[str, Any]] = []
        lines: list[str] = []
        # Évite le double comptage des ratios globaux quand des sous-composants existent.
        norms = {
            _normalize_key(str(row.get("ingredient_norm") or row.get("ingredient_display") or ""))
            for row in rows
        }
        has_waste = "waste paper ratio" in norms
        has_standard_pulp = "standard pulp ratio" in norms
        has_flocon_pulp = "flocon pulp ratio" in norms
        for idx, row in enumerate(rows, start=1):
            ratio_kg_per_ton = float(row.get("ratio_kg_per_ton", 0.0) or 0.0)
            ingredient_raw = str(row.get("ingredient_display") or row.get("ingredient_norm") or "").strip()
            ingredient_norm = _normalize_key(ingredient_raw)
            # "Fiber ratio" et "Pulp Ratio" sont des agrégats; si on a le détail, on les ignore.
            if ingredient_norm == "fiber ratio" and has_waste:
                continue
            if ingredient_norm == "pulp ratio" and (has_standard_pulp or has_flocon_pulp):
                continue
            ingredient = _canonical_ingredient_name(ingredient_raw)
            if not ingredient or ratio_kg_per_ton <= 0:
                continue
            required_kg = ratio_kg_per_ton * requested_tonnage
            lines.append(f"{idx} - {ingredient} : {required_kg:.3f} kg")
            items.append(
                {
                    "ingredient": ingredient,
                    "required_value": required_kg,
                    "required_unit": "kg",
                    "required_kg": required_kg,
                }
            )
        brut = (
            f"Recette base réelle (CSV) pour '{article_display}' - {requested_tonnage:.3f} tonnes\n"
            + "\n".join(lines)
        ).strip()
        return brut, items


RECIPE_CATALOG = RecipeCatalogService()


class RecipeExtractionService:
    """Structured extraction flow: base-first, LLM fallback."""

    async def extract(self, state: AgentState) -> tuple[str, list[dict[str, Any]], str, float]:
        q = str(state.get("question_operateur") or "")
        libelle = _libelle_article_recette(state)
        tonnage = _extract_requested_tonnage(q)
        texte = (
            "TÂCHE : Extraire la recette pour UN SEUL article.\n\n"
            "--- CONTRAINTES STRICTES ---\n"
            f"Article canonique (exact): {libelle}\n"
            f"Référence ERP: {state['id_article_erp']}\n"
            f"Tonnage demandé: {tonnage:.3f} tonnes\n\n"
            "Interdiction: ne pas reformuler/traduire le nom article, ne pas en choisir un autre.\n"
            "Chercher uniquement cet article exact dans la base recette et retourner les ingrédients/quantités.\n\n"
            f"Question opérateur (contexte): {q}"
        ).strip()

        brut, recipe_items = _fallback_recipe_from_csv(libelle, tonnage)
        if recipe_items:
            return brut, recipe_items, libelle, tonnage

        out = await post_recette_exacte(texte)
        if not out.get("ok"):
            return f"Erreur agent recette: {out.get('error', 'inconnue')}", [], libelle, tonnage

        brut = str(out.get("result", ""))
        recipe_items = _parse_recipe_items(brut)
        if not recipe_items:
            fallback_brut, fallback_items = _fallback_recipe_from_csv(libelle, tonnage)
            if fallback_items:
                return fallback_brut, fallback_items, libelle, tonnage
        return brut, recipe_items, libelle, tonnage


RECIPE_EXTRACTOR = RecipeExtractionService()


def _load_recipe_ratio_cache() -> dict[str, dict[str, Any]]:
    return RECIPE_CATALOG.load_ratio_cache()


def _resolve_recipe_article_payload(article: str) -> dict[str, Any] | None:
    return RECIPE_CATALOG.resolve_article_payload(article)


def _extract_article_from_question(question: str) -> str:
    return RECIPE_CATALOG.extract_article_from_question(question)


def _fallback_recipe_from_csv(article: str, requested_tonnage: float) -> tuple[str, list[dict[str, Any]]]:
    return RECIPE_CATALOG.fallback_recipe_from_csv(article, requested_tonnage)


@traceable(name="node_recette_exacte", run_type="chain")
async def node_recette_exacte(state: AgentState) -> StateUpdate:
    """Délègue au microservice Agent Recette Exacte avec des instructions strictes."""
    brut, recipe_items, _libelle, _tonnage = await RECIPE_EXTRACTOR.extract(state)
    recipe = {"raw_text": brut, "items": recipe_items}
    alerts = _build_stock_alerts(recipe_items, dict(state.get("inventory") or {}))
        
    return {
        "statut_classification": "N/A",
        "categorie_cible": "N/A",
        "resultat_agent_brut": brut,
        "recipe": recipe,
        "stock_alerts": alerts,
    }


@traceable(name="node_workflow_complet", run_type="chain")
async def node_workflow_complet(state: AgentState) -> StateUpdate:
    """
    Workflow combiné :
    1) MP/PDR, 2) si MP -> MP/CHIMIE, 3) recette, 4) alertes stock.
    """
    id_article = str(state.get("id_article_erp") or "")
    description = str(state.get("description") or "")
    categorie = str(state.get("categorie") or "")

    stage1 = await post_pdr_mp_classification(id_article, description, categorie)
    stage1_label = "INCONNU"
    stage2_label = "N/A"
    categorie_cible = ""
    classif_error = ""

    if not stage1.get("ok"):
        classif_error = str(stage1.get("error", "ERROR_STAGE1_MP_PDR"))
    else:
        stage1_label = str(stage1.get("level1", "INCONNU")).upper()
        categorie_cible = str(stage1.get("categorie_principale", "")).strip()
        if stage1_label == "MP":
            stage2 = await post_classification_full(id_article, description, categorie)
            if not stage2.get("ok"):
                classif_error = str(stage2.get("error", "ERROR_STAGE2_MP_CHIMIE"))
                stage2_label = "ERROR"
            else:
                stage2_label = str(stage2.get("level1", "INCONNU")).upper()
                if not categorie_cible:
                    categorie_cible = str(stage2.get("categorie_principale", "")).strip()

    final_label = stage2_label if stage1_label == "MP" else stage1_label
    if final_label in {"N/A", "ERROR", "INCONNU", ""}:
        final_label = stage1_label

    brut_recette, recipe_items, _libelle, _tonnage = await RECIPE_EXTRACTOR.extract(state)
    recipe = {"raw_text": brut_recette, "items": recipe_items}
    alerts = _build_stock_alerts(recipe_items, dict(state.get("inventory") or {}))

    brut = (
        "Workflow outils exécuté\n"
        f"- Stage1 MP/PDR: {stage1_label}\n"
        f"- Stage2 MP/CHIMIE: {stage2_label}\n"
        f"- Erreur classification: {classif_error or 'Aucune'}\n\n"
        f"Résultat recette:\n{brut_recette}"
    )
    return {
        "route_intent": "workflow",
        "statut_classification": final_label or "INCONNU",
        "categorie_cible": categorie_cible or "INCONNUE",
        "resultat_agent_brut": brut,
        "recipe": recipe,
        "stock_alerts": alerts,
        "workflow_stage1_label": stage1_label,
        "workflow_stage2_label": stage2_label,
    }


@traceable(name="node_human", run_type="chain")
async def node_human(state: AgentState) -> StateUpdate:
    """Réponse générale sans déléguer classification/recette."""
    q = state.get("question_operateur") or ""
    resp = await llm.ainvoke([SYSTEM_PROMPT_HUMAN, HumanMessage(content=q)])
    if not isinstance(resp, AIMessage):
        resp = AIMessage(content=str(resp))
    content = str(resp.content or "")
    return {"messages": [resp], "resultat_agent_brut": "", "final_response": content}


@traceable(name="node_supervisor", run_type="chain")
async def node_supervisor(state: AgentState) -> StateUpdate:
    """
    Nœud 4 — Supervisor LLM :
    rédige la réponse finale et déclenche les alertes de production selon
    les résultats du nœud 3 (stock_alerts).
    """
    route_intent = str(state.get("route_intent") or "")
    alerts = list(state.get("stock_alerts") or [])
    recipe = dict(state.get("recipe") or {})
    raw_items = recipe.get("items")
    recipe_items = list(raw_items) if isinstance(raw_items, list) else []
    confirm_production = bool(state.get("confirm_production") or False)
    confirmation_token_input = str(state.get("confirmation_token_input") or "").strip()
    confirmation_token = ""
    confirmation_required = False
    production_applied = False
    updated_inventory = dict(state.get("inventory") or {})
    updated_dashboard = dict(state.get("inventory_dashboard") or {})
    movements: list[dict[str, Any]] = []
    production_capacity: dict[str, Any] = {}
    stock_prediction: dict[str, Any] = {}

    has_alerts = len(alerts) > 0
    tonnage = _extract_requested_tonnage(str(state.get("question_operateur") or ""))
    if recipe_items:
        production_capacity = _estimate_production_capacity(recipe_items, updated_inventory, tonnage)
    # Keep collecting supervised time-series points even when stock is unchanged.
    # This allows the ML sub-agent to retrain from interaction timeline, not only consumption events.
    _record_stock_prediction_point(updated_dashboard, reason=f"supervisor_tick:{route_intent or 'unknown'}", force=True)
    stock_prediction = _build_stock_prediction()
    LOGGER.info(
        "node_supervisor:start route=%s stock_alerts=%s confirm=%s",
        route_intent,
        len(alerts),
        confirm_production,
    )

    can_confirm_production_flow = route_intent in {"recette", "workflow"} and bool(recipe_items) and not has_alerts

    if can_confirm_production_flow:
        confirmation_token = _build_confirmation_token(state, recipe_items)
        confirmation_required = not production_applied

    # Logique d'application stock : route recette, sans alerte, confirmation=true + token valide + non consommé.
    if can_confirm_production_flow:
        if not confirm_production:
            alert_mode = "EN_ATTENTE_CONFIRMATION"
            confirmation_required = True
        elif not confirmation_token_input:
            alert_mode = "TOKEN_REQUIS"
            confirmation_required = True
        elif confirmation_token_input != confirmation_token:
            alert_mode = "TOKEN_INVALIDE"
            confirmation_required = True
        else:
            async with TOKEN_LOCK, INVENTORY_LOCK:
                if confirmation_token in CONSUMED_CONFIRMATION_TOKENS:
                    alert_mode = "TOKEN_DEJA_CONSOMME"
                    confirmation_required = False
                else:
                    updated_inventory, movements = _apply_consumption(updated_inventory, recipe_items)
                    updated_dashboard = _refresh_dashboard(
                        updated_dashboard,
                        updated_inventory,
                        movements,
                        INVENTORY_LABEL_CACHE or {},
                    )
                    production_applied = True
                    production_capacity = _estimate_production_capacity(
                        recipe_items, updated_inventory, tonnage
                    )
                    CONSUMED_CONFIRMATION_TOKENS.add(confirmation_token)
                    # Persistance en mémoire du stock courant (scope process)
                    global INVENTORY_CACHE, DASHBOARD_CACHE
                    INVENTORY_CACHE = dict(updated_inventory)
                    DASHBOARD_CACHE = dict(updated_dashboard)
                    _record_stock_prediction_point(DASHBOARD_CACHE, reason="production_applied")
                    stock_prediction = _build_stock_prediction()
                    alert_mode = "VALIDATION_PRODUCTION"
                    confirmation_required = False
                    LOGGER.info("node_supervisor:consumption_applied movements=%s", len(movements))
    else:
        if route_intent == "recette" and not recipe_items:
            alert_mode = "ECHEC_RECETTE"
        else:
            alert_mode = "ALERTE_PRODUCTION" if has_alerts else "VALIDATION_PRODUCTION"

    bloc = {
        "id_article_erp": state.get("id_article_erp", ""),
        "description": state.get("description", ""),
        "categorie": state.get("categorie", ""),
        "question_operateur": state.get("question_operateur", ""),
        "route_intent": route_intent,
        "statut_classification": state.get("statut_classification", ""),
        "categorie_cible": state.get("categorie_cible", ""),
        "resultat_agent_brut": state.get("resultat_agent_brut", ""),
        "recipe": recipe,
        "stock_alerts": alerts,
        "confirm_production": confirm_production,
        "confirmation_token_input": confirmation_token_input,
        "confirmation_token": confirmation_token,
        "confirmation_required": confirmation_required,
        "production_applied": production_applied,
        "inventory_dashboard": updated_dashboard,
        "movements": movements,
        "mode": alert_mode,
        "stock_prediction": stock_prediction,
    }
    critical_alerts = [a for a in alerts if str(a.get("severity", "")).lower() == "critical"]
    supervisor_view = {
        "id_article_erp": bloc["id_article_erp"],
        "description": bloc["description"],
        "question_operateur": bloc["question_operateur"],
        "mode": bloc["mode"],
        "recipe_items": recipe_items,
        "critical_stock_alerts": critical_alerts,
        "confirmation_required": confirmation_required,
        "production_applied": production_applied,
        "movements": movements,
    }

    if route_intent == "workflow":
        stage1_label = str(state.get("workflow_stage1_label") or "INCONNU")
        stage2_label = str(state.get("workflow_stage2_label") or "N/A")
        title = "ALERTE PRODUCTION" if has_alerts else "VALIDATION PRODUCTION"
        recipe_table = _format_recipe_table(recipe_items)
        stock_block = _format_stock_alert_lines(alerts)
        content_parts = [
            f"Titre : {title}",
            "",
            "Workflow complet exécuté (classification -> recette -> stock).",
            "Tools activés:",
            f"- Tool Classification MP/PDR: {stage1_label}",
            f"- Tool Classification MP/CHIMIE (si MP): {stage2_label}",
            "- Tool Recette: exécuté",
            "- Tool Contrôle stock: exécuté",
            "",
        ]
        if recipe_table:
            content_parts.append(recipe_table)
            content_parts.append("")
        content_parts.append(stock_block)
        content = "\n".join(content_parts).strip()
        resp = AIMessage(content=content)
        LOGGER.info("node_supervisor:done mode=%s", alert_mode)
        return {
            "messages": [resp],
            "final_response": content,
            "confirmation_token": confirmation_token,
            "confirmation_required": confirmation_required,
            "production_applied": production_applied,
            "inventory": updated_inventory,
            "inventory_dashboard": updated_dashboard,
            "production_capacity": production_capacity,
            "stock_prediction": stock_prediction,
        }

    if route_intent == "classification":
        content = (
            "Titre : CLASSIFICATION MATIÈRES\n\n"
            f"{str(state.get('resultat_agent_brut') or '').strip()}\n\n"
            "Note: en mode auto, le système classe les matières demandées et indique leur usage production."
        ).strip()
        resp = AIMessage(content=content)
        return {
            "messages": [resp],
            "final_response": content,
            "confirmation_token": "",
            "confirmation_required": False,
            "production_applied": False,
            "inventory": updated_inventory,
            "inventory_dashboard": updated_dashboard,
            "production_capacity": production_capacity,
            "stock_prediction": stock_prediction,
        }

    if route_intent == "recette" and not recipe_items:
        brut = str(state.get("resultat_agent_brut") or "").strip()
        detail = brut or "Recette indisponible pour cet article (aucun ratio exploitable trouvé)."
        content = (
            "Titre : ECHEC EXTRACTION RECETTE\n\n"
            "Impossible de générer une recette exploitable pour cette demande.\n"
            f"Détail: {detail}\n\n"
            "Actions recommandées:\n"
            "- Vérifier le libellé article ERP (ex: Cannelure/Fluting exact),\n"
            "- Reformuler la demande avec le nom article présent dans la base recette,\n"
            "- Utiliser le workflow complet si vous voulez classification + recette + stock."
        ).strip()
        resp = AIMessage(content=content)
        return {
            "messages": [resp],
            "final_response": content,
            "confirmation_token": "",
            "confirmation_required": False,
            "production_applied": False,
            "inventory": updated_inventory,
            "inventory_dashboard": updated_dashboard,
            "production_capacity": production_capacity,
            "stock_prediction": stock_prediction,
        }

    system_supervisor = SystemMessage(
        content=(
            "Tu es le superviseur industriel Sotipapier.\n"
            "Tu dois répondre impérativement en français.\n"
            "Concentre-toi uniquement sur les alertes de stock critiques pour l'opérateur.\n"
            "Ne mentionne jamais les métadonnées techniques (nom de fichier source, nombre de lignes, pipeline, etc.).\n"
            "Pas de JSON, pas de markdown complexe, réponse courte orientée action atelier.\n"
            "Si mode=EN_ATTENTE_CONFIRMATION :\n"
            "- Réponds avec un titre 'CONFIRMATION REQUISE'.\n"
            "- Résume la recette, les consommations prévues et demande confirmation explicite.\n"
            "- Précise que le stock sera décrémenté uniquement après confirmation.\n"
            "Si mode=TOKEN_REQUIS :\n"
            "- Réponds 'TOKEN REQUIS' et demande de fournir confirmation_token avec confirm_production=true.\n"
            "Si mode=TOKEN_INVALIDE :\n"
            "- Réponds 'TOKEN INVALIDE' et demande de reprendre le token retourné par l'étape de confirmation.\n"
            "Si mode=TOKEN_DEJA_CONSOMME :\n"
            "- Réponds 'TOKEN DEJA UTILISE'.\n"
            "- Indique qu'aucune nouvelle décrémentation ne sera appliquée pour éviter le double comptage.\n"
            "Si mode=ALERTE_PRODUCTION ou si stock_alerts non vide :\n"
            "- Réponds avec un titre clair 'ALERTE PRODUCTION'.\n"
            "- Liste les ingrédients en rupture/insuffisance avec manque estimé.\n"
            "- Propose des actions immédiates (réapprovisionnement, substitution, réduction tonnage).\n"
            "Sinon :\n"
            "- Réponds avec un titre 'VALIDATION PRODUCTION'.\n"
            "- Confirme que la commande peut être lancée.\n"
            "- Si production_applied=true, mentionne que la décrémentation du stock est déjà appliquée.\n"
            "- Donne un mini-résumé opérationnel en français.\n"
            "Reste factuel, concis et orienté atelier."
        )
    )
    human_supervisor = HumanMessage(
        content=(
            "Contexte opérationnel:\n"
            f"{json.dumps(supervisor_view, ensure_ascii=False, indent=2)}"
        )
    )

    try:
        resp = await llm.ainvoke([system_supervisor, human_supervisor])
        if not isinstance(resp, AIMessage):
            resp = AIMessage(content=str(resp))
        content = str(resp.content or "").strip()
        if not content:
            raise ValueError("Réponse superviseur vide")
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("node_supervisor:error")
        if alert_mode == "EN_ATTENTE_CONFIRMATION":
            content = (
                "CONFIRMATION REQUISE\n"
                "La recette est prête et le stock est suffisant. "
                "Confirmez la production (confirm_production=true) avec le confirmation_token pour décrémenter le stock."
            )
        elif alert_mode == "TOKEN_REQUIS":
            content = (
                "TOKEN REQUIS\n"
                "Veuillez fournir confirmation_token avec confirm_production=true pour exécuter la production."
            )
        elif alert_mode == "TOKEN_INVALIDE":
            content = (
                "TOKEN INVALIDE\n"
                "Le token de confirmation ne correspond pas à la commande en attente."
            )
        elif alert_mode == "TOKEN_DEJA_CONSOMME":
            content = (
                "TOKEN DEJA UTILISE\n"
                "Cette commande a déjà été appliquée. Aucun second décrément de stock n'est autorisé."
            )
        elif has_alerts:
            content = (
                "ALERTE PRODUCTION\n"
                f"Le contrôle stock détecte {len(alerts)} alerte(s). "
                "Lancer un réapprovisionnement avant démarrage."
            )
        else:
            content = (
                "VALIDATION PRODUCTION\n"
                "Aucune alerte de stock détectée. Commande validée pour exécution."
            )
            if production_applied:
                content += " Décrémentation stock appliquée."
        content += f"\n[Détail technique: {exc}]"
        resp = AIMessage(content=content)

    # Ajoute une trace explicite d'activation des tools + tableau recette lisible opérateur.
    if route_intent in {"recette", "workflow"}:
        recipe_table = _format_recipe_table(recipe_items)
        stock_block = _format_stock_alert_lines(alerts)
        if route_intent == "workflow":
            stage1_label = str(state.get("workflow_stage1_label") or "INCONNU")
            stage2_label = str(state.get("workflow_stage2_label") or "N/A")
            tools_block = (
                "Tools activés:\n"
                f"- Tool Classification MP/PDR: {stage1_label}\n"
                f"- Tool Classification MP/CHIMIE (si MP): {stage2_label}\n"
                "- Tool Recette: exécuté\n"
                "- Tool Contrôle stock: exécuté"
            )
        else:
            tools_block = (
                "Tools activés:\n"
                "- Tool Recette: exécuté\n"
                "- Tool Contrôle stock: exécuté"
            )
        extras = [tools_block]
        if recipe_table:
            extras.append(recipe_table)
        extras.append(stock_block)
        content = f"{content}\n\n" + "\n\n".join(extras)
        resp = AIMessage(content=content)

    LOGGER.info("node_supervisor:done mode=%s", alert_mode)
    return {
        "messages": [resp],
        "final_response": content,
        "confirmation_token": confirmation_token,
        "confirmation_required": confirmation_required,
        "production_applied": production_applied,
        "inventory": updated_inventory,
        "inventory_dashboard": updated_dashboard,
        "production_capacity": production_capacity,
        "stock_prediction": stock_prediction,
    }


workflow = StateGraph(AgentState)
workflow.add_node("node_load_inventory", node_load_inventory)
workflow.add_node("router", router_node)
workflow.add_node("node_classification", node_classification)
workflow.add_node("node_recette_exacte", node_recette_exacte)
workflow.add_node("node_workflow_complet", node_workflow_complet)
workflow.add_node("node_human", node_human)
workflow.add_node("node_supervisor", node_supervisor)

workflow.add_edge(START, "node_load_inventory")
workflow.add_conditional_edges(
    "node_load_inventory",
    route_after_load_inventory,
    {
        "router": "router",
        "node_classification": "node_classification",
        "node_recette_exacte": "node_recette_exacte",
        "node_workflow_complet": "node_workflow_complet",
        "node_human": "node_human",
    },
)
workflow.add_conditional_edges(
    "router",
    route_after_router,
    {
        "node_classification": "node_classification",
        "node_recette_exacte": "node_recette_exacte",
        "node_workflow_complet": "node_workflow_complet",
        "node_human": "node_human",
    },
)
workflow.add_edge("node_classification", "node_supervisor")
workflow.add_edge("node_recette_exacte", "node_supervisor")
workflow.add_edge("node_workflow_complet", "node_supervisor")
workflow.add_edge("node_supervisor", END)
workflow.add_edge("node_human", END)

brain_app = workflow.compile()
