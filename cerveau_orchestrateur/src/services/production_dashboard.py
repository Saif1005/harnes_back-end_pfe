"""Agrégations dashboard production à partir du CSV recette réel."""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.core.config import get_settings


def _load_csv() -> pd.DataFrame:
    settings = get_settings()
    csv_path = settings.recipe_correlation_csv_path
    df = pd.read_csv(csv_path)
    required_cols = {"Year", "Month", "Code_machine", "family_pf", "recipe_key", "quantity_produced_ton"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes dans le CSV recette: {sorted(missing)}")
    return df


def _normalize(df: pd.DataFrame, start_year: int) -> pd.DataFrame:
    out = df.copy()
    out["Year"] = pd.to_numeric(out["Year"], errors="coerce").fillna(0).astype(int)
    out["Month"] = pd.to_numeric(out["Month"], errors="coerce").fillna(0).astype(int)
    out["family_pf"] = out["family_pf"].fillna("").astype(str).str.strip()
    out["Code_machine"] = out["Code_machine"].fillna("").astype(str).str.strip()
    out["recipe_key"] = out["recipe_key"].fillna("").astype(str).str.strip()
    out["quantity_produced_ton"] = pd.to_numeric(out["quantity_produced_ton"], errors="coerce").fillna(0.0)

    out = out[
        (out["Year"] >= int(start_year))
        & (out["Month"] >= 1)
        & (out["Month"] <= 12)
        & (out["family_pf"] != "")
    ].copy()
    if out.empty:
        return out

    # Le CSV a une ligne par ingrédient: on déduplique les lots de production avant agrégation.
    lot_keys = ["Year", "Month", "Code_machine", "family_pf", "recipe_key", "quantity_produced_ton"]
    out = out.drop_duplicates(subset=lot_keys)
    out["period"] = out["Year"].map(lambda y: f"{int(y):04d}") + "-" + out["Month"].map(lambda m: f"{int(m):02d}")
    return out


def build_production_dashboard(
    start_year: int = 2017, max_articles: int = 6, selected_article: str = ""
) -> dict[str, Any]:
    raw = _load_csv()
    data = _normalize(raw, start_year=start_year)
    if data.empty:
        return {
            "start_year": int(start_year),
            "summary": {"unique_articles": 0, "total_quantity_ton": 0.0, "active_lines": 0},
            "article_options": [],
            "monthly_totals": [],
            "top_articles": [],
            "article_trends": [],
        }

    monthly_totals_df = (
        data.groupby("period", as_index=False)["quantity_produced_ton"].sum().sort_values("period", ascending=True)
    )
    monthly_totals = [
        {"period": str(row["period"]), "quantity_ton": round(float(row["quantity_produced_ton"]), 3)}
        for _, row in monthly_totals_df.iterrows()
    ]

    by_article = (
        data.groupby("family_pf", as_index=False)["quantity_produced_ton"]
        .sum()
        .sort_values("quantity_produced_ton", ascending=False)
    )
    all_articles = [str(v) for v in by_article["family_pf"].tolist()]

    wanted = []
    selected = selected_article.strip()
    if selected and selected in all_articles:
        wanted.append(selected)
    for article in all_articles:
        if article not in wanted:
            wanted.append(article)
        if len(wanted) >= max(1, int(max_articles)):
            break

    article_period = (
        data.groupby(["family_pf", "period"], as_index=False)["quantity_produced_ton"]
        .sum()
        .sort_values(["family_pf", "period"], ascending=True)
    )
    periods = [str(v) for v in monthly_totals_df["period"].tolist()]
    article_trends: list[dict[str, Any]] = []
    for article in wanted:
        subset = article_period[article_period["family_pf"] == article]
        per_map = {str(r["period"]): round(float(r["quantity_produced_ton"]), 3) for _, r in subset.iterrows()}
        points = [{"period": p, "quantity_ton": float(per_map.get(p, 0.0))} for p in periods]
        article_trends.append({"article": article, "points": points})

    top_articles = [
        {"article": str(row["family_pf"]), "quantity_ton": round(float(row["quantity_produced_ton"]), 3)}
        for _, row in by_article.head(max(1, int(max_articles))).iterrows()
    ]

    latest_period = monthly_totals[-1]["period"] if monthly_totals else ""
    active_lines = 0
    if latest_period:
        active_lines = int(data[data["period"] == latest_period]["Code_machine"].replace("", pd.NA).dropna().nunique())

    return {
        "start_year": int(start_year),
        "summary": {
            "unique_articles": int(data["family_pf"].nunique()),
            "total_quantity_ton": round(float(data["quantity_produced_ton"].sum()), 3),
            "active_lines": int(active_lines),
        },
        "article_options": all_articles,
        "monthly_totals": monthly_totals,
        "top_articles": top_articles,
        "article_trends": article_trends,
    }
