from __future__ import annotations

import csv
from collections import defaultdict

from harness_backend.config.settings import SETTINGS
from harness_backend.services.legacy_compat import (
    extract_article_from_question,
    extract_requested_tonnage,
    parse_recipe_items,
)
from harness_backend.tools.adapters.legacy_tools_api import compute_recipe_remote


def _parse_article(query: str) -> str:
    return extract_article_from_question(query)


def _parse_tonnage(query: str) -> float:
    return extract_requested_tonnage(query)


def run_recipe_compute(query: str) -> dict:
    article = _parse_article(query)
    tonnage = _parse_tonnage(query)
    remote = compute_recipe_remote(query)
    if remote.get("ok"):
        recipe_text = str(remote.get("result", ""))
        recipe_items = parse_recipe_items(recipe_text)
        return {
            "article": article,
            "tonnage": tonnage,
            "recipe_text": recipe_text,
            "recipe_items": recipe_items,
            "model_used": SETTINGS.recipe_model,
            "source": "legacy_api_bridge",
        }

    ingredient_ratios = defaultdict(list)
    with open(SETTINGS.recipe_correlation_path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if str(row.get("family_pf", "")).strip() != article:
                continue
            ingredient = str(row.get("ingredient", "")).strip()
            ratio = float(row.get("ratio_kg_per_ton", 0.0) or 0.0)
            if ingredient:
                ingredient_ratios[ingredient].append(ratio)

    recipe_items: list[dict] = []
    for ingredient, ratios in ingredient_ratios.items():
        if not ratios:
            continue
        avg_ratio = sum(ratios) / len(ratios)
        recipe_items.append(
            {
                "ingredient": ingredient.strip(),
                "ratio_kg_per_ton": round(avg_ratio, 3),
                "required_kg": round(avg_ratio * tonnage, 3),
            }
        )
    recipe_items.sort(key=lambda x: x["required_kg"], reverse=True)
    return {
        "article": article,
        "tonnage": tonnage,
        "recipe_text": "",
        "recipe_items": recipe_items[:20],
        "model_used": SETTINGS.recipe_model,
        "source": "csv_fallback",
    }

