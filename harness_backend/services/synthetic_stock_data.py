from __future__ import annotations

import csv
import random
from pathlib import Path


MP_ITEMS = [
    "Kraft pour sacs",
    "Vieux papier brun",
    "Pate cellulose standard",
    "Fluting base reel",
    "Bobine papier brut",
]

CHIMIE_ITEMS = [
    "Acide sulfurique process",
    "Amidon cationique",
    "Biocide ligne machine",
    "Soude caustique",
    "ASA agent collage",
]

PDR_ITEMS = [
    "Roulement inox 6204",
    "Pompe process centrifuge",
    "Courroie transmission A-42",
    "Joint torique NBR",
    "Vis M12 acier",
]


def generate_synthetic_import_csv(path: str, rows: int = 1000, seed: int = 42) -> dict:
    rng = random.Random(seed)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    labels = ["MP", "CHIMIE", "PDR"]
    counts = {"MP": 0, "CHIMIE": 0, "PDR": 0}

    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["texte", "label", "quantity_kg"])
        writer.writeheader()
        for _ in range(max(1, int(rows))):
            label = rng.choice(labels)
            counts[label] += 1
            if label == "MP":
                text = rng.choice(MP_ITEMS)
                qty = round(rng.uniform(100, 5000), 3)
            elif label == "CHIMIE":
                text = rng.choice(CHIMIE_ITEMS)
                qty = round(rng.uniform(5, 600), 3)
            else:
                text = rng.choice(PDR_ITEMS)
                qty = round(rng.uniform(1, 250), 3)
            writer.writerow({"texte": text, "label": label, "quantity_kg": qty})

    return {"path": str(target), "rows": int(rows), "label_counts": counts, "seed": seed}

