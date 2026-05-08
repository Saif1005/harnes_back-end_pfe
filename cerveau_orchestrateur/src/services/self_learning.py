"""Self-learning job orchestration from long-term memory."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.models.entities import LongTermMemory

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_job(job_id: str, **kwargs: object) -> None:
    with JOBS_LOCK:
        if job_id not in JOBS:
            return
        JOBS[job_id].update(kwargs)
        JOBS[job_id]["updated_at"] = _utcnow_iso()


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        row = JOBS.get(job_id)
        return dict(row) if row else None


def create_retrain_job(*, target_model: str) -> str:
    job_id = f"sl-{uuid.uuid4().hex[:12]}"
    now = _utcnow_iso()
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "detail": "Job en file d'attente.",
            "target_model": target_model,
            "dataset_path": "",
            "output_path": "",
            "memories_used": 0,
            "started_at": now,
            "updated_at": now,
        }
    return job_id


def run_retrain_job(
    job_id: str,
    *,
    db: Session,
    base_path: str,
    max_memories: int,
) -> None:
    _set_job(job_id, status="running", detail="Collecte des memories long terme...")
    os.makedirs(base_path, exist_ok=True)

    rows = (
        db.query(LongTermMemory)
        .filter(LongTermMemory.namespace == "ask_agent_outputs")
        .order_by(LongTermMemory.updated_at.desc())
        .limit(max(1, int(max_memories)))
        .all()
    )
    memories = list(reversed(rows))
    dataset_path = os.path.join(base_path, f"{job_id}_dataset.jsonl")
    output_path = os.path.join(base_path, f"{job_id}_training_summary.json")
    _set_job(
        job_id,
        detail=f"Préparation dataset ({len(memories)} memories)...",
        dataset_path=dataset_path,
        output_path=output_path,
        memories_used=len(memories),
    )

    with open(dataset_path, "w", encoding="utf-8") as f:
        for m in memories:
            try:
                meta = json.loads(str(m.metadata_json or "{}"))
            except Exception:  # noqa: BLE001
                meta = {}
            sample = {
                "instruction": "Améliorer la réponse de l'assistant industriel.",
                "input": {
                    "route_intent": str(meta.get("route_intent") or ""),
                    "article_id": str(meta.get("article_id") or ""),
                },
                "output": str(m.memory_value or ""),
                "created_at": m.updated_at.isoformat(),
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    _set_job(job_id, detail="Simulation réentraînement Mistral en cours...")
    time.sleep(2)
    summary = {
        "job_id": job_id,
        "target_model": get_job(job_id).get("target_model", "mistral:7b-instruct") if get_job(job_id) else "mistral:7b-instruct",
        "status": "prepared",
        "note": (
            "Dataset prêt pour fine-tuning/RAG tuning. "
            "Le réentraînement complet du modèle Mistral nécessite un pipeline externe GPU."
        ),
        "dataset_path": dataset_path,
        "memories_used": len(memories),
        "generated_at": _utcnow_iso(),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    _set_job(job_id, status="done", detail="Self-learning prêt: dataset + résumé générés.")
