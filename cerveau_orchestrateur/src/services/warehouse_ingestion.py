"""Admin warehouse data ingestion and classification pipeline."""
from __future__ import annotations

import asyncio
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from src.models.entities import WarehouseInventoryRecord, WarehouseStockSnapshot
from src.tools.classification_api import post_classification_full, post_pdr_mp_classification

INGEST_JOBS: dict[str, dict[str, Any]] = {}
INGEST_JOBS_LOCK = Lock()


def create_ingest_job(filename: str, total_rows: int) -> str:
    job_id = f"wh-{uuid4().hex[:12]}"
    payload = {
        "job_id": job_id,
        "filename": filename,
        "status": "queued",
        "total_rows": int(total_rows),
        "processed_rows": 0,
        "progress_pct": 0.0,
        "counts": {"MP": 0, "PDR": 0, "CHIMIE": 0, "ERROR": 0},
        "qty_by_label_kg": {"MP": 0.0, "PDR": 0.0, "CHIMIE": 0.0, "ERROR": 0.0},
        "cancel_requested": False,
        "error": "",
        "batch_id": "",
    }
    with INGEST_JOBS_LOCK:
        INGEST_JOBS[job_id] = payload
    return job_id


def get_ingest_job(job_id: str) -> dict[str, Any] | None:
    with INGEST_JOBS_LOCK:
        row = INGEST_JOBS.get(job_id)
        return dict(row) if row else None


def cancel_ingest_job(job_id: str) -> bool:
    with INGEST_JOBS_LOCK:
        row = INGEST_JOBS.get(job_id)
        if not row:
            return False
        status = str(row.get("status") or "").lower()
        if status in {"done", "error", "cancelled"}:
            return True
        row["cancel_requested"] = True
        row["status"] = "cancelling"
        return True


def _update(job_id: str, **kwargs: Any) -> None:
    with INGEST_JOBS_LOCK:
        if job_id not in INGEST_JOBS:
            return
        INGEST_JOBS[job_id].update(kwargs)


async def run_ingest_job(job_id: str, *, filename: str, rows: list[dict[str, str]], db: Session) -> None:
    _update(job_id, status="running")
    batch_id = f"batch-{uuid4().hex[:10]}"
    _update(job_id, batch_id=batch_id)
    total = max(1, len(rows))

    # Replace previous warehouse snapshot with the new extract.
    db.query(WarehouseInventoryRecord).delete()
    db.query(WarehouseStockSnapshot).delete()
    db.commit()

    staged: list[WarehouseInventoryRecord] = []
    staged_snapshot: list[WarehouseStockSnapshot] = []
    for i, row in enumerate(rows, start=1):
        current = get_ingest_job(job_id) or {}
        if bool(current.get("cancel_requested")):
            if staged:
                db.add_all(staged)
                db.add_all(staged_snapshot)
                db.commit()
            _update(job_id, status="cancelled")
            return
        id_article = str(row.get("id_article_erp") or f"ROW-{i}")
        description = str(row.get("description") or "")
        categorie = str(row.get("categorie") or "")
        stock_quantity_kg = float(str(row.get("stock_quantity_kg") or "0").replace(",", ".") or 0.0)
        snapshot_date = str(row.get("snapshot_date") or "").strip()
        provided_final_label = str(row.get("provided_final_label") or "").upper().strip()

        mp_pdr = "ERROR"
        mp_chimie = "N/A"
        final_label = "ERROR"
        error = ""

        # Flexible chain: if file already provides a valid final label, trust it.
        if provided_final_label in {"MP", "PDR", "CHIMIE"}:
            final_label = provided_final_label
            mp_pdr = "PDR" if final_label == "PDR" else "MP"
            mp_chimie = "CHIMIE" if final_label == "CHIMIE" else "MP"
        else:
            stage1 = await post_pdr_mp_classification(id_article, description, categorie)
            if not stage1.get("ok"):
                error = str(stage1.get("error", "ERROR_STAGE1"))
            else:
                mp_pdr = str(stage1.get("level1", "ERROR")).upper()
                if mp_pdr == "PDR":
                    final_label = "PDR"
                elif mp_pdr == "MP":
                    stage2 = await post_classification_full(id_article, description, categorie)
                    if not stage2.get("ok"):
                        error = str(stage2.get("error", "ERROR_STAGE2"))
                        mp_chimie = "ERROR"
                        final_label = "MP"
                    else:
                        mp_chimie = str(stage2.get("level1", "ERROR")).upper()
                        final_label = mp_chimie if mp_chimie in {"MP", "CHIMIE"} else "MP"
                else:
                    error = f"ERROR_STAGE1_LABEL:{mp_pdr}"

        key = final_label if final_label in {"MP", "PDR", "CHIMIE"} else "ERROR"
        with INGEST_JOBS_LOCK:
            if job_id in INGEST_JOBS:
                INGEST_JOBS[job_id]["counts"][key] += 1
                INGEST_JOBS[job_id]["qty_by_label_kg"][key] += float(stock_quantity_kg or 0.0)
                if error:
                    INGEST_JOBS[job_id]["counts"]["ERROR"] += 1

        staged.append(
            WarehouseInventoryRecord(
                batch_id=batch_id,
                source_file=filename,
                id_article_erp=id_article,
                description=description,
                categorie=categorie,
                stage1_mp_pdr=mp_pdr,
                stage2_mp_chimie=mp_chimie,
                final_label=final_label,
                error=error,
            )
        )
        staged_snapshot.append(
            WarehouseStockSnapshot(
                batch_id=batch_id,
                source_file=filename,
                snapshot_date=snapshot_date,
                id_article_erp=id_article,
                description=description,
                categorie=categorie,
                stock_quantity_kg=stock_quantity_kg,
                stage1_mp_pdr=mp_pdr,
                stage2_mp_chimie=mp_chimie,
                final_label=final_label,
            )
        )
        if len(staged) >= 200:
            db.add_all(staged)
            db.add_all(staged_snapshot)
            db.commit()
            staged.clear()
            staged_snapshot.clear()

        _update(
            job_id,
            processed_rows=i,
            progress_pct=round((i / total) * 100.0, 2),
        )
        await asyncio.sleep(0)

    if staged:
        db.add_all(staged)
        db.add_all(staged_snapshot)
        db.commit()
    _update(job_id, status="done", progress_pct=100.0)
