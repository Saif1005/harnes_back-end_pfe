from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches
from typing import Any

ARTICLE_ALIAS_MAP: dict[str, str] = {
    "kraft pour sacs": "Kraft pour sacs",
    "kraft for sacs": "Kraft pour sacs",
    "cannelure": "Cannelure (Fluting)",
    "fluting": "Cannelure (Fluting)",
    "cannelure fluting": "Cannelure (Fluting)",
    "testliner": "TestLiner",
    "testliner colore": "TestLiner Coloré",
    "testliner coloree": "TestLiner Coloré",
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

INGREDIENT_ALIAS_MAP: dict[str, list[str]] = {
    "biocide": ["sanikem 522", "biocide"],
    "antimousse afranil": ["afranil", "antimousse", "anti-mousse", "defoamer"],
    "agent de retention": ["retention", "nalco core shell"],
    "polymere krofta": ["polymer", "krofta", "intrabond", "carbofloc"],
    "amidon cationique": ["amidon", "cationique", "carbofloc"],
    "amidon oxyde": ["amidon oxyde", "oxidized starch"],
    "waste paper ratio": ["vieux papier", "waste paper", "papier recycle"],
    "standard pulp ratio": ["pate standard", "standard pulp", "pulp"],
    "flocon pulp ratio": ["pate flocon", "flocon pulp", "pulp"],
}


def normalize_key(value: str) -> str:
    raw = (value or "").strip().lower()
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", raw)


def to_float(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    raw = raw.replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def canonical_ingredient_name(raw_ingredient: str) -> str:
    raw = str(raw_ingredient or "").strip()
    if not raw:
        return ""
    return INGREDIENT_DISPLAY_MAP.get(normalize_key(raw), raw)


def extract_requested_tonnage(question: str) -> float:
    q = str(question or "")
    m = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(t|tonne|tonnes|kg)\b", q, flags=re.IGNORECASE)
    if not m:
        return 1.0
    value = to_float(m.group(1))
    unit = str(m.group(2)).lower()
    if unit == "kg":
        return max(0.001, value / 1000.0)
    return max(0.001, value)


def extract_article_from_question(question: str) -> str:
    q_norm = normalize_key(question)
    for alias, canonical in ARTICLE_ALIAS_MAP.items():
        if normalize_key(alias) in q_norm:
            return canonical
    return "Kraft pour sacs"


def parse_recipe_items(raw_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^\s*\d+\s*-\s*(.+?)\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*(kg|tonne|tonnes|t)\b",
        re.IGNORECASE,
    )
    for line in (raw_text or "").splitlines():
        match = pattern.search(line.strip())
        if not match:
            continue
        ingredient = canonical_ingredient_name(str(match.group(1)).strip())
        value = to_float(match.group(2))
        unit_raw = str(match.group(3)).strip().lower()
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


def find_inventory_match(ingredient: str, inventory: dict[str, float]) -> tuple[str | None, float]:
    if not inventory:
        return None, 0.0
    normalized_to_original = {normalize_key(key): key for key in inventory.keys()}
    ing_norm = normalize_key(ingredient)
    if ing_norm in normalized_to_original:
        key = normalized_to_original[ing_norm]
        return key, float(inventory.get(key, 0.0))

    inv_norm_keys = list(normalized_to_original.keys())
    alias_candidates = INGREDIENT_ALIAS_MAP.get(ing_norm, [])
    alias_matches: list[str] = []
    for alias in alias_candidates:
        alias_norm = normalize_key(alias)
        for inv_norm in inv_norm_keys:
            if alias_norm and (alias_norm in inv_norm or inv_norm in alias_norm):
                alias_matches.append(inv_norm)
    if alias_matches:
        best_norm = max(alias_matches, key=lambda n: float(inventory.get(normalized_to_original.get(n, ""), 0.0)))
        best_key = normalized_to_original[best_norm]
        return best_key, float(inventory.get(best_key, 0.0))

    close_norm = get_close_matches(ing_norm, inv_norm_keys, n=5, cutoff=0.52)
    if close_norm:
        best_norm = max(close_norm, key=lambda c: SequenceMatcher(None, ing_norm, c).ratio())
        best_key = normalized_to_original[best_norm]
        return best_key, float(inventory.get(best_key, 0.0))
    return None, 0.0


def build_stock_alerts(recipe_items: list[dict[str, Any]], inventory: dict[str, float]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for item in recipe_items:
        ingredient = str(item.get("ingredient", "")).strip()
        required = float(item.get("required_kg", item.get("quantity_kg", 0.0)) or 0.0)
        if not ingredient or required <= 0:
            continue
        matched_key, available = find_inventory_match(ingredient, inventory)
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


def estimate_production_capacity(
    recipe_items: list[dict[str, Any]], inventory: dict[str, float], requested_tonnage: float
) -> dict[str, Any]:
    effective_tonnage = requested_tonnage if requested_tonnage > 0 else 1.0
    per_ingredient: list[dict[str, Any]] = []
    for item in recipe_items:
        ingredient = str(item.get("ingredient", "")).strip()
        required_kg = float(item.get("required_kg", item.get("quantity_kg", 0.0)) or 0.0)
        if not ingredient or required_kg <= 0:
            continue
        required_per_ton_kg = required_kg / effective_tonnage
        if required_per_ton_kg <= 0:
            continue
        matched_key, available_kg = find_inventory_match(ingredient, inventory)
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
        "max_producible_tonnage": round(max_tons, 3),
        "full_orders_possible": max(0, full_orders),
        "limiting_ingredient": str(limiting.get("ingredient") or ""),
    }


def format_recipe_table(recipe_items: list[dict[str, Any]]) -> str:
    if not recipe_items:
        return ""
    lines = [
        "Table recette (valeurs issues du tool recette):",
        "| Ingrédient | Quantité requise |",
        "|---|---|",
    ]
    for item in recipe_items[:20]:
        ingredient = str(item.get("ingredient", "")).strip() or "-"
        req_kg = float(item.get("required_kg", item.get("quantity_kg", 0.0)) or 0.0)
        qty = f"{req_kg/1000.0:.3f} t ({req_kg:.2f} kg)" if req_kg >= 1000 else f"{req_kg:.2f} kg"
        lines.append(f"| {ingredient} | {qty} |")
    return "\n".join(lines)


def route_fallback_heuristic(question: str) -> str:
    q = (question or "").lower().strip()
    if not q:
        return "human"
    if any(re.search(pattern, q) for pattern in (r"\bclass(er|e|ification)\b", r"\bmp\b", r"\bchimie\b", r"\bpdr\b")):
        return "classification"
    if any(k in q for k in ("recette", "produire", "production", "tonne", "tonnes", "tonnage", "kg", "dosage")):
        return "recette"
    return "human"

