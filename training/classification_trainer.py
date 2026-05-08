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

try:
    import torch  # type: ignore
    from transformers import (  # type: ignore
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )
except Exception:  # noqa: BLE001
    torch = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    Trainer = None
    TrainingArguments = None


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
    base_model: str = "FacebookAI/xlm-roberta-large",
    training_mode: str = "xlm_roberta_large",
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

    if training_mode == "xlm_roberta_large":
        xlm_report = _train_xlm_roberta_checkpoint(
            model_name=model_name,
            base_model=base_model,
            texts=texts,
            labels=labels,
            source_path=source_path,
            target_dir=target_dir,
            counts=counts,
        )
        if xlm_report is not None:
            return xlm_report

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


def _train_xlm_roberta_checkpoint(
    model_name: str,
    base_model: str,
    texts: list[str],
    labels: list[str],
    source_path: str,
    target_dir: str,
    counts: dict[str, int],
) -> TrainingReport | None:
    if (
        Trainer is None
        or TrainingArguments is None
        or AutoTokenizer is None
        or AutoModelForSequenceClassification is None
        or torch is None
    ):
        return None
    label_values = sorted(set(labels))
    label_to_id = {lab: idx for idx, lab in enumerate(label_values)}
    id_to_label = {idx: lab for lab, idx in label_to_id.items()}
    y = [label_to_id[l] for l in labels]

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model,
        num_labels=len(label_values),
        id2label=id_to_label,
        label2id=label_to_id,
    )

    class TextDataset(torch.utils.data.Dataset):  # type: ignore[attr-defined]
        def __init__(self, t: list[str], yy: list[int]) -> None:
            enc = tokenizer(t, truncation=True, padding=True, max_length=160)
            self.enc = enc
            self.yy = yy

        def __len__(self) -> int:
            return len(self.yy)

        def __getitem__(self, idx: int) -> dict[str, Any]:
            item = {k: torch.tensor(v[idx]) for k, v in self.enc.items()}  # type: ignore[attr-defined]
            item["labels"] = torch.tensor(self.yy[idx])  # type: ignore[attr-defined]
            return item

    ds = TextDataset(texts, y)
    ckpt_dir = SETTINGS.classification_checkpoint_dir
    args = TrainingArguments(
        output_dir=ckpt_dir,
        num_train_epochs=float(SETTINGS.training_default_epochs),
        per_device_train_batch_size=4,
        save_strategy="epoch",
        logging_steps=25,
        report_to=[],
    )
    trainer = Trainer(model=model, args=args, train_dataset=ds)
    trainer.train()
    trainer.save_model(ckpt_dir)
    tokenizer.save_pretrained(ckpt_dir)
    manifest = {
        "checkpoint_dir": ckpt_dir,
        "base_model": base_model,
        "model_name": model_name,
        "label_map": {str(k): str(v) for k, v in id_to_label.items()},
        "counts": counts,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(SETTINGS.classification_checkpoint_manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=True, indent=2)
    return TrainingReport(
        status="ok",
        model_name=model_name,
        dataset_path=source_path,
        output_dir=target_dir,
        examples=len(texts),
        labels=counts,
        accuracy=0.0,
        algorithm="xlm-roberta-large-finetune",
        artifact_path=ckpt_dir,
        trained_at=datetime.now(timezone.utc).isoformat(),
        message="xlm-roberta-large checkpoint trained and saved",
    )

