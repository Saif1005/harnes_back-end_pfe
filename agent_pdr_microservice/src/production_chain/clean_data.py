from pathlib import Path
import pandas as pd
import re

BASE_DIR = Path(__file__).resolve().parents[2]  # .../agent_pdr_microservice
INPUT_CSV = BASE_DIR / "data" / "dataset_niveau1_mp_vs_pdr (1).csv"
OUTPUT_CSV = BASE_DIR / "data" / "dataset_niveau1_mp_vs_pdr_clean.csv"

df = pd.read_csv(INPUT_CSV)

def clean_text(text):
    if isinstance(text, str):
        return re.sub(r"\s*\[contexte:.*?\]\s*", "", text, flags=re.IGNORECASE).strip()
    return text

df["texte"] = df["texte"].apply(clean_text)
df.to_csv(OUTPUT_CSV, index=False)
print(f"Nettoyage terminé: {OUTPUT_CSV}")