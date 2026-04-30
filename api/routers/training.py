from __future__ import annotations

from fastapi import APIRouter, HTTPException

from harness_backend.api.schemas.training import (
    ClassificationTrainingRequest,
    ClassificationTrainingResponse,
    PredictionTrainingRequest,
    PredictionTrainingResponse,
)
from harness_backend.training.classification_trainer import report_to_dict, train_classification_model
from harness_backend.training.prediction_trainer import prediction_report_to_dict, train_prediction_model

router = APIRouter(prefix="/admin/training", tags=["training"])


@router.post("/classification", response_model=ClassificationTrainingResponse)
def train_classification(payload: ClassificationTrainingRequest) -> ClassificationTrainingResponse:
    try:
        report = train_classification_model(
            model_name=payload.model_name,
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

