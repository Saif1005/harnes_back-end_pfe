from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harness_backend.api.schemas.training import (
    ClassificationTrainingRequest,
    ClassificationTrainingResponse,
    PredictionTrainingRequest,
    PredictionTrainingResponse,
)
from harness_backend.config.settings import SETTINGS
from harness_backend.services.stock_runtime import map_legacy_dataset
from harness_backend.training.classification_trainer import report_to_dict, train_classification_model
from harness_backend.training.prediction_trainer import prediction_report_to_dict, train_prediction_model

router = APIRouter(prefix="/admin/training", tags=["training"])


@router.post("/classification", response_model=ClassificationTrainingResponse)
def train_classification(payload: ClassificationTrainingRequest) -> ClassificationTrainingResponse:
    try:
        report = train_classification_model(
            model_name=payload.model_name,
            base_model=payload.base_model,
            training_mode=payload.training_mode,
            dataset_path=payload.dataset_path or None,
            output_dir=payload.output_dir or None,
            test_size=payload.test_size,
        )
        return ClassificationTrainingResponse(**report_to_dict(report))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"classification_training_failed: {exc}") from exc


@router.post("/prediction", response_model=PredictionTrainingResponse)
def train_prediction(payload: PredictionTrainingRequest) -> PredictionTrainingResponse:
    try:
        report = train_prediction_model(
            model_name=payload.model_name,
            dataset_path=payload.dataset_path or None,
            output_dir=payload.output_dir or None,
        )
        return PredictionTrainingResponse(**prediction_report_to_dict(report))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"prediction_training_failed: {exc}") from exc


@router.post("/classification-from-stock")
def train_classification_from_stock(payload: dict) -> dict:
    """
    Build/refresh mapped stock dataset then fine-tune XLM-R on it.
    """
    try:
        source_path = str(payload.get("source_path", "")).strip() or None
        target_path = str(payload.get("target_path", "")).strip() or SETTINGS.stock_mapped_dataset_path
        base_model = str(payload.get("base_model", "")).strip() or "FacebookAI/xlm-roberta-large"
        model_name = str(payload.get("model_name", "")).strip() or SETTINGS.classification_model_name
        training_mode = str(payload.get("training_mode", "")).strip() or "xlm_roberta_large"
        classify_all = bool(payload.get("classify_all", True))
        production_only = bool(payload.get("production_only", True))
        article_reference_path = str(payload.get("article_reference_path", "")).strip() or None

        mapped = map_legacy_dataset(
            source_path=source_path,
            target_path=target_path,
            classify_missing_labels=True,
            classify_all=classify_all,
            production_only=production_only,
            article_reference_path=article_reference_path,
        )
        report = train_classification_model(
            model_name=model_name,
            base_model=base_model,
            training_mode=training_mode,
            dataset_path=str(mapped.get("target_path") or target_path),
            output_dir=None,
            test_size=None,
        )
        return {"mapped": mapped, "training": report_to_dict(report)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"classification_from_stock_failed: {exc}") from exc

