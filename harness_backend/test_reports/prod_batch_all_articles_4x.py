#!/usr/bin/env python3
"""
Run recipe + invoke + resume workflow 4 times per distinct machine line from formuleexacte.csv.
Reset stock from official CSV between runs for comparable results.
Usage on EC2:
  python3 prod_batch_all_articles_4x.py --base-url http://127.0.0.1:8030
"""
from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def post(base: str, path: str, payload: dict | None, timeout: int = 240) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
        return int(r.status), json.loads(body) if body else {}


def compact_stock_payload(data: dict | None, sample_keys: int = 12) -> dict:
    """Résumé stock lisible sans exploser la taille JSON (pas tout l'inventaire)."""
    if not isinstance(data, dict):
        return {}
    inv = data.get("inventory_map") or {}
    keys = list(inv.keys())[:sample_keys]
    sample = {k: inv[k] for k in keys}
    return {
        "totals_kg": data.get("totals_kg"),
        "source": data.get("source"),
        "query": data.get("query"),
        "inventory_item_count": len(inv),
        "inventory_sample": sample,
    }


def compact_prediction_payload(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    out: dict = {"forecast_next_kg": data.get("forecast_next_kg"), "model_used": data.get("model_used")}
    diag = data.get("diagnostics")
    if isinstance(diag, dict):
        out["diagnostics_summary"] = {
            k: {kk: v.get(kk) for kk in ("training_status", "points", "algorithm") if isinstance(v, dict)}
            for k, v in diag.items()
        }
    return out


def compact_recipe_compute_payload(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    return {
        "article": data.get("article"),
        "tonnage": data.get("tonnage"),
        "recipe_engine": data.get("recipe_engine"),
        "model_used": data.get("model_used"),
        "source": data.get("source"),
        "recipe_text": data.get("recipe_text"),
        "recipe_items": data.get("recipe_items"),
    }


def compact_invoke_response(inv: dict) -> dict:
    """Réponse API /invoke telle que renvoyée au client (message + détails utiles)."""
    details = inv.get("details") or {}
    tool_results = details.get("tool_results") or []
    compact_tools: list[dict] = []
    for tr in tool_results:
        if not isinstance(tr, dict):
            continue
        name = tr.get("tool_name")
        td = tr.get("data") if isinstance(tr.get("data"), dict) else {}
        entry: dict = {"tool_name": name, "ok": tr.get("ok"), "model": tr.get("model")}
        if name == "stock_check":
            entry["data"] = compact_stock_payload(td)
        elif name == "prediction_regression":
            entry["data"] = compact_prediction_payload(td)
        elif name == "recipe_compute":
            entry["data"] = compact_recipe_compute_payload(td)
        else:
            dumb = json.dumps(td, default=str)
            entry["data"] = td if len(dumb) < 8000 else {"_truncated": True, "keys": list(td.keys()) if isinstance(td, dict) else []}
        compact_tools.append(entry)
    return {
        "run_id": inv.get("run_id"),
        "status": inv.get("status"),
        "route": inv.get("route"),
        "message": inv.get("message"),
        "approval_id": inv.get("approval_id"),
        "details": {
            "tool_results": compact_tools,
            "errors": details.get("errors"),
            "metadata": details.get("metadata"),
            "react_trace": details.get("react_trace"),
        },
    }


def compact_resume_response(res: dict) -> dict:
    """Réponse /resume avec consommation + refresh stock/prédiction."""
    details = res.get("details") or {}
    meta = details.get("metadata") or {}
    consumption = meta.get("stock_consumption")
    tool_results = details.get("tool_results") or []
    compact_tools: list[dict] = []
    for tr in tool_results:
        if not isinstance(tr, dict):
            continue
        name = tr.get("tool_name")
        td = tr.get("data") if isinstance(tr.get("data"), dict) else {}
        entry: dict = {"tool_name": name, "ok": tr.get("ok"), "model": tr.get("model")}
        if name == "stock_check":
            entry["data"] = compact_stock_payload(td)
        elif name == "prediction_regression":
            entry["data"] = compact_prediction_payload(td)
        elif name == "recipe_compute":
            entry["data"] = compact_recipe_compute_payload(td)
        else:
            entry["data"] = td
        compact_tools.append(entry)
    return {
        "run_id": res.get("run_id"),
        "status": res.get("status"),
        "route": res.get("route"),
        "message": res.get("message"),
        "approval_id": res.get("approval_id"),
        "stock_consumption": consumption,
        "details": {
            "tool_results": compact_tools,
            "errors": details.get("errors"),
            "metadata": meta,
            "react_trace": details.get("react_trace"),
        },
    }


def recipe_tool_full_response(recipe: dict) -> dict:
    """Réponse brute du tool recette (valeurs calculées pour l'opérateur)."""
    return {
        "article": recipe.get("article"),
        "tonnage": recipe.get("tonnage"),
        "recipe_text": recipe.get("recipe_text"),
        "recipe_items": recipe.get("recipe_items"),
        "model_used": recipe.get("model_used"),
        "recipe_engine": recipe.get("recipe_engine"),
        "source": recipe.get("source"),
        "error": recipe.get("error"),
    }


def machine_to_article_prompt(machine_cible: str) -> str:
    mc = machine_cible.lower()
    if "kraft" in mc:
        return "Kraft pour sacs"
    if "fluting" in mc or "cannelure" in mc:
        return "Cannelure (Fluting)"
    if "test color" in mc:
        return "TestLiner Coloré"
    if "testliner" in mc:
        return "TestLiner"
    return machine_cible


def load_articles(formula_path: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    with open(formula_path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            mc = str(row.get("machine_cible", "")).strip().lower()
            if not mc or mc in seen:
                continue
            seen.add(mc)
            out.append({"machine_cible": mc, "article_prompt": machine_to_article_prompt(mc)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8030")
    parser.add_argument("--formula", default="/opt/harness/data/formuleexacte.csv")
    parser.add_argument("--official-stock", default="/opt/harness/data/magasin_stock_historique_2017_2023.csv")
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    base = args.base_url
    official = args.official_stock
    formula = args.formula
    n_iter = max(1, int(args.iterations))

    articles = load_articles(formula)
    results: list[dict] = []

    for art in articles:
        article_name = art["article_prompt"]
        mc = art["machine_cible"]
        for i in range(1, n_iter + 1):
            post(base, "/admin/data/import-official-stock", {"source_path": official})
            st_r, recipe = post(base, "/tools/recipe", {"query": f"preparer recette exacte pour 4 tonnes {article_name}"})
            st_i, inv = post(
                base,
                "/invoke",
                {"query": f"passer commande 4 tonnes {article_name}", "session_id": f"batch-{mc}-{i}", "user_id": "qa-batch"},
            )
            row: dict = {
                "article": article_name,
                "machine_cible": mc,
                "iteration": i,
                "recipe_http": st_r,
                "recipe_source": recipe.get("source"),
                "recipe_engine": recipe.get("recipe_engine"),
                "recipe_items_count": len(recipe.get("recipe_items") or []),
                "invoke_http": st_i,
                "invoke_status": inv.get("status"),
                "run_id": inv.get("run_id", ""),
                "approval_id": inv.get("approval_id", ""),
                "resume_status": "",
                "resume_tools": [],
                "consumption_present": False,
                "errors": [],
                # Réponses système complètes (calculs, texte, prévisions)
                "responses": {
                    "recipe_tool": recipe_tool_full_response(recipe),
                    "invoke": compact_invoke_response(inv),
                    "resume": None,
                },
            }
            if st_r != 200:
                row["errors"].append("recipe_http_error")
            if st_i != 200:
                row["errors"].append("invoke_http_error")

            if inv.get("status") == "interrupted" and inv.get("approval_id"):
                st_res, res = post(
                    base,
                    "/resume",
                    {
                        "run_id": inv.get("run_id"),
                        "approval_id": inv.get("approval_id"),
                        "approved": True,
                        "reviewer": "qa-batch",
                        "comment": "batch auto-approval",
                    },
                )
                row["resume_status"] = res.get("status", "") if st_res == 200 else f"http_{st_res}"
                details = res.get("details", {}) if isinstance(res, dict) else {}
                row["resume_tools"] = [
                    x.get("tool_name") for x in (details.get("tool_results") or []) if isinstance(x, dict)
                ]
                row["consumption_present"] = bool((details.get("metadata") or {}).get("stock_consumption"))
                row["responses"]["resume"] = compact_resume_response(res)
                if st_res != 200:
                    row["errors"].append("resume_http_error")
            elif inv.get("status") == "ok":
                row["resume_status"] = "not_required"
            else:
                row["errors"].append("invoke_unexpected_status")

            results.append(row)

    summary = {
        "total_articles": len(articles),
        "iterations_per_article": n_iter,
        "total_runs": len(results),
        "recipe_formula_source_runs": sum(1 for r in results if r.get("recipe_source") == "formula_exact_csv"),
        "successful_workflow_runs": sum(
            1
            for r in results
            if r.get("invoke_status") in {"ok", "interrupted"} and r.get("resume_status") in {"ok", "not_required"}
        ),
        "runs_with_errors": sum(1 for r in results if r.get("errors")),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out) if args.out else Path(f"/home/ubuntu/prod_recipe_all_articles_{n_iter}x_{stamp}.json")
    report = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": f"formuleexacte distinct machine_cible, {n_iter} runs each",
        "summary": summary,
        "results": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(out_path), "summary": summary}, ensure_ascii=True))


if __name__ == "__main__":
    main()
