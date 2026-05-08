from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness_backend.config.settings import SETTINGS

try:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline  # type: ignore
except Exception:  # noqa: BLE001
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    pipeline = None

_RUNTIME_PIPELINE = None
_RUNTIME_MANIFEST = None


def load_checkpoint_manifest() -> dict[str, Any] | None:
    manifest_path = Path(SETTINGS.classification_checkpoint_manifest)
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _ensure_pipeline() -> tuple[Any | None, dict[str, Any] | None]:
    global _RUNTIME_PIPELINE, _RUNTIME_MANIFEST
    if _RUNTIME_PIPELINE is not None:
        return _RUNTIME_PIPELINE, _RUNTIME_MANIFEST
    manifest = load_checkpoint_manifest()
    if manifest is None:
        return None, None
    if pipeline is None or AutoTokenizer is None or AutoModelForSequenceClassification is None:
        return None, manifest
    ckpt_dir = str(manifest.get("checkpoint_dir", SETTINGS.classification_checkpoint_dir))
    try:
        tok = AutoTokenizer.from_pretrained(ckpt_dir)
        mdl = AutoModelForSequenceClassification.from_pretrained(ckpt_dir)
        _RUNTIME_PIPELINE = pipeline("text-classification", model=mdl, tokenizer=tok, truncation=True)
        _RUNTIME_MANIFEST = manifest
        return _RUNTIME_PIPELINE, _RUNTIME_MANIFEST
    except Exception:  # noqa: BLE001
        return None, manifest


def predict_with_checkpoint(text: str) -> dict[str, Any] | None:
    clf, manifest = _ensure_pipeline()
    if clf is None:
        return None
    out = clf(text or "")
    if not isinstance(out, list) or not out:
        return None
    first = out[0]
    if not isinstance(first, dict):
        return None
    label_raw = str(first.get("label", "MP")).upper().strip()
    score = float(first.get("score", 0.0))
    label_map = dict((manifest or {}).get("label_map", {}))
    label = str(label_map.get(label_raw, label_raw)).upper()
    if label not in {"MP", "CHIMIE", "PDR"}:
        label = "MP"
    return {
        "label": label,
        "score": score,
        "model_used": SETTINGS.classification_model_name,
        "source": "checkpoint",
    }

