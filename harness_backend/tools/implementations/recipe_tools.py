from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict

from harness_backend.config.settings import SETTINGS
from harness_backend.services.legacy_compat import (
    canonical_ingredient_name,
    extract_article_from_question,
    extract_requested_tonnage,
    normalize_key,
    parse_recipe_items,
)
from harness_backend.tools.adapters.legacy_tools_api import compute_recipe_remote

logger = logging.getLogger(__name__)

try:
    from langchain_ollama import ChatOllama  # type: ignore
except Exception:  # noqa: BLE001
    ChatOllama = None


def _parse_article(query: str) -> str:
    return extract_article_from_question(query)


def _parse_tonnage(query: str) -> float:
    return extract_requested_tonnage(query)


def _article_machine_aliases(article: str) -> list[str]:
    low = (article or "").lower()
    if "kraft" in low:
        return ["kraft", "sotikraft", "kraft export"]
    if "fluting" in low or "cannelure" in low:
        return ["fluting", "cannelure"]
    if "testliner" in low and "color" in low:
        return ["test color", "testliner color"]
    if "testliner" in low:
        return ["testliner"]
    return [low]


def _exact_recipe_from_formula_csv(article: str, tonnage: float) -> list[dict]:
    """
    Build exact recipe from formuleexacte.csv:
    - machine_cible filtered by article aliases
    - keep best scored row per ingredient
    - use quantite_standard_kg as per-ton baseline, then scale by requested tonnage
    """
    aliases = _article_machine_aliases(article)
    best_by_ingredient: dict[str, dict] = {}
    try:
        with open(SETTINGS.formula_exact_path, "r", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                machine = str(row.get("machine_cible", "")).strip().lower()
                if machine and not any(a in machine for a in aliases):
                    continue
                ingredient = str(row.get("id_article_erp", "")).strip()
                if not ingredient:
                    continue
                try:
                    qty_per_ton = float(str(row.get("quantite_standard_kg", "0")).replace(",", ".").strip() or 0.0)
                except ValueError:
                    qty_per_ton = 0.0
                if qty_per_ton <= 0:
                    continue
                try:
                    score = float(str(row.get("score_final", "0")).replace(",", ".").strip() or 0.0)
                except ValueError:
                    score = 0.0
                key = ingredient.lower()
                prev = best_by_ingredient.get(key)
                if prev is None or score > float(prev.get("score", 0.0)):
                    best_by_ingredient[key] = {"ingredient": ingredient, "qty_per_ton": qty_per_ton, "score": score}
    except FileNotFoundError:
        return []

    items: list[dict] = []
    for val in best_by_ingredient.values():
        required_kg = round(float(val["qty_per_ton"]) * tonnage, 3)
        if required_kg <= 0:
            continue
        items.append(
            {
                "ingredient": canonical_ingredient_name(str(val["ingredient"]).strip()),
                "ratio_kg_per_ton": round(float(val["qty_per_ton"]), 3),
                "required_kg": required_kg,
            }
        )
    return _consolidate_recipe_items(items)


def _consolidate_recipe_items(recipe_items: list[dict]) -> list[dict]:
    """
    Merge duplicates and normalize ingredient naming for coherent outputs.
    """
    merged: dict[str, dict] = {}
    for it in recipe_items:
        ing_raw = str(it.get("ingredient", "")).strip()
        if not ing_raw:
            continue
        ing = canonical_ingredient_name(ing_raw)
        key = normalize_key(ing)
        if not key:
            continue
        required_kg = float(it.get("required_kg", 0.0) or 0.0)
        ratio_kg_per_ton = float(it.get("ratio_kg_per_ton", 0.0) or 0.0)
        rec = merged.setdefault(
            key,
            {
                "ingredient": ing,
                "ratio_kg_per_ton": 0.0,
                "required_kg": 0.0,
            },
        )
        rec["required_kg"] = float(rec["required_kg"]) + required_kg
        rec["ratio_kg_per_ton"] = float(rec["ratio_kg_per_ton"]) + ratio_kg_per_ton

    out: list[dict] = []
    for v in merged.values():
        req = round(float(v["required_kg"]), 3)
        if req <= 0:
            continue
        out.append(
            {
                "ingredient": str(v["ingredient"]).strip(),
                "ratio_kg_per_ton": round(float(v["ratio_kg_per_ton"]), 3),
                "required_kg": req,
            }
        )
    out.sort(key=lambda x: x["required_kg"], reverse=True)
    return out[:30]


def _format_recipe_lines_deterministic(recipe_items: list[dict]) -> str:
    lines: list[str] = []
    for i, it in enumerate(recipe_items[:25], 1):
        ing = str(it.get("ingredient", "")).strip()
        kg = float(it.get("required_kg", 0.0) or 0.0)
        if ing:
            lines.append(f"{i} - {ing} : {kg:.3f} kg")
    return "\n".join(lines)


def _synthesize_recipe_text_with_qwen(
    article: str,
    tonnage: float,
    recipe_items: list[dict],
    operator_query: str,
    legacy_recipe_text: str = "",
) -> str:
    """
    Tâche recette déléguée au LLM Qwen (instruct) : formuler la recette à partir des quantités
    imposées (CSV / données) sans les inventer.
    """
    if not SETTINGS.recipe_use_llm or ChatOllama is None or not recipe_items:
        return _format_recipe_lines_deterministic(recipe_items)
    llm = ChatOllama(
        base_url=SETTINGS.ollama_base_url,
        model=SETTINGS.recipe_llm_model,
        temperature=0.05,
    )
    payload = json.dumps(recipe_items[:25], ensure_ascii=True)
    extra = ""
    if legacy_recipe_text.strip():
        extra = f"\nTexte source (ne pas changer les quantités, seulement harmoniser le format):\n{legacy_recipe_text[:2500]}\n"
    prompt = (
        f"Tu es l'agent recette usine (modèle {SETTINGS.recipe_llm_model}).\n"
        f"Article produit: {article}. Tonnes à produire: {tonnage}.\n"
        f"Consigne opérateur: {operator_query[:500]}\n"
        f"{extra}"
        "Données chiffrées OBLIGATOIRES (JSON, required_kg exacts à respecter pour chaque ingrédient):\n"
        f"{payload}\n\n"
        "Réponds UNIQUEMENT par des lignes au format strict (une par ingrédient, pas de markdown, pas d'introduction):\n"
        "1 - <ingrédient> : <nombre> kg\n"
        "2 - ...\n"
        "Les nombres kg doivent correspondre exactement aux required_kg du JSON pour le même ingrédient."
    )
    try:
        resp = llm.invoke(prompt)
        text = str(getattr(resp, "content", resp) or "").strip()
        parsed = parse_recipe_items(text)
        if len(parsed) >= min(1, len(recipe_items)):
            return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("recipe_qwen_synthesis_failed: %s", exc)
    return _format_recipe_lines_deterministic(recipe_items)


def run_recipe_compute(query: str) -> dict:
    article = _parse_article(query)
    tonnage = _parse_tonnage(query)
    exact_items = _exact_recipe_from_formula_csv(article, tonnage)
    if exact_items:
        exact_items = _consolidate_recipe_items(exact_items)
        recipe_text = _synthesize_recipe_text_with_qwen(article, tonnage, exact_items, query)
        parsed = parse_recipe_items(recipe_text)
        if parsed:
            exact_items = _consolidate_recipe_items(parsed[:30])
        return {
            "article": article,
            "tonnage": tonnage,
            "recipe_text": recipe_text,
            "recipe_items": exact_items,
            "model_used": SETTINGS.recipe_llm_model if SETTINGS.recipe_use_llm else SETTINGS.recipe_model,
            "recipe_engine": "formuleexacte+qwen",
            "source": "formula_exact_csv",
        }

    remote = compute_recipe_remote(query)
    if remote.get("ok"):
        recipe_text = str(remote.get("result", ""))
        recipe_items = _consolidate_recipe_items(parse_recipe_items(recipe_text))
        used_llm = False
        if SETTINGS.recipe_llm_postprocess_remote and SETTINGS.recipe_use_llm and recipe_items:
            recipe_text = _synthesize_recipe_text_with_qwen(
                article, tonnage, recipe_items, query, legacy_recipe_text=recipe_text
            )
            recipe_items = _consolidate_recipe_items(parse_recipe_items(recipe_text) or recipe_items)
            used_llm = True
        elif not recipe_text.strip() and recipe_items and SETTINGS.recipe_use_llm:
            recipe_text = _synthesize_recipe_text_with_qwen(article, tonnage, recipe_items, query)
            recipe_items = _consolidate_recipe_items(parse_recipe_items(recipe_text) or recipe_items)
            used_llm = True
        return {
            "article": article,
            "tonnage": tonnage,
            "recipe_text": recipe_text,
            "recipe_items": recipe_items,
            "model_used": SETTINGS.recipe_llm_model if used_llm else SETTINGS.recipe_model,
            "recipe_engine": "legacy_api+qwen" if used_llm else "legacy_api",
            "source": "legacy_api_bridge",
        }

    ingredient_ratios = defaultdict(list)
    try:
        with open(SETTINGS.recipe_correlation_path, "r", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if str(row.get("family_pf", "")).strip() != article:
                    continue
                ingredient = str(row.get("ingredient", "")).strip()
                ratio = float(row.get("ratio_kg_per_ton", 0.0) or 0.0)
                if ingredient:
                    ingredient_ratios[ingredient].append(ratio)
    except FileNotFoundError:
        return {
            "article": article,
            "tonnage": tonnage,
            "recipe_text": "",
            "recipe_items": [],
            "model_used": SETTINGS.recipe_llm_model,
            "source": "missing_dataset",
            "error": f"recipe_correlation_not_found: {SETTINGS.recipe_correlation_path}",
        }

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
    recipe_items = _consolidate_recipe_items(recipe_items)
    recipe_text = _synthesize_recipe_text_with_qwen(article, tonnage, recipe_items, query)
    parsed = parse_recipe_items(recipe_text)
    if parsed:
        recipe_items = _consolidate_recipe_items(parsed[:30])
    return {
        "article": article,
        "tonnage": tonnage,
        "recipe_text": recipe_text,
        "recipe_items": recipe_items,
        "model_used": SETTINGS.recipe_llm_model if SETTINGS.recipe_use_llm else SETTINGS.recipe_model,
        "recipe_engine": "csv_ratios+qwen",
        "source": "csv_fallback",
    }
