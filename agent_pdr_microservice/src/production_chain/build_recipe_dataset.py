from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
from sklearn.preprocessing import MultiLabelBinarizer


# =============================================================================
# Paths (easy to edit)
# =============================================================================
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RATIOS_PATH = PROJECT_ROOT / "data_sources" / "Data_Produc_Qual" / "RATIOS STANDARDS.csv.xlsx"
ARTICLES_PATH = PROJECT_ROOT / "data_sources" / "Data_Produc_Qual" / "db_article.csv"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "recipe_train_multilabel.csv"


# =============================================================================
# Column candidates (adapt if your files use other names)
# =============================================================================
RATIOS_PRODUCT_CODE_CANDIDATES = [
    "code produit fini",
    "code_produit_fini",
    "produit fini",
    "code pf",
    "pf",
]
RATIOS_COMPONENT_CODE_CANDIDATES = [
    "code composant",
    "code_composant",
    "code mp",
    "matiere premiere",
    "matière première",
    "code article",
    "article",
]
ARTICLE_CODE_CANDIDATES = [
    "code article",
    "article",
    "item no_",
    "item_no_",
    "item no",
    "code",
]
ARTICLE_DESCRIPTION_CANDIDATES = [
    "description",
    "description_1",
    "designation",
    "désignation",
    "libelle",
    "libellé",
]
ARTICLE_CATEGORY_CANDIDATES = [
    "description_categorie",
    "categorie",
    "catégorie",
    "zone",
    "machine",
    "famille",
]


def _norm_col(col: str) -> str:
    return re.sub(r"\s+", " ", str(col).strip().lower())


def _find_col_by_candidates(columns: Iterable[str], candidates: list[str]) -> Optional[str]:
    cols = list(columns)
    cols_norm = {_norm_col(c): c for c in cols}
    for cand in candidates:
        c = cols_norm.get(_norm_col(cand))
        if c is not None:
            return c
    return None


def _find_col_by_keywords(columns: Iterable[str], include_all: list[str]) -> Optional[str]:
    for col in columns:
        n = _norm_col(col)
        if all(k in n for k in include_all):
            return col
    return None


def _detect_csv_sep(path: Path) -> str:
    # Try separators from most likely to least likely.
    seps = [";", "\t", ",", "|"]
    best_sep = ";"
    best_cols = 0
    for sep in seps:
        try:
            df = pd.read_csv(path, sep=sep, nrows=20, encoding="utf-8-sig")
            ncols = len(df.columns)
            if ncols > best_cols:
                best_cols = ncols
                best_sep = sep
        except Exception:
            continue
    return best_sep


def _read_ratios(path: Path) -> tuple[pd.DataFrame, str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Ratios file not found: {path}")

    # Try all sheets, keep the first one where we can detect product/component code columns.
    xls = pd.ExcelFile(path)
    last_error = "No sheet read yet"
    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(path, sheet_name=sheet)
            if df.empty:
                continue

            product_col = _find_col_by_candidates(df.columns, RATIOS_PRODUCT_CODE_CANDIDATES)
            component_col = _find_col_by_candidates(df.columns, RATIOS_COMPONENT_CODE_CANDIDATES)

            # Fallback by keywords if exact candidates do not match.
            if product_col is None:
                product_col = _find_col_by_keywords(df.columns, ["produit"])
            if component_col is None:
                component_col = _find_col_by_keywords(df.columns, ["composant"]) or _find_col_by_keywords(
                    df.columns, ["article"]
                )

            if product_col and component_col:
                return df, product_col, component_col
            last_error = (
                f"Sheet '{sheet}': unable to detect product/component columns. "
                f"Detected: product={product_col}, component={component_col}"
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"Sheet '{sheet}' read error: {exc}"

    # Fallback for Sotipapier matrix layout:
    # - Row 1: machine/zone (e.g. PM2, PM3...)
    # - Row 2: finished products (e.g. Kraft, Fluting...)
    # - Rows >= 3: component names + numeric ratios per product column
    # This fallback converts matrix -> long format with [component_code, product_code].
    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(path, sheet_name=sheet, header=None)
            if raw.empty or raw.shape[0] < 4 or raw.shape[1] < 3:
                continue

            product_row = raw.iloc[1]
            machine_row = raw.iloc[0]
            records: list[dict[str, str]] = []

            def _mk_component_name(v0: object, v1: object) -> str:
                a = str(v0).strip() if pd.notna(v0) else ""
                b = str(v1).strip() if pd.notna(v1) else ""
                # Prefer explicit sub-component in col B when present.
                return b if b else a

            for r in range(2, raw.shape[0]):
                comp_name = _mk_component_name(raw.iat[r, 0], raw.iat[r, 1] if raw.shape[1] > 1 else None)
                if not comp_name:
                    continue

                for c in range(2, raw.shape[1]):
                    product_name = str(product_row.iat[c]).strip() if pd.notna(product_row.iat[c]) else ""
                    machine_name = str(machine_row.iat[c]).strip() if pd.notna(machine_row.iat[c]) else ""
                    if not product_name:
                        continue

                    value = raw.iat[r, c]
                    if pd.isna(value):
                        continue
                    # Keep only numeric and strictly positive ratio cells.
                    try:
                        ratio = float(value)
                    except Exception:
                        continue
                    if ratio <= 0:
                        continue

                    product_code = f"{machine_name}::{product_name}" if machine_name else product_name
                    records.append(
                        {
                            "component_code": comp_name,
                            "product_code": product_code,
                        }
                    )

            if records:
                df_long = pd.DataFrame(records).drop_duplicates()
                return df_long, "product_code", "component_code"
        except Exception:
            continue

    raise ValueError(
        "Unable to detect ratios columns in any sheet (including matrix fallback). "
        f"Check candidates and file format. Last detail: {last_error}"
    )


def _read_articles(path: Path) -> tuple[pd.DataFrame, str, str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Articles file not found: {path}")

    sep = _detect_csv_sep(path)
    try:
        df = pd.read_csv(path, sep=sep, encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Unable to read articles CSV '{path}' with sep='{sep}': {exc}") from exc

    if df.empty:
        raise ValueError(f"Articles file is empty: {path}")

    code_col = _find_col_by_candidates(df.columns, ARTICLE_CODE_CANDIDATES)
    desc_col = _find_col_by_candidates(df.columns, ARTICLE_DESCRIPTION_CANDIDATES)
    cat_col = _find_col_by_candidates(df.columns, ARTICLE_CATEGORY_CANDIDATES)

    # Lightweight fallback if explicit names are not found.
    if code_col is None:
        code_col = _find_col_by_keywords(df.columns, ["item"]) or _find_col_by_keywords(df.columns, ["code"])
    if desc_col is None:
        desc_col = _find_col_by_keywords(df.columns, ["description"]) or _find_col_by_keywords(df.columns, ["libell"])
    if cat_col is None:
        cat_col = _find_col_by_keywords(df.columns, ["categorie"]) or _find_col_by_keywords(df.columns, ["category"])

    if not code_col or not desc_col or not cat_col:
        raise ValueError(
            "Unable to detect article columns. "
            f"Detected: code={code_col}, description={desc_col}, category={cat_col}. "
            "Please adjust ARTICLE_*_CANDIDATES lists."
        )

    return df, code_col, desc_col, cat_col


def _slug_label(value: str) -> str:
    s = re.sub(r"\s+", "_", str(value).strip().lower())
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return f"label_{s or 'unknown'}"


def build_recipe_dataset() -> pd.DataFrame:
    # 1) Read and aggregate recipes (component -> list of finished products)
    ratios_df, product_col, component_col = _read_ratios(RATIOS_PATH)
    ratios_df = ratios_df[[component_col, product_col]].copy()
    ratios_df[component_col] = ratios_df[component_col].fillna("").astype(str).str.strip()
    ratios_df[product_col] = ratios_df[product_col].fillna("").astype(str).str.strip()
    ratios_df = ratios_df[(ratios_df[component_col] != "") & (ratios_df[product_col] != "")]

    comp_to_products = (
        ratios_df.groupby(component_col)[product_col]
        .apply(lambda s: sorted(set(s.astype(str).tolist())))
        .reset_index(name="products")
    )

    # 2) Read articles and left merge
    articles_df, art_code_col, art_desc_col, art_cat_col = _read_articles(ARTICLES_PATH)

    # Robust against duplicated column names: select by first matching index, not by label only.
    code_idx = next(i for i, c in enumerate(articles_df.columns) if c == art_code_col)
    desc_idx = next(i for i, c in enumerate(articles_df.columns) if c == art_desc_col)
    cat_idx = next(i for i, c in enumerate(articles_df.columns) if c == art_cat_col)
    articles_selected = pd.DataFrame(
        {
            "article_code": articles_df.iloc[:, code_idx],
            "description": articles_df.iloc[:, desc_idx],
            "categorie": articles_df.iloc[:, cat_idx],
        }
    )
    articles_selected["article_code"] = articles_selected["article_code"].fillna("").astype(str).str.strip()

    merged = comp_to_products.merge(
        articles_selected,
        how="left",
        left_on=component_col,
        right_on="article_code",
    )

    # 3) Text feature engineering with strict context format
    merged["description"] = merged["description"].fillna("").astype(str)
    merged["categorie"] = merged["categorie"].fillna("").astype(str)
    # If article join is missing, keep component identifier as fallback text.
    merged.loc[merged["description"].str.strip() == "", "description"] = merged[component_col].astype(str)
    merged["texte"] = merged["description"] + " [CONTEXTE: " + merged["categorie"] + "]"
    merged["texte"] = merged["texte"].str.lower().str.replace(r"\s+", " ", regex=True).str.strip()

    # 4) Multi-label binarization
    mlb = MultiLabelBinarizer()
    y = mlb.fit_transform(merged["products"])
    label_cols = [_slug_label(c) for c in mlb.classes_]

    labels_df = pd.DataFrame(y, columns=label_cols, index=merged.index).astype(int)
    final_df = pd.concat([merged[["texte"]], labels_df], axis=1)

    # 5) Export and logs
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_csv(OUTPUT_PATH, index=False)

    print("=== recipe_train_multilabel.csv generated ===")
    print(f"Ratios file: {RATIOS_PATH}")
    print(f"Articles file: {ARTICLES_PATH}")
    print(f"Output file: {OUTPUT_PATH}")
    print(f"Detected ratios columns -> component: '{component_col}', product: '{product_col}'")
    print(
        "Detected articles columns -> "
        f"code: '{art_code_col}', description: '{art_desc_col}', category: '{art_cat_col}'"
    )
    print(f"Nombre total de MP uniques trouvées: {len(final_df)}")
    print(f"Taille du vocabulaire des produits finis: {len(mlb.classes_)}")
    print("\nAperçu dataset:")
    print(final_df.head())

    return final_df


def main() -> int:
    try:
        build_recipe_dataset()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] build_recipe_dataset failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
