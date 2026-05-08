from pathlib import Path
from typing import cast
import unicodedata

import pandas as pd


def _norm(value: object) -> str:
    """Normalise les textes : minuscules, sans espaces superflus, et SANS ACCENTS."""
    texte = str(value).strip().lower()
    # Suppression des accents (é devient e, à devient a)
    texte_sans_accent = ''.join(c for c in unicodedata.normalize('NFD', texte) if unicodedata.category(c) != 'Mn')
    return " ".join(texte_sans_accent.split())


def _read_table(path: Path) -> pd.DataFrame:
    """Read CSV/XLSX with basic fallbacks (separator + encoding)."""
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)

    errors: list[str] = []
    for enc in ("utf-8", "latin-1", "cp1252"):
        for sep in (",", ";"):
            try:
                return pd.read_csv(path, encoding=enc, sep=sep)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"encoding={enc}, sep={sep}: {exc}")
    raise RuntimeError(f"Impossible de lire {path}. Tentatives:\n" + "\n".join(errors))


def _read_ratios_matrix(path: Path) -> pd.DataFrame:
    """
    Parse RATIOS STANDARDS matrix layout into long format:
    id_article_erp, machine_cible, quantite_standard_kg
    """
    raw = cast(pd.DataFrame, pd.read_excel(path, header=None))
    if raw.empty or raw.shape[0] < 4 or raw.shape[1] < 3:
        raise ValueError("Format ratios inattendu: matrice vide ou trop petite.")

    machine_row = raw.iloc[0]
    product_row = raw.iloc[1]
    rows: list[dict[str, object]] = []

    def _component_name(v0: object, v1: object) -> str:
        a = str(v0).strip() if pd.notna(v0) else ""
        b = str(v1).strip() if pd.notna(v1) else ""
        return b if b else a

    for r in range(2, raw.shape[0]):
        component = _component_name(raw.iat[r, 0], raw.iat[r, 1] if raw.shape[1] > 1 else None)
        if not component:
            continue
        for c in range(2, raw.shape[1]):
            product = str(product_row.iat[c]).strip() if pd.notna(product_row.iat[c]) else ""
            machine = str(machine_row.iat[c]).strip() if pd.notna(machine_row.iat[c]) else ""
            if not product:
                continue

            val = raw.iat[r, c]
            if pd.isna(val):
                continue
            try:
                qte = float(val)
            except Exception:
                continue
            if qte <= 0:
                continue

            machine_cible = f"{machine}::{product}" if machine else product
            rows.append(
                {
                    "id_article_erp": _norm(component),
                    "machine_cible": _norm(machine_cible),
                    "quantite_standard_kg": qte,
                }
            )

    if not rows:
        raise ValueError("Aucune donnée de ratio valide détectée dans la matrice.")
    return pd.DataFrame(rows).drop_duplicates()


def _read_historique_multilabel(path: Path) -> pd.DataFrame:
    """
    Convert recipe_train_multilabel_1000.csv into long format:
    id_article_erp, machine_cible, occurences
    """
    df = cast(pd.DataFrame, _read_table(path))
    if "texte" not in df.columns:
        raise KeyError(f"Colonne 'texte' introuvable. Colonnes: {list(df.columns)}")

    label_cols = [c for c in df.columns if str(c).startswith("label_")]
    if not label_cols:
        raise KeyError(f"Aucune colonne label_* détectée. Colonnes: {list(df.columns)}")

    base_txt = (
        df["texte"]
        .fillna("")
        .astype(str)
        .str.split("[contexte:", n=1, expand=True, regex=False)[0]
        .str.strip()
        .map(_norm)
    )

    rows: list[dict[str, object]] = []
    for idx, article in base_txt.items():
        if not article:
            continue
        for lbl in label_cols:
            val = df.at[idx, lbl]
            try:
                active = int(val) == 1
            except Exception:
                active = False
            if active:
                rows.append(
                    {
                        "id_article_erp": article,
                        "machine_cible": _norm(lbl),
                        "occurences": 1,
                    }
                )

    if not rows:
        raise ValueError("Historique multi-label vide après conversion.")
    return pd.DataFrame(rows)


def generer_base_formules() -> None:
    root = Path(__file__).resolve().parents[3]
    chemin_ratios = root / "data_sources" / "Data_Produc_Qual" / "RATIOS STANDARDS.csv.xlsx"
    chemin_historique = root / "agent_pdr_microservice" / "data" / "recipe_train_multilabel_1000.csv"
    chemin_sortie = Path(__file__).resolve().parent / "formuleexacte.csv"

    print("Lecture des fichiers en cours...")

    df_ratios = cast(pd.DataFrame, _read_ratios_matrix(chemin_ratios))
    df_historique = cast(pd.DataFrame, _read_historique_multilabel(chemin_historique))

    col_article_id = "id_article_erp"
    col_machine = "machine_cible"
    col_ratio = "quantite_standard_kg"

    # DICTIONNAIRE CORRIGÉ AVEC LES UNDERSCORES DE L'HISTORIQUE
    mapping_machines = {
        "label_pm3_fluting": "pm3::fluting",
        "label_fluting": "pm3::fluting",
        "label_pm2_kraft_export": "pm2::kraft export",
        "label_sotikraft": "sotikraft",
        "label_pm2_kraft": "pm2::kraft",
        "label_testliner": "pm2::testliner",
        "label_test_color": "pm2::test color"
    }
    df_historique[col_machine] = df_historique[col_machine].replace(mapping_machines)

    df_frequence = cast(
        pd.DataFrame,
        df_historique.groupby([col_article_id, col_machine], as_index=False)["occurences"].sum(),
    )
    total_par_article = df_frequence.groupby(col_article_id)["occurences"].transform("sum")
    df_frequence["probabilite_historique"] = (df_frequence["occurences"] / total_par_article).round(4)

    # =========================================================
    # 🚨 RADAR N°2 : DIAGNOSTIC DES MACHINES 🚨
    # =========================================================
    machines_historique = set(df_frequence[col_machine].unique())
    machines_ratios = set(df_ratios[col_machine].unique())
    machines_en_commun = machines_historique.intersection(machines_ratios)
    
    print("\n" + "="*50)
    print("🚨 CE QUE L'EXCEL A RÉELLEMENT COMPRIS 🚨")
    print(df_ratios[[col_article_id, col_machine, col_ratio]].head(5))
    
    print("\n--- MACHINES DANS L'HISTORIQUE ---")
    print(machines_historique)
    
    print("\n--- MACHINES DANS L'EXCEL RATIOS ---")
    print(machines_ratios)
    
    print(f"\n✅ MACHINES EN COMMUN : {len(machines_en_commun)}")
    print("="*50 + "\n")
    # =========================================================

    df_formule_finale = cast(
        pd.DataFrame,
        pd.merge(
            df_frequence,
            df_ratios[[col_article_id, col_machine, col_ratio]],
            on=[col_article_id, col_machine],
            how="left",
        ),
    )

    df_formule_finale[col_ratio] = df_formule_finale[col_ratio].fillna(0.0)
    df_formule_finale["score_final"] = (
        0.7 * df_formule_finale["probabilite_historique"] + 0.3 * df_formule_finale[col_ratio]
    ).round(4)
    df_formule_finale = df_formule_finale.sort_values(
        by=[col_article_id, "probabilite_historique"], ascending=[True, False]
    )

    df_formule_finale.to_csv(chemin_sortie, index=False, encoding="utf-8")
    
    print(f"✅ Fichier généré avec succès : {chemin_sortie}")
    lignes_avec_ratio = len(df_formule_finale[df_formule_finale[col_ratio] > 0])
    print(f"🎯 Lignes où un vrai ratio a été trouvé : {lignes_avec_ratio} sur {len(df_formule_finale)}\n")

if __name__ == "__main__":
    generer_base_formules()