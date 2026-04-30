from __future__ import annotations

import csv
import json
import os
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_backend.config.settings import SETTINGS

try:
    from sklearn.linear_model import Ridge  # type: ignore
except Exception:  # noqa: BLE001
    Ridge = None


@dataclass
class PredictionTrainingReport:
    status: str
    model_name: str
    dataset_path: str
    output_dir: str
    points: int
    algorithm: str
    artifact_path: str
    trained_at: str
    message: str


def _load_series(path: str) -> list[float]:
    series: list[float] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            qty = row.get("quantity_kg")
            if qty is None:
                continue
            raw = str(qty).strip().replace(",", ".")
            try:
                val = abs(float(raw))
            except ValueError:
                continue
            series.append(val)
    return series


def train_prediction_model(
    model_name: str = "ridge-regression-stock",
    dataset_path: str | None = None,
    output_dir: str | None = None,
) -> PredictionTrainingReport:
    source_path = dataset_path or SETTINGS.dataset_classification_path
    target_dir = output_dir or SETTINGS.training_output_dir
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    points = _load_series(source_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_base = os.path.join(target_dir, f"{model_name}_{stamp}")

    if len(points) < 3:
        artifact_path = f"{artifact_base}.json"
        with open(artifact_path, "w", encoding="utf-8") as out:
            json.dump({"points": len(points), "message": "insufficient_points"}, out, indent=2)
        return PredictionTrainingReport(
            status="ok",
            model_name=model_name,
            dataset_path=source_path,
            output_dir=target_dir,
            points=len(points),
            algorithm="stats-fallback",
            artifact_path=artifact_path,
            trained_at=datetime.now(timezone.utc).isoformat(),
            message="insufficient points, fallback artifact generated",
        )

    if Ridge is not None:
        x = [[i] for i in range(len(points))]
        y = points
        model = Ridge(alpha=1.0)
        model.fit(x, y)
        artifact_path = f"{artifact_base}.pkl"
        with open(artifact_path, "wb") as out:
            pickle.dump(model, out)
        algo = "ridge-regression"
    else:
        # Store trend coefficients fallback
        slope = points[-1] - points[-2]
        intercept = points[-1]
        artifact_path = f"{artifact_base}.json"
        with open(artifact_path, "w", encoding="utf-8") as out:
            json.dump({"slope": slope, "intercept": intercept, "points": len(points)}, out, indent=2)
        algo = "linear-fallback"

    return PredictionTrainingReport(
        status="ok",
        model_name=model_name,
        dataset_path=source_path,
        output_dir=target_dir,
        points=len(points),
        algorithm=algo,
        artifact_path=artifact_path,
        trained_at=datetime.now(timezone.utc).isoformat(),
        message="prediction model artifact generated",
    )


def prediction_report_to_dict(report: PredictionTrainingReport) -> dict[str, Any]:
    return asdict(report)

