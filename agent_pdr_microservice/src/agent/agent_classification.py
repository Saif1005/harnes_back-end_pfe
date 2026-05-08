"""
API FastAPI : classification ingrédient MP vs CHIMIE (XLM-RoBERTa-large fine-tuné).

Port par défaut : 8001 (variable d'environnement CLASSIFICATION_PORT).
"""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from langsmith import traceable
from transformers import pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = Path(
    os.environ.get(
        "CLASSIFICATION_MODEL_DIR",
        str(PROJECT_ROOT / "models_saved" / "xlm_roberta_large_mp_chimie"),
    )
)
DEVICE = 0 if torch.cuda.is_available() else -1


def _normalize_text(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").strip())


@traceable(name="classification_mp_chimie_inference", run_type="chain")
def _run_mp_chimie_pipe(pipe: Any, text: str) -> dict[str, Any]:
    """Inférence HF tracée dans LangSmith (projet = LANGSMITH_PROJECT sur l’hôte)."""
    out = pipe(text)[0]
    return dict(out)


class ClassifyBody(BaseModel):
    description: str = Field(..., description="Description / libellé de l'ingrédient industriel")


class ClassifyResponse(BaseModel):
    categorie_principale: str = Field(..., description="Libellé métier : Matière première ou Produit chimique")
    level1: str = Field(..., description="MP ou CHIMIE")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MODEL_DIR.exists():
        raise RuntimeError(
            f"Répertoire modèle introuvable: {MODEL_DIR}. "
            "Exécutez scripts/train_xlm_roberta.py ou montez models_saved/xlm_roberta_large_mp_chimie."
        )
    app.state.pipe = pipeline(
        task="text-classification",
        model=str(MODEL_DIR),
        tokenizer=str(MODEL_DIR),
        device=DEVICE,
    )
    yield


app = FastAPI(
    title="Classification MP / CHIMIE (Sotipapier)",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/api/v1/classify", response_model=ClassifyResponse)
async def classify(body: ClassifyBody) -> ClassifyResponse:
    texte = _normalize_text(body.description)
    if not texte:
        raise HTTPException(status_code=422, detail="description vide après nettoyage.")

    out = _run_mp_chimie_pipe(app.state.pipe, texte)
    raw_label = str(out.get("label", ""))
    score = float(out.get("score", 0.0))
    cfg = getattr(app.state.pipe.model, "config", None)
    id2label = getattr(cfg, "id2label", None) if cfg is not None else None
    if isinstance(id2label, dict) and raw_label.startswith("LABEL_"):
        try:
            idx = int(raw_label.split("_")[-1])
            label = str(id2label.get(idx, raw_label)).upper()
        except (ValueError, IndexError):
            label = raw_label.upper()
    else:
        label = raw_label.upper()

    if label not in {"MP", "CHIMIE"}:
        raise HTTPException(
            status_code=500,
            detail=f"Label modèle inattendu: {label!r} (score={score})",
        )

    if label == "MP":
        cat = "Matiere premiere(fibre/pate/papier)"
    else:
        cat = "Produit chimique (additif de process)"

    return ClassifyResponse(categorie_principale=cat, level1=label)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "model_dir": str(MODEL_DIR), "cuda": torch.cuda.is_available()}
