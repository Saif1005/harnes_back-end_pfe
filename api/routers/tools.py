from __future__ import annotations

from fastapi import APIRouter

from harness_backend.tools.implementations.classification_tools import run_material_classification
from harness_backend.tools.implementations.prediction_tools import run_prediction_regression
from harness_backend.tools.implementations.recipe_tools import run_recipe_compute
from harness_backend.tools.implementations.stock_tools import run_stock_check

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/classification")
def classification_tool(payload: dict) -> dict:
    query = str(payload.get("query", ""))
    return run_material_classification(query)


@router.post("/recipe")
def recipe_tool(payload: dict) -> dict:
    query = str(payload.get("query", ""))
    return run_recipe_compute(query)


@router.post("/stock")
def stock_tool(payload: dict) -> dict:
    query = str(payload.get("query", ""))
    return run_stock_check(query)


@router.post("/prediction")
def prediction_tool(payload: dict) -> dict:
    query = str(payload.get("query", ""))
    return run_prediction_regression(query)

