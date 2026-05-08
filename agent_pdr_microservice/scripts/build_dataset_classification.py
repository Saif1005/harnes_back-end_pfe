#!/usr/bin/env python3
"""
Construit ``data/dataset_classification.csv`` (colonnes: texte, label) à partir de
``correlation_qualite_ingredients_recette.csv``.

Labels : MP (matière première fibreuse) | CHIMIE (additifs / produits chimiques).

- Extraction des ingrédients uniques + **variantes contextuelles** (famille article, recette).
- **Phrases de référence** alignées sur ``formule_recette.md`` (Sotipapier : carton, Kraft, TestLiner).
- **Augmentation** par préfixes / suffixes typiques ERP-papier (sans API externe).
- **Équilibrage** des classes jusqu'à un minimum cible (oversampling contrôlé de la minorité).
"""
from __future__ import annotations

import argparse
import csv
import random
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CORR_CSV = DATA_DIR / "correlation_qualite_ingredients_recette.csv"
OUT_CSV = DATA_DIR / "dataset_classification.csv"

# --- Règles de labellisation (inchangées, cohérentes avec l'historique CSV) ---

_CHIMIE_FRAGMENTS = (
    "starch",
    "amidon",
    "biocide",
    "defoamer",
    "antimousse",
    "afranil",
    "erol",
    "retention",
    "rétention",
    "krofta",
    "polymer",
    "polymère",
    "sizing",
    "ppo",
    "asa",
    "collage",
    "pac ",
    "pac,",
    "pac)",
    " coagulant",
    "dye",
    "colorant",
    "oxidized",
    "oxydé",
    "cationic",
    "cationique",
    "prestige",
    "cleaning aids",
    "nettoyage",
    "size press",
    "wet end",
)

_MP_FRAGMENTS = (
    "pulp",
    "pâte",
    "flocon",
    "waste paper",
    "fiber ratio",
    "fibre ratio",
    "ratio fibre",
    "standard pulp",
    "fiber/waste",
    "pulp ratio",
)

# Phrases **document métier** (formule_recette.md / lignes Sotipapier) — uniquement CHIMIE
_CURATED_CHIMIE_TEXTS = (
    "Amidon cationique — masse humide",
    "Amidon oxydé traitement surface (size press)",
    "Agent de collage ASA Kraft pour sacs",
    "Sizing PPO collage humide TestLiner",
    "PAC coagulant tour de formation",
    "Colorant masse humide (dye wet end)",
    "Antimousse Afranil rupture mousse",
    "Antimousse Erol ligne carton",
    "Agent de rétention fines et charges",
    "Polymère clarification flottation Krofta",
    "Biocide contrôle slime machine papier",
    "Prestige nettoyage filtre / circuit",
    "Dosage biocide Cannelure Fluting",
    "Rétention aids ratio ligne production",
    "Starch oxidized ratio surface sèche",
    "Starch cationic ratio masse",
    "Dye ratio wet end TestLiner coloré",
    "Coagulant PAC fixation charges anioniques",
    "Agent hydrophobe ASA sizing",
    "Collage PPO imperméabilité TestLiner",
)

# Phrases métier — uniquement MP (fibres / déchets / ratios fibre)
_CURATED_MP_TEXTS = (
    "Fiber ratio — Cannelure Fluting",
    "Ratio fibre déchets papier",
    "Waste paper ratio masse",
    "Standard pulp fibre vierge",
    "Flocon pulp apport résistance",
    "Pulp ratio Kraft pour sacs",
    "Fiber ratio global 1.1",
    "Matière première fibreuse ligne carton",
    "Apport pâte standard et flocon",
    "Mélange waste paper et pulp",
    "Ratio fibre / déchets papier process",
)

# Préfixes / suffixes **plausibles** sur une ligne papier (ERP, kg/t, machine)
_PREFIXES = (
    "",
    "Dosage ",
    "Ingrédient : ",
    "Réf. recette — ",
    "ERP — ",
    "Ajout masse ",
    "Consommation ",
)

_SUFFIXES = (
    "",
    " ratio",
    " Ratio",
    " (kg/t)",
    " kg/t papier",
    " — ligne papier",
    " wet end",
    " tour formation",
    " machine PM",
)

# Quelques reformulations EN/FR **sûres** (même classe que le texte d'origine)
_CHIMIE_ALIASES: tuple[tuple[str, str], ...] = (
    ("starch cationic", "amidon cationique"),
    ("starch oxidized", "amidon oxydé"),
    ("retention aids", "agent de rétention"),
    ("defoamer", "antimousse"),
)

_MP_ALIASES: tuple[tuple[str, str], ...] = (
    ("waste paper", "déchets de papier"),
    ("waste paper", "papier de récupération"),
    ("standard pulp", "pâte standard"),
    ("flocon pulp", "pâte flocon"),
    ("fiber ratio", "ratio fibre"),
    ("pulp ratio", "ratio pâte"),
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def label_ingredient(ingredient: str) -> str:
    low = _norm(ingredient)
    if not low:
        return "CHIMIE"
    if any(f in low for f in _CHIMIE_FRAGMENTS):
        return "CHIMIE"
    if any(m in low for m in _MP_FRAGMENTS):
        return "MP"
    return "CHIMIE"


def _dedup_key(texte: str) -> str:
    return _norm(texte)


def _template_variants(texte: str) -> list[str]:
    """Combinaisons préfixe + suffixe (texte brut industriel)."""
    t = (texte or "").strip()
    if not t:
        return []
    out: list[str] = []
    for p in _PREFIXES:
        for s in _SUFFIXES:
            v = f"{p}{t}{s}".strip()
            if v:
                out.append(v)
    return out


def _alias_variants(texte: str, label: str) -> list[str]:
    """Une passe de remplacement FR/EN selon le label (évite de toucher aux CHIMIE avec règles MP)."""
    low = texte
    variants: list[str] = [texte]
    pairs = _MP_ALIASES if label == "MP" else _CHIMIE_ALIASES
    for a, b in pairs:
        la, lb = a.lower(), b.lower()
        if la in low.lower():
            variants.append(re.sub(re.escape(a), b, texte, flags=re.IGNORECASE))
        if lb in low.lower():
            variants.append(re.sub(re.escape(b), a, texte, flags=re.IGNORECASE))
    return variants


def _expand_text(texte: str, label: str) -> list[str]:
    """Augmentation locale : alias + gabarits ERP."""
    bucket: list[str] = []
    for alias_v in _alias_variants(texte, label):
        bucket.extend(_template_variants(alias_v))
    return bucket


def _balance_class(
    rows_by_key: dict[str, tuple[str, str]],
    label: str,
    target: int,
    seed_phrases: list[str],
    rng: random.Random,
) -> None:
    """Ajoute des lignes synthétiques pour la classe ``label`` jusqu'à ``target`` exemplaires uniques."""
    count = sum(1 for _k, (_t, lab) in rows_by_key.items() if lab == label)
    if count >= target:
        return
    need = target - count
    attempts = 0
    max_attempts = need * 80
    idx = 0
    bases = list(seed_phrases)
    rng.shuffle(bases)
    while need > 0 and attempts < max_attempts:
        attempts += 1
        base = bases[idx % len(bases)]
        idx += 1
        # Légère jitter : parfois double préfixe ou variante titre
        noise = attempts % 7
        jittered = base
        if noise == 1:
            jittered = base.title()
        elif noise == 2:
            jittered = f"{base} — Sotipapier"
        elif noise == 3:
            jittered = f"Article carton : {base}"
        elif noise == 4 and label == "CHIMIE":
            jittered = f"Additif process : {base}"
        elif noise == 5 and label == "MP":
            jittered = f"Fibre / charge : {base}"

        for v in _expand_text(jittered, label):
            key = _dedup_key(v)
            if key not in rows_by_key:
                rows_by_key[key] = (v, label)
                need -= 1
                if need <= 0:
                    return


def _load_corr(args: argparse.Namespace) -> tuple[set[str], set[tuple[str, str, str]]]:
    """Ingrédients uniques + triplets (ingrédient, family_pf, recipe_key) pour le contexte."""
    ingredients: set[str] = set()
    triples: set[tuple[str, str, str]] = set()
    with args.corr.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        if "ingredient" not in fields:
            raise ValueError("Colonne 'ingredient' absente du CSV.")
        has_family = "family_pf" in fields
        has_recipe = "recipe_key" in fields
        for row in reader:
            ing = (row.get("ingredient") or "").strip()
            if not ing:
                continue
            ingredients.add(ing)
            fam = (row.get("family_pf") or "").strip() if has_family else ""
            rk = (row.get("recipe_key") or "").strip() if has_recipe else ""
            if fam or rk:
                triples.add((ing, fam, rk))
    return ingredients, triples


def _context_variants(ingredient: str, fam: str, rk: str) -> list[str]:
    """Formulations type libellé ERP + ligne produit (données réelles, pas inventées)."""
    lab = label_ingredient(ingredient)
    if lab not in {"MP", "CHIMIE"}:
        return []
    out: list[str] = []
    parts = [p for p in (fam, rk) if p]
    if not parts:
        return []
    ctx = " / ".join(parts)
    out.append(f"{ingredient} — {ctx}")
    out.append(f"{ctx} : {ingredient}")
    out.append(f"{ingredient} ({ctx})")
    if fam:
        out.append(f"[{fam}] {ingredient}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère dataset_classification.csv avec augmentation.")
    parser.add_argument("--corr", type=Path, default=CORR_CSV)
    parser.add_argument("--out", type=Path, default=OUT_CSV)
    parser.add_argument(
        "--min-per-class",
        type=int,
        default=200,
        help="Nombre minimum d'exemplaires uniques par classe après équilibrage (défaut: 200).",
    )
    parser.add_argument(
        "--no-balance",
        action="store_true",
        help="Ne pas forcer l'équilibre MP/CHIMIE (garde seulement graines + expansions).",
    )
    parser.add_argument(
        "--no-augment",
        action="store_true",
        help="Une ligne par ingrédient unique uniquement (comportement minimal).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Graine pour l'oversampling de la minorité.")
    args = parser.parse_args()

    if not args.corr.exists():
        raise FileNotFoundError(f"Fichier introuvable: {args.corr}")

    ingredients, triples = _load_corr(args)
    rng = random.Random(args.seed)

    # (clé normalisée) -> (texte affiché, label)
    rows_by_key: dict[str, tuple[str, str]] = {}

    def add_row(texte: str, label: str) -> None:
        texte = (texte or "").strip()
        if not texte:
            return
        key = _dedup_key(texte)
        if key not in rows_by_key:
            rows_by_key[key] = (texte, label)

    # 1) Graines : ingrédient brut
    for ing in sorted(ingredients):
        lab = label_ingredient(ing)
        add_row(ing, lab)

    seed_mp = [ing for ing in sorted(ingredients) if label_ingredient(ing) == "MP"]
    seed_ch = [ing for ing in sorted(ingredients) if label_ingredient(ing) == "CHIMIE"]

    if not args.no_augment:
        # 2) Contexte production (colonnes CSV)
        for ing, fam, rk in triples:
            lab = label_ingredient(ing)
            for v in _context_variants(ing, fam, rk):
                add_row(v, lab)

        # 3) Courbe métier documentée
        for t in _CURATED_MP_TEXTS:
            add_row(t, "MP")
        for t in _CURATED_CHIMIE_TEXTS:
            add_row(t, "CHIMIE")

        # 4) Gabarits sur chaque graine + curated
        for ing in seed_mp:
            for v in _expand_text(ing, "MP"):
                add_row(v, "MP")
        for ing in seed_ch:
            for v in _expand_text(ing, "CHIMIE"):
                add_row(v, "CHIMIE")
        for t in _CURATED_MP_TEXTS:
            for v in _expand_text(t, "MP"):
                add_row(v, "MP")
        for t in _CURATED_CHIMIE_TEXTS:
            for v in _expand_text(t, "CHIMIE"):
                add_row(v, "CHIMIE")

    if not args.no_balance and not args.no_augment:
        mp_seeds = seed_mp + list(_CURATED_MP_TEXTS)
        ch_seeds = seed_ch + list(_CURATED_CHIMIE_TEXTS)
        mp_c = sum(1 for _k, (_t, lab) in rows_by_key.items() if lab == "MP")
        ch_c = sum(1 for _k, (_t, lab) in rows_by_key.items() if lab == "CHIMIE")
        # Équilibre : même cardinal que la classe majoritaire (ou min-per-class si plus grand)
        target_final = max(mp_c, ch_c, args.min_per_class)
        _balance_class(rows_by_key, "MP", target_final, mp_seeds, rng)
        _balance_class(rows_by_key, "CHIMIE", target_final, ch_seeds, rng)

    final_rows = sorted(rows_by_key.values(), key=lambda x: (x[1], x[0].lower()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["texte", "label"])
        w.writeheader()
        for texte, label in final_rows:
            w.writerow({"texte": texte, "label": label})

    mp = sum(1 for _t, lab in final_rows if lab == "MP")
    ch = sum(1 for _t, lab in final_rows if lab == "CHIMIE")
    print(
        f"Écrit: {args.out} ({len(final_rows)} lignes) — MP={mp} CHIMIE={ch} "
        f"(min_per_class={args.min_per_class}, augment={not args.no_augment}, balance={not args.no_balance})"
    )


if __name__ == "__main__":
    main()
