from __future__ import annotations

import argparse
import random
import re
from pathlib import Path
from typing import Iterable

import pandas as pd


def _norm_col(col: str) -> str:
    return re.sub(r"\s+", " ", str(col).strip().lower())


def _pick_col(columns: Iterable[str], candidates: list[str]) -> str | None:
    normalized = {_norm_col(c): c for c in columns}
    for cand in candidates:
        out = normalized.get(_norm_col(cand))
        if out:
            return out
    return None


def _pick_col_by_keywords(columns: Iterable[str], include_all: list[str]) -> str | None:
    for c in columns:
        n = _norm_col(c)
        if all(k in n for k in include_all):
            return c
    return None


def _to_float(value: object) -> float:
    raw = str(value or "").strip().replace(" ", "")
    if not raw:
        return 0.0
    neg = False
    if raw.startswith("(") and raw.endswith(")"):
        neg = True
        raw = raw[1:-1]
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        val = float(raw)
    except Exception:  # noqa: BLE001
        return 0.0
    return -val if neg else val


def _read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        last_err = ""
        for sep in (";", ",", "\t", "|"):
            for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                try:
                    df = pd.read_csv(path, sep=sep, encoding=enc)
                    if len(df.columns) >= 2:
                        return df
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
        raise RuntimeError(f"Unable to read CSV '{path}': {last_err}")
    raise ValueError(f"Unsupported input format: {path.suffix}")


def build_compatible_dataset(input_path: Path, output_path: Path, seed: int | None = None) -> pd.DataFrame:
    df = _read_table(input_path)
    if df.empty:
        raise ValueError("Input dataset is empty.")

    text_col = _pick_col(df.columns, ["texte", "text", "description", "designation", "libelle", "ingredient"])
    if text_col is None:
        text_col = _pick_col_by_keywords(df.columns, ["desc"]) or _pick_col_by_keywords(df.columns, ["ingredient"])
    if text_col is None:
        raise ValueError(f"Unable to detect text column in: {list(df.columns)}")

    quantity_col = _pick_col(
        df.columns,
        [
            "quantity_kg",
            "quantite_kg",
            "stock_quantity_kg",
            "quantity",
            "quantite",
            "qty",
            "qte",
            "consumption_reelle_kg",
            "quantity_actual_kg",
            "quantity_theoretical_kg",
        ],
    )
    if quantity_col is None:
        quantity_col = _pick_col_by_keywords(df.columns, ["quant"]) or _pick_col_by_keywords(df.columns, ["stock"])

    article_col = _pick_col(df.columns, ["family_pf", "article", "id_article_erp", "code_article", "code article"])
    machine_col = _pick_col(df.columns, ["code_machine", "machine", "atelier", "zone", "categorie"])

    out = pd.DataFrame()
    out["texte"] = df[text_col].fillna("").astype(str).str.strip()
    if article_col:
        out["article_context"] = df[article_col].fillna("").astype(str).str.strip()
    else:
        out["article_context"] = ""
    if machine_col:
        out["machine_context"] = df[machine_col].fillna("").astype(str).str.strip()
    else:
        out["machine_context"] = ""

    # Build a classifier-friendly text while keeping "texte" as main model input.
    out["texte"] = (
        out["texte"]
        + " [article: "
        + out["article_context"]
        + "] [machine: "
        + out["machine_context"]
        + "]"
    ).str.replace(r"\s+", " ", regex=True).str.strip()

    if seed is not None:
        random.seed(int(seed))

    if quantity_col:
        out["quantity_kg"] = df[quantity_col].map(_to_float).abs()
    else:
        # No quantity in raw file: generate random proxy quantity for prediction training.
        # Range chosen to simulate heterogeneous stock/consumption levels.
        out["quantity_kg"] = [round(random.uniform(1.0, 500.0), 3) for _ in range(len(out))]

    # Remove labels by design. Keep only compatible columns for classification + prediction.
    out = out[["texte", "quantity_kg", "article_context", "machine_context"]]
    out = out[out["texte"] != ""].reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate compatible unlabeled dataset (texte + quantity_kg) from raw unorganized data."
    )
    parser.add_argument("--input", required=True, help="Path to input CSV/XLSX raw dataset")
    parser.add_argument("--output", required=True, help="Path to output compatible CSV")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed for reproducible quantity_kg")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    df = build_compatible_dataset(input_path, output_path, seed=args.seed)
    print(f"Compatible dataset generated: {output_path}")
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
