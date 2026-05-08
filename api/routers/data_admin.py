from __future__ import annotations

import csv
import time
from fastapi import APIRouter, HTTPException

from harness_backend.config.settings import SETTINGS
from harness_backend.tools.implementations.classification_tools import run_material_classification
from harness_backend.tools.implementations.prediction_tools import run_prediction_regression
from harness_backend.tools.implementations.recipe_tools import run_recipe_compute
from harness_backend.tools.implementations.stock_tools import run_stock_check
from harness_backend.services.stock_runtime import (
    apply_stock_adjustments,
    build_restock_plan,
    import_official_stock_history,
    get_inventory_state,
    map_legacy_dataset,
    rebuild_stock_base_from_dataset,
)
from harness_backend.services.synthetic_stock_data import generate_synthetic_import_csv

router = APIRouter(prefix="/admin/data", tags=["data-admin"])


@router.post("/map-legacy")
def map_legacy(payload: dict) -> dict:
    try:
        source_path = str(payload.get("source_path", "")).strip() or None
        target_path = str(payload.get("target_path", "")).strip() or None
        classify_missing_labels = bool(payload.get("classify_missing_labels", True))
        classify_all = bool(payload.get("classify_all", False))
        production_only = bool(payload.get("production_only", True))
        article_reference_path = str(payload.get("article_reference_path", "")).strip() or None
        return map_legacy_dataset(
            source_path=source_path,
            target_path=target_path,
            classify_missing_labels=classify_missing_labels,
            classify_all=classify_all,
            production_only=production_only,
            article_reference_path=article_reference_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"map_legacy_failed: {exc}") from exc


@router.post("/rebuild-stock")
def rebuild_stock(payload: dict) -> dict:
    try:
        dataset_path = str(payload.get("dataset_path", "")).strip() or None
        info = rebuild_stock_base_from_dataset(dataset_path=dataset_path)
        info["stock_state"] = get_inventory_state()
        return info
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"rebuild_stock_failed: {exc}") from exc


@router.post("/import-build-stock")
def import_build_stock(payload: dict) -> dict:
    """
    One-shot import pipeline:
    1) map legacy/raw file
    2) auto-classify MP/PDR/CHIMIE (missing labels by default)
    3) rebuild stock runtime DB
    """
    try:
        source_path = str(payload.get("source_path", "")).strip() or None
        target_path = str(payload.get("target_path", "")).strip() or None
        classify_missing_labels = bool(payload.get("classify_missing_labels", True))
        classify_all = bool(payload.get("classify_all", False))
        production_only = bool(payload.get("production_only", True))
        article_reference_path = str(payload.get("article_reference_path", "")).strip() or None
        mapped = map_legacy_dataset(
            source_path=source_path,
            target_path=target_path,
            classify_missing_labels=classify_missing_labels,
            classify_all=classify_all,
            production_only=production_only,
            article_reference_path=article_reference_path,
        )
        rebuilt = rebuild_stock_base_from_dataset(dataset_path=str(mapped.get("target_path") or "") or None)
        return {
            "mapped": mapped,
            "rebuilt": rebuilt,
            "stock_state": get_inventory_state(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"import_build_stock_failed: {exc}") from exc


@router.post("/benchmark-random")
def benchmark_random(payload: dict) -> dict:
    """
    Inject random industrial-like data, rebuild stock, and benchmark:
    - classification accuracy on injected set
    - tool latencies (classification / stock / recipe / prediction)
    - stock consistency checks
    """
    try:
        rows = int(payload.get("rows", 1500) or 1500)
        seed = int(payload.get("seed", 42) or 42)
        synthetic_path = str(payload.get("synthetic_path", "")).strip() or (
            f"{SETTINGS.stock_mapped_dataset_path}.synthetic.csv"
        )

        generated = generate_synthetic_import_csv(path=synthetic_path, rows=rows, seed=seed)
        mapped = map_legacy_dataset(
            source_path=generated["path"],
            target_path=SETTINGS.stock_mapped_dataset_path,
            classify_missing_labels=True,
            classify_all=True,
            production_only=False,
        )
        rebuilt = rebuild_stock_base_from_dataset(dataset_path=str(mapped.get("target_path") or ""))
        stock_state = get_inventory_state()

        # Classification quality on synthetic data (labels are known).
        total = 0
        correct = 0
        with open(generated["path"], "r", encoding="utf-8", errors="ignore") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                text = str(row.get("texte", "")).strip()
                expected = str(row.get("label", "")).strip().upper()
                if not text or expected not in {"MP", "CHIMIE", "PDR"}:
                    continue
                pred = str(run_material_classification(text).get("label", "")).strip().upper()
                total += 1
                if pred == expected:
                    correct += 1
        acc = (correct / total) if total else 0.0

        # Tool performance latencies.
        perf: dict[str, float] = {}
        t0 = time.perf_counter()
        cls = run_material_classification("acide amidon biocide")
        perf["classification_ms"] = round((time.perf_counter() - t0) * 1000, 3)

        t0 = time.perf_counter()
        stk = run_stock_check("stock disponible")
        perf["stock_ms"] = round((time.perf_counter() - t0) * 1000, 3)

        t0 = time.perf_counter()
        rcp = run_recipe_compute("produire 2 tonnes de Kraft pour sacs")
        perf["recipe_ms"] = round((time.perf_counter() - t0) * 1000, 3)

        t0 = time.perf_counter()
        prd = run_prediction_regression("prediction stock")
        perf["prediction_ms"] = round((time.perf_counter() - t0) * 1000, 3)

        checks = {
            "classification_label_valid": str(cls.get("label", "")) in {"MP", "CHIMIE", "PDR"},
            "stock_totals_non_negative": all(float(v) >= 0 for v in (stk.get("totals_kg", {}) or {}).values()),
            "recipe_items_non_empty": len(rcp.get("recipe_items", []) or []) > 0,
            "prediction_has_forecast": len(prd.get("forecast_next_kg", {}) or {}) > 0,
        }

        return {
            "generated": generated,
            "mapped": mapped,
            "rebuilt": rebuilt,
            "stock_state": stock_state,
            "classification_eval": {
                "total": total,
                "correct": correct,
                "accuracy": round(acc, 4),
            },
            "tool_performance_ms": perf,
            "sanity_checks": checks,
            "ok": all(bool(v) for v in checks.values()),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"benchmark_random_failed: {exc}") from exc


@router.post("/import-official-stock")
def import_official_stock(payload: dict) -> dict:
    """
    Import official historical stock CSV into SQL runtime and rebuild current stock snapshot.
    This becomes the authoritative stock source for runtime tools.
    """
    try:
        source_path = str(payload.get("source_path", "")).strip() or None
        imported = import_official_stock_history(source_path=source_path)
        return {
            "imported": imported,
            "stock_state": get_inventory_state(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"import_official_stock_failed: {exc}") from exc


@router.post("/adjust-stock")
def adjust_stock(payload: dict) -> dict:
    """
    Dynamic +/- stock adjustments (restock or manual correction),
    persisted into stock_movements and reflected in reasoning base.
    """
    try:
        adjustments = list(payload.get("adjustments") or [])
        run_id = str(payload.get("run_id", "")).strip() or "admin-adjust"
        reason = str(payload.get("reason", "")).strip() or "manual_adjustment"
        applied = apply_stock_adjustments(adjustments=adjustments, run_id=run_id, reason=reason)
        return {
            "applied": applied,
            "stock_state": get_inventory_state(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"adjust_stock_failed: {exc}") from exc


@router.post("/auto-restock")
def auto_restock(payload: dict) -> dict:
    """
    Build low-stock restock proposal and optionally apply it.
    """
    try:
        label = str(payload.get("label", "")).strip() or None
        min_quantity_kg = float(payload.get("min_quantity_kg", 10.0) or 10.0)
        target_quantity_kg = float(payload.get("target_quantity_kg", 100.0) or 100.0)
        limit = int(payload.get("limit", 200) or 200)
        auto_apply = bool(payload.get("auto_apply", False))
        run_id = str(payload.get("run_id", "")).strip() or "auto-restock"
        reason = str(payload.get("reason", "")).strip() or "auto_restock"

        plan = build_restock_plan(
            label=label,
            min_quantity_kg=min_quantity_kg,
            target_quantity_kg=target_quantity_kg,
            limit=limit,
        )
        applied = {"count": 0, "updates": []}
        if auto_apply:
            adjustments = [
                {
                    "material_key": x.get("material_key", ""),
                    "delta_kg": float(x.get("proposed_delta_kg", 0.0) or 0.0),
                }
                for x in (plan.get("items") or [])
            ]
            applied = apply_stock_adjustments(adjustments=adjustments, run_id=run_id, reason=reason)

        return {
            "plan": plan,
            "applied": applied,
            "stock_state": get_inventory_state(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"auto_restock_failed: {exc}") from exc

