from __future__ import annotations

import csv

from harness_backend.config.settings import SETTINGS
from harness_backend.services.legacy_compat import normalize_key


def run_stock_check(query: str) -> dict:
    totals = {"MP": 0.0, "CHIMIE": 0.0, "PDR": 0.0}
    inventory_by_item: dict[str, float] = {}
    labels_by_item: dict[str, str] = {}
    with open(SETTINGS.dataset_classification_path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            qty = float(row.get("quantity_kg", 0.0) or 0.0)
            raw_text = str(row.get("texte", "")).strip()
            text = raw_text.lower()
            key = normalize_key(raw_text)
            if key:
                inventory_by_item[key] = float(inventory_by_item.get(key, 0.0) + abs(qty))
            if any(k in text for k in ("acide", "soude", "amidon", "asa", "pac", "ppo", "biocide")):
                totals["CHIMIE"] += abs(qty)
                if key:
                    labels_by_item[key] = "CHIMIE"
            elif any(k in text for k in ("roulement", "courroie", "vis", "joint", "moteur", "pompe")):
                totals["PDR"] += abs(qty)
                if key:
                    labels_by_item[key] = "PDR"
            else:
                totals["MP"] += abs(qty)
                if key:
                    labels_by_item[key] = "MP"

    return {
        "totals_kg": {k: round(v, 3) for k, v in totals.items()},
        "inventory_map": {k: round(v, 3) for k, v in inventory_by_item.items()},
        "inventory_labels": labels_by_item,
        "source": "dataset_classification_compatible.csv",
        "query": query,
    }

