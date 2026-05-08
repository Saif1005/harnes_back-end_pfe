from __future__ import annotations

from harness_backend.config.settings import SETTINGS
from harness_backend.services.classification_checkpoint import predict_with_checkpoint
from harness_backend.tools.adapters.legacy_tools_api import classify_mp_chimie, classify_pdr_mp


def _apply_business_overrides(query: str, label: str) -> str:
    text = (query or "").lower()
    # Fuel / machine operation consumables should not be treated as production MP.
    if any(
        k in text
        for k in (
            "gazoil",
            "gazole",
            "diesel",
            "huile hydraulique",
            "huile moteur",
            "lubrifiant",
            "graisse",
            "carburant",
        )
    ):
        return "PDR"
    return label


def run_material_classification(query: str) -> dict:
    checkpoint = predict_with_checkpoint(query)
    if checkpoint is not None:
        checkpoint["label"] = _apply_business_overrides(query, str(checkpoint.get("label", "MP")).upper())
        return checkpoint

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
        label = _apply_business_overrides(query, str(label).upper())
        return {
            "label": label,
            "model_used": model_used,
            "source": "legacy_api_bridge",
            "explanation": "Result from legacy classification microservices via adapter.",
        }

    text = (query or "").lower()
    if any(k in text for k in ("acide", "soude", "amidon", "asa", "ppo", "pac", "biocide")):
        label = "CHIMIE"
    elif any(k in text for k in ("roulement", "courroie", "vis", "joint", "moteur", "pompe")):
        label = "PDR"
    else:
        label = "MP"
    label = _apply_business_overrides(query, label)
    return {
        "label": label,
        "model_used": SETTINGS.classification_model_name,
        "source": "local_fallback",
        "explanation": "Classification inferred by industrial lexical patterns.",
    }

