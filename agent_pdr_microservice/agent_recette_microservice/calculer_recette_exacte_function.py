from __future__ import annotations
import re
import unicodedata
from typing import Dict, List, Tuple, Optional
from langchain_core.tools import tool

# ------------------------------------------------------------------------
# MATRICE DES RECETTES EXACTES (Extraite de formule_recette.md)
# ------------------------------------------------------------------------
RECETTES_DB: Dict[str, Dict[str, float]] = {
    "waste paper ratio": {"Cannelure (Fluting)": 1.204, "Kraft pour sacs": 0.28, "TestLiner": 1.204, "TestLiner Coloré": 1.204},
    "fiber ratio": {"Kraft pour sacs": 1.1, "Cannelure (Fluting)": 1.204, "TestLiner": 1.204, "TestLiner Coloré": 1.204},
    "standard pulp": {"Kraft pour sacs": 0.5494},
    "flocon pulp": {"Kraft pour sacs": 0.2706},
    "amidon cationique": {"Cannelure (Fluting)": 33.0, "Kraft pour sacs": 26.0, "TestLiner": 33.0, "TestLiner Coloré": 33.0},
    "amidon oxyde": {"Cannelure (Fluting)": 50.0},
    "size press": {"TestLiner Coloré": 14.0},
    "agent de collage asa": {"Kraft pour sacs": 3.2},
    "sizing ppo": {"TestLiner": 3.5, "TestLiner Coloré": 3.5},
    "pac": {"TestLiner": 3.5, "TestLiner Coloré": 3.5},
    "dye": {"TestLiner Coloré": 5.5},
    "antimousse afranil": {"Cannelure (Fluting)": 0.5, "Kraft pour sacs": 1.5, "TestLiner": 0.5, "TestLiner Coloré": 0.5},
    "defoamer erol": {"Cannelure (Fluting)": 1.5, "TestLiner": 1.5, "TestLiner Coloré": 1.5},
    "agent de retention": {"Cannelure (Fluting)": 0.37, "Kraft pour sacs": 0.27, "TestLiner": 0.37, "TestLiner Coloré": 0.37},
    "polymere krofta": {"Cannelure (Fluting)": 0.37, "Kraft pour sacs": 0.25, "TestLiner": 0.37, "TestLiner Coloré": 0.37},
    "prestige": {"Cannelure (Fluting)": 0.5, "Kraft pour sacs": 0.4},
    "biocide": {"Cannelure (Fluting)": 0.15, "Kraft pour sacs": 0.15, "TestLiner": 0.15, "TestLiner Coloré": 0.15}
}

PROBA_MACHINE = {
    "Cannelure (Fluting)": [("0102MPM3", 60.0), ("0102MPM2", 40.0)],
    "Kraft pour sacs": [("0102MPM2", 95.0), ("0102MPM3", 5.0)],
    "TestLiner": [("0102MPM3", 85.0), ("0102MPM2", 15.0)],
    "TestLiner Coloré": [("0102MPM3", 100.0)]
}

# Matières de base exprimées en tonnes (t/t), pas en kg/t.
BASE_MATERIALS_TONNES = {
    "waste paper ratio",
    "fiber ratio",
    "standard pulp",
    "flocon pulp",
}

def _normalize_text(value: str) -> str:
    s = " ".join((value or "").strip().lower().split())
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def _parse_query(query: str) -> Tuple[str, Optional[float]]:
    raw = (query or "").strip()
    if not raw:
        return "", None

    tonnage = None
    m = re.search(r"tonnage\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?)", raw, flags=re.IGNORECASE)
    if m:
        tonnage = float(m.group(1).replace(",", "."))
        raw = re.sub(r"tonnage\s*[:=]\s*[0-9]+(?:[.,][0-9]+)?", "", raw, flags=re.IGNORECASE).strip(" ;,")

    if raw.lower().startswith("article="):
        raw = raw.split("=", 1)[1].strip()
    if raw.lower().startswith("article:"):
        raw = raw.split(":", 1)[1].strip()

    return raw, tonnage

def _find_best_match(article_norm: str) -> Optional[str]:
    for key in RECETTES_DB.keys():
        kn = _normalize_text(key)
        if kn in article_norm or article_norm in kn:
            return key
    return None

def _familles_uniques() -> List[str]:
    seen: List[str] = []
    for ratios in RECETTES_DB.values():
        for f in ratios:
            if f not in seen:
                seen.append(f)
    return seen

def _find_famille_match(article_norm: str) -> Optional[str]:
    for famille in sorted(_familles_uniques(), key=len, reverse=True):
        fn = _normalize_text(famille)
        if not fn:
            continue
        if fn == article_norm or fn in article_norm or article_norm in fn:
            return famille
    return None

def _is_base_material_tonnes(ingredient_key: str) -> bool:
    return _normalize_text(ingredient_key) in BASE_MATERIALS_TONNES

def _lines_for_ingredient(article_label: str, db_key: str, tonnage: Optional[float]) -> List[str]:
    applications = RECETTES_DB[db_key]
    lines: List[str] = [f"Spécifications pour l'ingrédient '{db_key}' :\n"]
    for famille, ratio in applications.items():
        machines = PROBA_MACHINE.get(famille, [("Machine Inconnue", 100.0)])
        machines_str = " ou ".join([f"{m} ({p}%)" for m, p in machines])
        
        if tonnage is not None:
            qte = float(tonnage) * ratio
            if _is_base_material_tonnes(db_key):
                lines.append(f"- Pour {tonnage} tonnes de {famille} : {qte:.3f} tonnes (Machines : {machines_str})")
            else:
                lines.append(f"- Pour {tonnage} tonnes de {famille} : {qte:.3f} kg (Machines : {machines_str})")
        else:
            if _is_base_material_tonnes(db_key):
                lines.append(f"- Pour {famille} : {ratio:.3f} t/t (Machines : {machines_str})")
            else:
                lines.append(f"- Pour {famille} : {ratio:.3f} kg/t (Machines : {machines_str})")
    return lines

def _lines_for_famille(famille: str, tonnage: Optional[float]) -> List[str]:
    """C'est ici qu'on applique le formatage exact demandé par l'utilisateur."""
    lines: List[str] = []
    
    # 1. Phrase d'introduction
    if tonnage is not None:
        lines.append(f"Cette commande de {tonnage} tonnes de {famille} nécessite :\n")
    else:
        lines.append(f"La recette standard pour 1 tonne de {famille} nécessite :\n")
    
    # 2. Liste numérotée des ingrédients sans doublons
    # Évite les redondances de formulation :
    # - "fiber ratio" + "waste paper ratio" (global + détail)
    # - "pulp ratio" + "standard/flocon pulp" (global + détail)
    has_waste = bool(RECETTES_DB.get("waste paper ratio", {}).get(famille))
    has_standard_pulp = bool(RECETTES_DB.get("standard pulp", {}).get(famille))
    has_flocon_pulp = bool(RECETTES_DB.get("flocon pulp", {}).get(famille))
    idx = 1
    for ing_key, ratios in RECETTES_DB.items():
        if famille in ratios:
            ing_norm = _normalize_text(ing_key)
            if ing_norm == "fiber ratio" and has_waste:
                continue
            if ing_norm == "pulp ratio" and (has_standard_pulp or has_flocon_pulp):
                continue
            ratio = ratios[famille]
            if tonnage is not None:
                qte_totale = float(tonnage) * ratio
                if _is_base_material_tonnes(ing_key):
                    lines.append(f"{idx} - {ing_key} : {qte_totale:.3f} tonnes")
                else:
                    lines.append(f"{idx} - {ing_key} : {qte_totale:.3f} kg")
            else:
                if _is_base_material_tonnes(ing_key):
                    lines.append(f"{idx} - {ing_key} : {ratio:.3f} t/t")
                else:
                    lines.append(f"{idx} - {ing_key} : {ratio:.3f} kg/t")
            idx += 1
            
    # 3. Phrase de conclusion sur les machines
    lines.append("\nFinalement : ")
    machines = PROBA_MACHINE.get(famille, [("Machine Inconnue", 100.0)])
    machines_str = " ou ".join([f"la machine {m} ({p}%)" for m, p in machines])
    lines[-1] += f"cette commande va s'effectuer sur {machines_str}."
    
    return lines

@tool(return_direct=True)
def calculer_recette_exacte(query: str) -> str:
    """Retourne la recette exacte et calcule les tonnages d'additifs chimiques ou matières premières."""

    article, tonnage = _parse_query(query)
    article_norm = _normalize_text(article)

    if not article_norm:
        return "Erreur d'exécution : Veuillez fournir un identifiant d'article ou d'ingrédient."

    famille = _find_famille_match(article_norm)
    if famille:
        return "\n".join(_lines_for_famille(famille, tonnage))
        
    db_key = _find_best_match(article_norm)
    if db_key:
        return "\n".join(_lines_for_ingredient(article, db_key, tonnage))

    return (
        f"Échec de l'extraction : L'article '{article}' ne correspond à aucun ratio défini "
        "dans la fiche technique industrielle."
    )