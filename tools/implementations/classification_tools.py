from __future__ import annotations

from harness_backend.config.settings import SETTINGS
from harness_backend.tools.adapters.legacy_tools_api import classify_mp_chimie, classify_pdr_mp


def run_material_classification(query: str) -> dict:
    remote_mp_chimie = classify_mp_chimie(query)
    remote_pdr_mp = classify_pdr_mp(id_article="", description=query, categorie="")
    if remote_mp_chimie.get("ok") and remote_pdr_mp.get("ok"):
        pdr_or_mp = str(remote_pdr_mp.get("level1", "MP"))
        if pdr_or_mp == "PDR":
            label = "PDR"
            model_used = SETTINGS.classifier_primary_model
        else:
            label = str(remote_mp_chimie.get("level1", "MP"))
            model_used = (
                SETTINGS.classifier_primary_model if label == "MP" else SETTINGS.classifier_secondary_model
            )
        return {
            "label": label,
            "model_used": model_used,
            "source": "legacy_api_bridge",
            "explanation": "Result from legacy classification microservices via adapter.",
        }

    text = (query or "").lower()
    if any(k in text for k in ("acide", "soude", "amidon", "asa", "ppo", "pac", "biocide")):
        label = "CHIMIE"
        model_used = SETTINGS.classifier_secondary_model
    elif any(k in text for k in ("roulement", "courroie", "vis", "joint", "moteur", "pompe")):
        label = "PDR"
        model_used = SETTINGS.classifier_primary_model
    else:
        label = "MP"
        model_used = SETTINGS.classifier_primary_model
    return {
        "label": label,
        "model_used": model_used,
        "source": "local_fallback",
        "explanation": "Classification inferred by industrial lexical patterns.",
    }

