"""Classification de fichiers pièces de rechange (temps réel via polling)."""
from __future__ import annotations

import asyncio
import io
import re
from threading import Lock
from typing import Any
from uuid import uuid4

import pandas as pd

from src.tools.classification_api import post_classification_full, post_pdr_mp_classification

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = Lock()


def _read_csv_flexible(content: bytes) -> pd.DataFrame:
    # CSV terrain: séparateur parfois ';' et encodage parfois latin-1.
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(encoding)
            return pd.read_csv(io.StringIO(text), dtype=str, sep=None, engine="python")
        except Exception:  # noqa: BLE001
            continue
    raise ValueError("Impossible de lire le CSV (encodage/séparateur non reconnu).")


def _pick_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        key = cand.lower().strip()
        if key in normalized:
            return normalized[key]
    for col in columns:
        low = col.lower().strip()
        if any(c in low for c in candidates):
            return col
    return None


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _to_float(value: Any) -> float:
    raw = _safe_text(value).replace(" ", "")
    if not raw:
        return 0.0
    # Formats terrain:
    # - "1 234,56"
    # - "1.234,56"
    # - "(123,45)" (négatif comptable)
    neg = False
    if raw.startswith("(") and raw.endswith(")"):
        neg = True
        raw = raw[1:-1]
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    if not raw:
        return 0.0
    try:
        value_f = float(raw)
        return -value_f if neg else value_f
    except Exception:  # noqa: BLE001
        return 0.0


def _normalize_stock_label(value: Any) -> str:
    raw = _safe_text(value).upper().replace("-", " ").replace("_", " ").strip()
    if not raw:
        return ""
    aliases = {
        "MATIERE PREMIERE": "MP",
        "MATIERE PREMIERES": "MP",
        "MATIERE PRIMAIRE": "MP",
        "MATIERE PRIMAIRE": "MP",
        "M P": "MP",
        "PIECE DE RECHANGE": "PDR",
        "PIECES DE RECHANGE": "PDR",
        "PIECE RECHANGE": "PDR",
        "PIECES RECHANGE": "PDR",
        "CHEMIE": "CHIMIE",
        "CHIMIQUE": "CHIMIE",
    }
    if raw in {"MP", "PDR", "CHIMIE"}:
        return raw
    return aliases.get(raw, "")


def _normalize_ingredient_description(value: Any) -> str:
    """
    Normalise un libellé ingrédient:
    - retire le contexte article entre crochets: "[Kraft] ...",
    - réduit les espaces,
    - retire les séparateurs en bord.
    """
    text = _safe_text(value)
    if not text:
        return ""
    text = re.sub(r"^\s*\[[^\]]+\]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;")
    return text


def parse_uploaded_file(content: bytes, filename: str, categorie_default: str = "") -> list[dict[str, str]]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        df = _read_csv_flexible(content)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        raise ValueError("Format non supporté. Utilisez CSV/XLSX.")

    if df.empty:
        return []

    columns = [str(c) for c in df.columns]
    id_col = _pick_column(
        columns,
        [
            "id_article_erp",
            "id_erp",
            "id erp",
            "reference",
            "référence",
            "code_article",
            "code article",
            "article_id",
        ],
    )
    desc_col = _pick_column(
        columns,
        [
            "texte",
            "description",
            "description_article",
            "description article",
            "designation",
            "désignation",
            "description_texte",
            "libelle",
            "libellé",
            "article",
        ],
    )
    cat_col = _pick_column(
        columns,
        [
            "categorie",
            "catégorie",
            "zone",
            "machine",
            "description_categorie",
            "description catégorie",
            "code machine",
        ],
    )
    qty_col = _pick_column(
        columns,
        [
            "stock",
            "stock_kg",
            "stock kg",
            "qte",
            "qte_stock",
            "quantite",
            "quantité",
            "quantity",
            "solde",
            "disponible",
        ],
    )
    date_col = _pick_column(
        columns,
        [
            "date",
            "date_extrait",
            "date extrait",
            "snapshot_date",
            "date_stock",
            "date stock",
            "annee",
            "année",
            "year",
        ],
    )
    label_col = _pick_column(
        columns,
        [
            "final_label",
            "label_final",
            "label",
            "classe",
            "class",
            "categorie_finale",
            "cat_finale",
            "type_matiere",
            "type matière",
        ],
    )

    if not desc_col:
        # Fallback: première colonne textuelle non-technique.
        skip = {c for c in [id_col, cat_col] if c}
        for col in columns:
            if col in skip:
                continue
            values = df[col].dropna().astype(str).str.strip()
            non_empty = values[values != ""]
            if len(non_empty) > 0:
                desc_col = col
                break
    if not desc_col:
        raise ValueError(
            "Colonne description introuvable. Attendu ex: description/designation/libelle/article."
        )

    aggregated: dict[tuple[str, str, str, str], dict[str, str | float]] = {}
    for row_num, (_idx, row) in enumerate(df.iterrows(), start=1):
        description = _normalize_ingredient_description(row.get(desc_col))
        if not description:
            continue
        id_article = _safe_text(row.get(id_col)) if id_col else f"ROW-{row_num}"
        categorie = _safe_text(row.get(cat_col)) if cat_col else ""
        if not categorie:
            categorie = (categorie_default or "").strip()
        stock_qty = abs(_to_float(row.get(qty_col))) if qty_col else 0.0
        snapshot_date = _safe_text(row.get(date_col)) if date_col else ""
        provided_final_label = _normalize_stock_label(row.get(label_col)) if label_col else ""
        agg_key = (description.lower(), categorie, snapshot_date, provided_final_label)
        bucket = aggregated.get(agg_key)
        if bucket is None:
            aggregated[agg_key] = {
                "id_article_erp": id_article,
                "description": description,
                "categorie": categorie,
                "stock_quantity_kg": float(stock_qty),
                "snapshot_date": snapshot_date,
                "provided_final_label": provided_final_label,
            }
        else:
            bucket["stock_quantity_kg"] = float(bucket.get("stock_quantity_kg", 0.0) or 0.0) + float(stock_qty)

    rows: list[dict[str, str]] = []
    for idx, item in enumerate(aggregated.values(), start=1):
        rows.append(
            {
                "id_article_erp": str(item.get("id_article_erp") or f"ING-{idx}"),
                "description": str(item.get("description") or ""),
                "categorie": str(item.get("categorie") or ""),
                "stock_quantity_kg": str(round(float(item.get("stock_quantity_kg") or 0.0), 6)),
                "snapshot_date": str(item.get("snapshot_date") or ""),
                "provided_final_label": str(item.get("provided_final_label") or ""),
            }
        )
    return rows


def create_job(filename: str, total_rows: int) -> str:
    job_id = str(uuid4())
    payload = {
        "job_id": job_id,
        "filename": filename,
        "status": "queued",
        "total_rows": int(total_rows),
        "processed_rows": 0,
        "progress_pct": 0.0,
        "counts": {"MP": 0, "PDR": 0, "CHIMIE": 0, "ERROR": 0},
        "results": [],
        "error": "",
    }
    with JOBS_LOCK:
        JOBS[job_id] = payload
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with JOBS_LOCK:
        data = JOBS.get(job_id)
        if not data:
            return None
        return dict(data)


def _update_job(job_id: str, **kwargs: Any) -> None:
    with JOBS_LOCK:
        if job_id not in JOBS:
            return
        JOBS[job_id].update(kwargs)


async def run_job(job_id: str, rows: list[dict[str, str]]) -> None:
    _update_job(job_id, status="running")
    total = max(1, len(rows))
    for i, row in enumerate(rows, start=1):
        id_article = row["id_article_erp"]
        description = row["description"]
        categorie = row["categorie"]

        stage1 = await post_pdr_mp_classification(id_article, description, categorie)
        mp_pdr = "ERROR"
        mp_chimie = "N/A"
        final_label = "ERROR"
        error = ""

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

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job["processed_rows"] = i
            job["progress_pct"] = round((i / total) * 100.0, 2)
            job["counts"][final_label if final_label in {"MP", "PDR", "CHIMIE"} else "ERROR"] += 1
            if error:
                job["counts"]["ERROR"] += 1
            job["results"].append(
                {
                    "id_article_erp": id_article,
                    "description": description,
                    "categorie": categorie,
                    "stage1_mp_pdr": mp_pdr,
                    "stage2_mp_chimie": mp_chimie,
                    "final_label": final_label,
                    "error": error,
                }
            )

        # Rend la progression visible côté frontend même sur des petits fichiers.
        await asyncio.sleep(0)

    _update_job(job_id, status="done", progress_pct=100.0)

