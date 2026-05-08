from __future__ import annotations

import csv
from collections import defaultdict

from harness_backend.config.settings import SETTINGS
from harness_backend.services.stock_runtime import get_prediction_series
try:
    from sklearn.linear_model import Ridge  # type: ignore
except Exception:  # noqa: BLE001
    Ridge = None


def run_prediction_regression(query: str) -> dict:
    runtime_series = get_prediction_series(limit=400)
    if any(runtime_series.values()):
        series_by_label = runtime_series
    else:
        series_by_label: dict[str, list[float]] = defaultdict(list)
        try:
            with open(SETTINGS.dataset_classification_path, "r", encoding="utf-8", errors="ignore") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    qty = abs(float(row.get("quantity_kg", 0.0) or 0.0))
                    text = str(row.get("texte", "")).lower()
                    if any(k in text for k in ("acide", "soude", "amidon", "asa", "pac", "ppo", "biocide")):
                        label = "CHIMIE"
                    elif any(k in text for k in ("roulement", "courroie", "vis", "joint", "moteur", "pompe")):
                        label = "PDR"
                    else:
                        label = "MP"
                    series_by_label[label].append(qty)
        except FileNotFoundError:
            return {
                "forecast_next_kg": {},
                "diagnostics": {},
                "model_used": "unavailable",
                "query": query,
                "error": f"dataset_not_found: {SETTINGS.dataset_classification_path}",
            }

    forecast: dict[str, float] = {}
    diagnostics: dict[str, dict] = {}
    for label, values in series_by_label.items():
        if len(values) < 4:
            forecast[label] = round(sum(values), 3)
            diagnostics[label] = {"training_status": "collecting", "points": len(values)}
            continue
        if Ridge is not None:
            x = [[i] for i in range(len(values))]
            y = values
            model = Ridge(alpha=1.0)
            model.fit(x, y)
            next_idx = [[len(values)]]
            pred = float(model.predict(next_idx)[0])
            algo = "ridge-regression"
        else:
            delta = values[-1] - values[-2]
            pred = values[-1] + delta
            algo = "linear-fallback"
        forecast[label] = round(max(pred, 0.0), 3)
        diagnostics[label] = {
            "training_status": "trained",
            "points": len(values),
            "alpha": 1.0 if Ridge is not None else 0.0,
            "algorithm": algo,
        }

    algo = SETTINGS.prediction_model_name if Ridge is not None else "linear-fallback"
    return {
        "forecast_next_kg": forecast,
        "diagnostics": diagnostics,
        "model_used": algo,
        "query": query,
    }

