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
    "defoamer 1 (afranil)": "Antimousse afranil",
    "defoamer 2 (erol)": "Antimousse erol",
    "wet end starch ratio": "Wet end starch",
    "wet end ratio": "Wet end starch",
    "wet end": "Wet end starch",
    "retention aids ratio": "Agent de retention",
    "krofta polymer ratio": "Polymere krofta",
    "prestige cleaning aids ratio (prestige)": "Prestige",
    "pulp ratio": "Pate papier",
    "standard pulp ratio": "Pate standard",
    "flocon pulp ratio": "Pate flocon",
    "sizing kraft (agent collage asa)": "Agent collage ASA",
}

INGREDIENT_ALIAS_MAP: dict[str, list[str]] = {
    "biocide": ["sanikem 522", "biocide", "sanikem"],
    "antimousse afranil": ["afranil", "antimousse", "anti-mousse", "defoamer", "erol", "afranil/erol"],
    # Même SKU magasin « Antimousse (Afranil/Erol) », consommation cumulative sur les deux lignes recette.
    "antimousse erol": ["erol", "afranil", "antimousse", "anti-mousse", "defoamer", "afranil/erol"],
    "agent de retention": ["retention", "nalco core shell", "rétention"],
    "wet end starch": ["sizing", "ppo", "asa", "wet end adjuv"],
    "polymere krofta": ["polymer", "krofta", "intrabond", "carbofloc", "polymere"],
    "amidon cationique": ["amidon", "cationique", "carbofloc"],
    "amidon oxyde": ["amidon oxyde", "oxidized starch", "surface"],
    "waste paper ratio": ["vieux papier", "waste paper", "papier recycle"],
    "standard pulp ratio": ["pate standard", "standard pulp", "pulp"],
    "flocon pulp ratio": ["pate flocon", "flocon pulp", "pulp"],
    # Libellés canoniques (DISPLAY_MAP) ↔ tokens désignations magasin officielles
    "vieux papier": ["vieux papiers", "vieux papier", "waste paper", "fibres", "waste"],
    "pate standard": ["standard pulp"],
    "pate flocon": ["flocon pulp", "flocon"],
    "pate papier": ["standard pulp", "flocon pulp"],
    "agent collage asa": ["sizing", "ppo", "asa", "collage"],
    # Libre recette sans entrée ERP « collage » séparée : proximité fonctionnelle avec sizing ASA.
    "agent de collage": ["sizing", "ppo", "asa", "/ asa"],
    "prestige": ["prestige", "cleaning"],
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


def _ingredient_search_terms(ing_norm: str) -> set[str]:
    terms: set[str] = {ing_norm}
    alias_lists: list[list[str]] = []
    if ing_norm in INGREDIENT_ALIAS_MAP:
        alias_lists.append(INGREDIENT_ALIAS_MAP[ing_norm])
    for fk, cand_aliases in INGREDIENT_ALIAS_MAP.items():
        disp = INGREDIENT_DISPLAY_MAP.get(fk)
        if disp and normalize_key(str(disp)) == ing_norm:
            alias_lists.append(cand_aliases)
    for cand in alias_lists:
        for alias in cand:
            an = normalize_key(alias)
            if len(an) >= 3:
                terms.add(an)
            raw = str(alias).strip().lower()
            if len(raw) >= 3:
                terms.add(raw)
    return {t for t in terms if t}


def _label_match_bonus(ing_norm: str, label_raw: str) -> float:
    lu = label_raw.upper()
    bonus = 0.0
    if lu == "CHIMIE" and any(
        x in ing_norm
        for x in (
            "amidon",
            "biocide",
            "pac",
            "ppo",
            "soude",
            "acide",
            "retention",
            "antimousse",
            "prestige",
            "krofta",
            "asa",
            "sizing",
        )
    ):
        bonus += 18.0
    if lu == "MP" and any(
        x in ing_norm for x in ("flocon", "pate standard", "pate flocon", "vieux", "pate papier", "fibres")
    ):
        bonus += 18.0
    return bonus


# Jetons trop fréquents → faux positifs (ex : « Agent de Rétention » vs « agent de collage »).
_LOW_SIGNAL_INGREDIENT_TOKENS = frozenset({"agent"})


def _reject_display_for_ingredient(ing_norm: str, disp_norm: str) -> bool:
    """Évite les confusions majeures entre familles proches (collage / rétention)."""
    if "agent de retention" in ing_norm or ing_norm.endswith(" retention"):
        return "retention" not in disp_norm
    if ing_norm == "agent de collage" or ing_norm.startswith("agent de collage "):
        if "retention" in disp_norm and "sizing" not in disp_norm and "ppo" not in disp_norm:
            return True
    return False


def _display_match_score(ing_norm: str, disp_norm: str, search_terms: set[str]) -> float:
    if not disp_norm:
        return 0.0
    best = 0.0
    for term in search_terms:
        if len(term) < 3:
            continue
        if term in disp_norm:
            best = max(best, 95.0 + float(min(len(term), 36)))
    ratio = SequenceMatcher(None, ing_norm, disp_norm).ratio()
    if ratio >= 0.38:
        best = max(best, ratio * 72.0)
    for tok in ing_norm.split():
        if len(tok) < 4 or tok in _LOW_SIGNAL_INGREDIENT_TOKENS:
            continue
        if tok in disp_norm:
            best += 14.0
    return best


def find_inventory_match(
    ingredient: str,
    inventory: dict[str, float],
    displays: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
) -> tuple[str | None, float]:
    """Match recipe ingredient labels to ERP material_key using optional display names (stock SQL)."""
    if not inventory:
        return None, 0.0
    normalized_to_original = {normalize_key(key): key for key in inventory.keys()}
    raw_ing = str(ingredient or "").strip()
    ingredient_eff = (canonical_ingredient_name(raw_ing) or raw_ing).strip()
    ing_norm = normalize_key(ingredient_eff)
    if ing_norm in normalized_to_original:
        key = normalized_to_original[ing_norm]
        return key, float(inventory.get(key, 0.0))

    search_terms = _ingredient_search_terms(ing_norm)

    if displays:
        best_key: str | None = None
        best_pair = (-1.0, -1.0)
        disp_min_score = 40.0
        for mk, qty in inventory.items():
            dn_raw = displays.get(mk, "") or ""
            dn = normalize_key(dn_raw)
            if not dn:
                continue
            if _reject_display_for_ingredient(ing_norm, dn):
                continue
            score = _display_match_score(ing_norm, dn, search_terms)
            if labels:
                score += _label_match_bonus(ing_norm, str(labels.get(mk, "")))
            if score < disp_min_score:
                continue
            pair = (score, float(qty))
            if pair > best_pair:
                best_pair = pair
                best_key = mk
        if best_key is not None:
            return best_key, float(inventory.get(best_key, 0.0))

    inv_norm_keys = list(normalized_to_original.keys())
    alias_candidates = INGREDIENT_ALIAS_MAP.get(ing_norm, [])
    # Also aliases linked via formulation DISPLAY_MAP → same canonical ingredient
    for fk, cand in INGREDIENT_ALIAS_MAP.items():
        disp = INGREDIENT_DISPLAY_MAP.get(fk)
        if disp and normalize_key(str(disp)) == ing_norm:
            alias_candidates = alias_candidates + list(cand)
    seen_alias: set[str] = set()
    dedup_aliases: list[str] = []
    for a in alias_candidates:
        na = normalize_key(a)
        if na and na not in seen_alias:
            seen_alias.add(na)
            dedup_aliases.append(a)
    alias_matches: list[str] = []
    for alias in dedup_aliases:
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


def build_stock_alerts(
    recipe_items: list[dict[str, Any]],
    inventory: dict[str, float],
    displays: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for item in recipe_items:
        ingredient = str(item.get("ingredient", "")).strip()
        required = float(item.get("required_kg", item.get("quantity_kg", 0.0)) or 0.0)
        if not ingredient or required <= 0:
            continue
        matched_key, available = find_inventory_match(ingredient, inventory, displays, labels)
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
    recipe_items: list[dict[str, Any]],
    inventory: dict[str, float],
    requested_tonnage: float,
    displays: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
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
        matched_key, available_kg = find_inventory_match(ingredient, inventory, displays, labels)
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

