from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from langsmith import traceable
from pydantic import BaseModel, Field
from transformers import pipeline


PROJECT_ROOT = Path(__file__).resolve().parent
LEVEL1_DIR = Path(os.environ.get("LEVEL1_MODEL_DIR", str(PROJECT_ROOT / "local_models" / "level1_mp_pdr")))

DEVICE = 0 if torch.cuda.is_available() else -1


def _normalize_text(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower()).strip()


@traceable(name="classification_mp_pdr_inference", run_type="chain")
def _run_level1_pipe(pipe: Any, text: str) -> dict[str, Any]:
    """Inférence HF MP vs PDR tracée dans LangSmith."""
    out = pipe(text)[0]
    return dict(out)


class ClassifyRequest(BaseModel):
    id_article_erp: str = Field(default="", description="Identifiant article ERP")
    description_texte: str = Field(default="", description="Texte brut de l'article à classifier")
    description_categorie: str = Field(default="", description="Contexte machine/zone")


class ClassifyResponse(BaseModel):
    id_article_erp: str
    input_text: str
    level1: dict[str, Any]
    categorie_principale: str = Field(
        ...,
        description="Destination métier principale : production (MP) ou magasin PDR (PDR).",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not LEVEL1_DIR.exists():
        raise RuntimeError(f"Level1 model directory not found: {LEVEL1_DIR}")

    app.state.level1_pipe = pipeline(
        task="text-classification",
        model=str(LEVEL1_DIR),
        tokenizer=str(LEVEL1_DIR),
        device=DEVICE,
    )
    yield


app = FastAPI(
    title="Sotipapier Classification Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/api/v1/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest) -> ClassifyResponse:
    """Classification binaire unique : MP (Matière Première) vs PDR (Pièce de rechange)."""
    texte_brut = _normalize_text(req.description_texte)
    if not texte_brut:
        raise HTTPException(status_code=422, detail="description_texte vide après nettoyage.")

    level1_out = _run_level1_pipe(app.state.level1_pipe, texte_brut)
    level1_label = str(level1_out.get("label", "")).upper()
    level1_score = float(level1_out.get("score", 0.0))

    if level1_label == "MP":
        categorie_principale = "Ligne de production (Matière Première)"
    elif level1_label == "PDR":
        categorie_principale = "Magasin pièces de rechange (PDR)"
    else:
        categorie_principale = "Indéterminée"

    return ClassifyResponse(
        id_article_erp=req.id_article_erp,
        input_text=texte_brut,
        level1={"label": level1_label, "score": level1_score},
        categorie_principale=categorie_principale,
    )
