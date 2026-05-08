"""Configuration centralisée via variables d'environnement."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres runtime du cerveau orchestrateur."""

    url_instance_a: str = "http://127.0.0.1:8000/api/v1/classify"
    url_classification_mp_chimie: str = Field(
        default="http://127.0.0.1:8001/api/v1/classify",
        description="API XLM-RoBERTa MP/CHIMIE. Compose : http://agent-classification:8001/api/v1/classify",
    )
    url_recette_agent: str = "http://127.0.0.1:8002/api/v1/recette"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "mistral:7b-instruct"
    inventory_excel_path: str = (
        "/home/saifakkari/PFE_Saif/Back-end/projet_industriel_agi/"
        "data_sources/piece_de_rechange_data/ECA_PDR_31122023_Raw(AutoRecovered).csv.xlsx"
    )
    recipe_correlation_csv_path: str = (
        "/app/data_sources/recipe_data/correlation_qualite_ingredients_recette.csv"
    )
    inventory_dashboard_top_n: int = 20
    inventory_classification_max_items: int = 500
    inventory_classification_concurrency: int = 20
    database_url: str = "sqlite:////tmp/cerveau.db"
    auth_secret_key: str = "CHANGE_ME_SECRET_KEY_SOTIPAPIER"
    auth_algorithm: str = "HS256"
    auth_access_token_expire_minutes: int = 480
    auth_google_client_ids: str = ""
    auth_admin_bootstrap_key: str = ""
    auth_admin_emails: str = ""
    erp_sql_connect_timeout_seconds: int = 5
    self_learning_db_long_memory_path: str = "/tmp/db_long_memory"
    s3_memory_bucket: str = ""
    s3_sqlite_key: str = "runtime/cerveau.db"
    s3_sqlite_snapshot_prefix: str = "runtime/snapshots"
    s3_sqlite_sync_interval_seconds: int = 180

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne une instance cachée de la configuration."""
    return Settings()

