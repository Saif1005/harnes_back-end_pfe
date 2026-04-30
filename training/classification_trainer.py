from __future__ import annotations

import csv
import json
import os
import pickle
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness_backend.config.settings import SETTINGS

try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    from sklearn.linear_model import LogisticRegression  # type: ignore
    from sklearn.metrics import accuracy_score  # type: ignore
    from sklearn.model_selection import train_test_split  # type: ignore
    from sklearn.pipeline import Pipeline  # type: ignore
except Exception:  # noqa: BLE001
    TfidfVectorizer = None
    LogisticRegression = None
    accuracy_score = None
    train_test_split = None
    Pipeline = None


@dataclass
class TrainingReport:
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


def _heuristic_label(text: str) -> str:
    low = (text or "").lower()
    if any(k in low for k in ("acide", "soude", "amidon", "asa", "ppo", "pac", "biocide")):
        return "CHIMIE"
    if any(k in low for k in ("roulement", "courroie", "vis", "joint", "moteur", "pompe")):
        return "PDR"
    return "MP"


def _load_dataset(path: str) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            text = str(row.get("texte", "")).strip()
            if not text:
                continue
            label = str(row.get("label", "")).strip().upper()
            if not label:
                label = _heuristic_label(text)
            texts.append(text)
            labels.append(label)
    return texts, labels


def train_classification_model(
    model_name: str,
    dataset_path: str | None = None,
    output_dir: str | None = None,
    test_size: float | None = None,
) -> TrainingReport:
    source_path = dataset_path or SETTINGS.dataset_classification_path
    target_dir = output_dir or SETTINGS.training_output_dir
    split_ratio = float(test_size if test_size is not None else SETTINGS.training_default_test_size)

    Path(target_dir).mkdir(parents=True, exist_ok=True)
    texts, labels = _load_dataset(source_path)
    counts = dict(Counter(labels))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_base = os.path.join(target_dir, f"{model_name.replace('/', '_')}_{stamp}")

    if not texts:
        report = TrainingReport(
            status="error",
            model_name=model_name,
            dataset_path=source_path,
            output_dir=target_dir,
            examples=0,
            labels={},
            accuracy=0.0,
            algorithm="none",
            artifact_path="",
            trained_at=datetime.now(timezone.utc).isoformat(),
            message="dataset is empty",
        )
        return report

    if Pipeline is not None and TfidfVectorizer is not None and LogisticRegression is not None:
        x_train, x_test, y_train, y_test = train_test_split(
            texts, labels, test_size=max(0.05, min(0.4, split_ratio)), random_state=42, stratify=labels
        )
        model = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2)),
                ("clf", LogisticRegression(max_iter=600)),
            ]
        )
        model.fit(x_train, y_train)
        pred = model.predict(x_test)
        acc = float(accuracy_score(y_test, pred)) if accuracy_score is not None else 0.0
        artifact_path = f"{artifact_base}.pkl"
        with open(artifact_path, "wb") as out:
            pickle.dump(model, out)
        return TrainingReport(
            status="ok",
            model_name=model_name,
            dataset_path=source_path,
            output_dir=target_dir,
            examples=len(texts),
            labels=counts,
            accuracy=round(acc, 4),
            algorithm="tfidf+logreg",
            artifact_path=artifact_path,
            trained_at=datetime.now(timezone.utc).isoformat(),
            message="classification model trained successfully",
        )

    artifact_path = f"{artifact_base}.json"
    with open(artifact_path, "w", encoding="utf-8") as out:
        json.dump({"label_counts": counts, "examples": len(texts)}, out, ensure_ascii=True, indent=2)
    return TrainingReport(
        status="ok",
        model_name=model_name,
        dataset_path=source_path,
        output_dir=target_dir,
        examples=len(texts),
        labels=counts,
        accuracy=0.0,
        algorithm="stats-fallback",
        artifact_path=artifact_path,
        trained_at=datetime.now(timezone.utc).isoformat(),
        message="fallback training summary generated (sklearn unavailable)",
    )


def report_to_dict(report: TrainingReport) -> dict[str, Any]:
    return asdict(report)

