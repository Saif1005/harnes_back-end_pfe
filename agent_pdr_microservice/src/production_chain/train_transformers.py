"""Entraînement du classificateur binaire MP vs PDR (niveau 1 uniquement)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from datasets import Dataset
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)
from transformers.trainer_utils import set_seed


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "local_models"

LEVEL1_DATA_DEFAULT = DATA_DIR / "dataset_niveau1_mp_vs_pdr_clean.csv"

LEVEL1_MODEL_DIR = MODELS_DIR / "level1_mp_pdr"

BASE_MODEL = os.environ.get("HF_BASE_MODEL", "camembert-base")
EPOCHS = int(os.environ.get("TRAIN_EPOCHS", "3"))
BATCH_SIZE = int(os.environ.get("TRAIN_BATCH_SIZE", "8"))
MAX_LENGTH = int(os.environ.get("TRAIN_MAX_LENGTH", "160"))
SEED = int(os.environ.get("TRAIN_SEED", "42"))


def _resolve_level1_path() -> Path:
    env_path = os.environ.get("LEVEL1_DATA_PATH", "")
    if env_path:
        return Path(env_path)
    if LEVEL1_DATA_DEFAULT.exists():
        return LEVEL1_DATA_DEFAULT
    candidates = sorted(DATA_DIR.glob("dataset_niveau1_mp_vs_pdr*.csv"))
    if candidates:
        return candidates[0]
    return LEVEL1_DATA_DEFAULT


def _tokenize_batch(tokenizer: AutoTokenizer, examples: Dict[str, List[str]]) -> Dict[str, Any]:
    return tokenizer(
        examples["texte"],
        truncation=True,
        padding="max_length",
        max_length=MAX_LENGTH,
    )


def _prepare_level1_dataset(path: Path) -> Tuple[Dataset, Dataset, Dict[str, int], Dict[int, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Level1 dataset not found: {path}")

    df = pd.read_csv(path)
    required = {"texte", "label_type"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Level1 dataset missing columns: {sorted(missing)}")

    df = df.copy()
    df["texte"] = df["texte"].fillna("").astype(str).str.strip()
    df["label_type"] = df["label_type"].fillna("").astype(str).str.strip().str.upper()
    df = df[(df["texte"] != "") & (df["label_type"].isin(["MP", "PDR"]))].reset_index(drop=True)
    if df.empty:
        raise ValueError("Level1 dataset is empty after cleaning.")

    label2id = {"PDR": 0, "MP": 1}
    id2label = {v: k for k, v in label2id.items()}
    df["labels"] = df["label_type"].map(label2id).astype(int)

    train_df, val_df = train_test_split(df[["texte", "labels"]], test_size=0.2, random_state=SEED, stratify=df["labels"])
    return (
        Dataset.from_pandas(train_df.reset_index(drop=True)),
        Dataset.from_pandas(val_df.reset_index(drop=True)),
        label2id,
        id2label,
    )


def _train_level1() -> None:
    path = _resolve_level1_path()
    print(f"[Level1] dataset: {path}")
    train_ds, val_ds, label2id, id2label = _prepare_level1_dataset(path)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=False)
    train_ds = train_ds.map(lambda ex: _tokenize_batch(tokenizer, ex), batched=True)
    val_ds = val_ds.map(lambda ex: _tokenize_batch(tokenizer, ex), batched=True)
    train_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
    val_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=2,
        label2id=label2id,
        id2label=id2label,
    )

    def compute_metrics(pred: Any) -> Dict[str, float]:
        preds = np.argmax(pred.predictions, axis=1)
        y = pred.label_ids
        return {
            "accuracy": float(accuracy_score(y, preds)),
            "f1_macro": float(f1_score(y, preds, average="macro")),
        }

    LEVEL1_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    args = TrainingArguments(
        output_dir=str(LEVEL1_MODEL_DIR / "checkpoints"),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        learning_rate=2e-5,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        logging_steps=25,
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        report_to="none",
        seed=SEED,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )
    trainer.train()
    trainer.save_model(str(LEVEL1_MODEL_DIR))
    tokenizer.save_pretrained(str(LEVEL1_MODEL_DIR))
    print(f"[Level1] model saved to: {LEVEL1_MODEL_DIR}")


def main() -> None:
    set_seed(SEED)
    print(f"Base model: {BASE_MODEL}")
    print(f"Epochs={EPOCHS}, batch_size={BATCH_SIZE}, max_length={MAX_LENGTH}")
    _train_level1()
    print("Training complete (niveau 1 uniquement).")


if __name__ == "__main__":
    main()
