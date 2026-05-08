from __future__ import annotations

from pydantic import BaseModel, Field


class ClassificationTrainingRequest(BaseModel):
    model_name: str = Field(default="camembert-classifier")
    base_model: str = Field(default="FacebookAI/xlm-roberta-large")
    training_mode: str = Field(default="xlm_roberta_large")
    dataset_path: str = Field(default="")
    output_dir: str = Field(default="")
    test_size: float = Field(default=0.2, ge=0.05, le=0.4)


class ClassificationTrainingResponse(BaseModel):
    status: str
    model_name: str
    dataset_path: str
    output_dir: str
    examples: int
    labels: dict[str, int]
    accuracy: float
    algorithm: str
    artifact_path: str
    trained_at: str
    message: str


class PredictionTrainingRequest(BaseModel):
    model_name: str = Field(default="ridge-regression-stock")
    dataset_path: str = Field(default="")
    output_dir: str = Field(default="")


class PredictionTrainingResponse(BaseModel):
    status: str
    model_name: str
    dataset_path: str
    output_dir: str
    points: int
    algorithm: str
    artifact_path: str
    trained_at: str
    message: str

