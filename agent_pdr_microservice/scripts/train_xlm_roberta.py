#!/usr/bin/env python3
"""
Fine-tuning XLM-RoBERTa-large (SequenceClassification, 2 classes) : MP vs CHIMIE.

Multilingue (FR/EN), adapté au déploiement cloud (GPU recommandé).

Entrée  : ``data/dataset_classification.csv`` (colonnes ``texte``, ``label``)
Sortie  : ``models_saved/xlm_roberta_large_mp_chimie/``

Variables d'environnement utiles :
  HF_BASE_MODEL   (défaut: FacebookAI/xlm-roberta-large)
  TRAIN_EPOCHS, TRAIN_BATCH_SIZE, TRAIN_MAX_LENGTH, TRAIN_SEED
  TRAIN_FP16      auto | 0 | 1  (fp16 si GPU et auto/1)
  TRAIN_GRAD_ACCUM  accumulation de gradient (défaut: 1)
  TRAIN_CLEAR_HF_TOKEN  si 1/true : retire HF_TOKEN / HUGGING_FACE_HUB_TOKEN (évite 401 anonyme si token expiré)
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import torch
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models_saved"
DEFAULT_DATA = DATA_DIR / "dataset_classification.csv"
DEFAULT_OUT = MODELS_DIR / "xlm_roberta_large_mp_chimie"

LABEL2ID = {"MP": 0, "CHIMIE": 1}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}

BASE_MODEL = os.environ.get("HF_BASE_MODEL", "FacebookAI/xlm-roberta-large")
EPOCHS = int(os.environ.get("TRAIN_EPOCHS", "1"))
BATCH_SIZE = int(os.environ.get("TRAIN_BATCH_SIZE", "4"))
MAX_LENGTH = int(os.environ.get("TRAIN_MAX_LENGTH", "256"))
SEED = int(os.environ.get("TRAIN_SEED", "42"))
GRAD_ACCUM = int(os.environ.get("TRAIN_GRAD_ACCUM", "1"))

_fp16_env = os.environ.get("TRAIN_FP16", "auto").lower()
if _fp16_env in ("0", "false", "no"):
    FP16 = False
elif _fp16_env in ("1", "true", "yes"):
    FP16 = True
else:
    FP16 = bool(torch.cuda.is_available())


def _maybe_drop_hf_tokens_for_public_hub() -> None:
    """Un token expiré (env ou ~/.cache/huggingface/token) peut provoquer un 401 au lieu d’un accès anonyme."""
    if os.environ.get("TRAIN_CLEAR_HF_TOKEN", "").lower() not in ("1", "true", "yes"):
        return
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN", "HF_TOKEN_PATH"):
        os.environ.pop(key, None)
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    token_file = hf_home / "token"
    if token_file.is_file():
        try:
            token_file.unlink()
        except OSError:
            pass


def _tokenize_batch(tokenizer: AutoTokenizer, examples: Dict[str, List[str]]) -> Dict[str, Any]:
    return tokenizer(
        examples["texte"],
        truncation=True,
        padding="max_length",
        max_length=MAX_LENGTH,
    )


def load_dataset_csv(path: Path) -> tuple[Dataset, Dataset]:
    df = pd.read_csv(path)
    required = {"texte", "label"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes: {sorted(missing)}")

    df = df.copy()
    df["texte"] = df["texte"].fillna("").astype(str).str.strip()
    df["label"] = df["label"].fillna("").astype(str).str.strip().str.upper()
    df = df[(df["texte"] != "") & (df["label"].isin(LABEL2ID.keys()))].reset_index(drop=True)
    if df.empty:
        raise ValueError("Dataset vide après nettoyage.")
    if df["label"].nunique() < 2:
        raise ValueError("Il faut au moins les deux classes MP et CHIMIE dans le CSV.")

    df["labels"] = df["label"].map(LABEL2ID).astype(int)
    train_df, val_df = train_test_split(
        df[["texte", "labels"]],
        test_size=0.2,
        random_state=SEED,
        stratify=df["labels"],
    )
    return (
        Dataset.from_pandas(train_df.reset_index(drop=True)),
        Dataset.from_pandas(val_df.reset_index(drop=True)),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument(
        "--base-model",
        type=str,
        default=BASE_MODEL,
        help="Identifiant Hugging Face (défaut: env HF_BASE_MODEL ou FacebookAI/xlm-roberta-large).",
    )
    args = parser.parse_args()

    if not args.data.exists():
        raise FileNotFoundError(
            f"{args.data} introuvable. Générez-le avec: python scripts/build_dataset_classification.py"
        )

    _maybe_drop_hf_tokens_for_public_hub()
    set_seed(SEED)
    train_ds, val_ds = load_dataset_csv(args.data)
    print(
        f"Train={len(train_ds)}  Val={len(val_ds)}  base={args.base_model!r}  "
        f"fp16={FP16}  batch={args.batch_size}  grad_accum={GRAD_ACCUM}  max_len={MAX_LENGTH}"
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    train_ds = train_ds.map(lambda ex: _tokenize_batch(tokenizer, ex), batched=True)
    val_ds = val_ds.map(lambda ex: _tokenize_batch(tokenizer, ex), batched=True)
    train_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
    val_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=2,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    def compute_metrics(pred: Any) -> Dict[str, float]:
        preds = np.argmax(pred.predictions, axis=1)
        y = pred.label_ids
        return {
            "accuracy": float(accuracy_score(y, preds)),
            "f1_macro": float(f1_score(y, preds, average="macro")),
        }

    args.output.mkdir(parents=True, exist_ok=True)
    targs = TrainingArguments(
        output_dir=str(args.output / "checkpoints"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=GRAD_ACCUM,
        learning_rate=2e-5,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=10,
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        report_to="none",
        seed=SEED,
        fp16=FP16,
        gradient_checkpointing=True,
    )

    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics,
    )
    trainer.train()
    trainer.save_model(str(args.output))
    tokenizer.save_pretrained(str(args.output))
    print(f"Modèle sauvegardé: {args.output}")


if __name__ == "__main__":
    main()
