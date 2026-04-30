from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    return raw in {"1", "true", "yes", "on"}


class HarnessSettings:
    def __init__(self) -> None:
        self.app_name = "industrial-harness-backend"
        self.app_version = "0.1.0"
        self.debug = _env_bool("DEBUG", False)
        self.orchestrator_model = os.getenv("ORCHESTRATOR_MODEL", "mistral:7b")
        self.recipe_model = os.getenv("RECIPE_MODEL", "qwen2.5:7b")
        self.classifier_primary_model = os.getenv("CLASSIFIER_PRIMARY_MODEL", "camembert-classifier")
        self.classifier_secondary_model = os.getenv("CLASSIFIER_SECONDARY_MODEL", "xlm-roberta-large-classifier")
        self.dataset_classification_path = (
            "/home/saifakkari/PFE_Saif/Back-end/projet_industriel_agi/"
            "agent_pdr_microservice/data/dataset_classification_compatible.csv"
        )
        self.formula_exact_path = (
            "/home/saifakkari/PFE_Saif/Back-end/projet_industriel_agi/" "agent_pdr_microservice/data/formuleexacte.csv"
        )
        self.recipe_correlation_path = (
            "/home/saifakkari/PFE_Saif/Back-end/projet_industriel_agi/"
            "agent_pdr_microservice/data/correlation_qualite_ingredients_recette.csv"
        )
        self.recipe_markdown_path = (
            "/home/saifakkari/PFE_Saif/Back-end/projet_industriel_agi/" "agent_pdr_microservice/data/formule_recette.md"
        )
        self.legacy_url_instance_a = os.getenv("LEGACY_URL_INSTANCE_A", "http://127.0.0.1:8000/api/v1/classify")
        self.legacy_url_classification_mp_chimie = os.getenv(
            "LEGACY_URL_CLASSIFICATION_MP_CHIMIE", "http://127.0.0.1:8001/api/v1/classify"
        )
        self.legacy_url_recette_agent = os.getenv("LEGACY_URL_RECETTE_AGENT", "http://127.0.0.1:8002/api/v1/recette")
        self.training_output_dir = os.getenv("TRAINING_OUTPUT_DIR", "/tmp/harness/models")
        self.training_default_epochs = int(os.getenv("TRAINING_DEFAULT_EPOCHS", "3"))
        self.training_default_test_size = float(os.getenv("TRAINING_DEFAULT_TEST_SIZE", "0.2"))
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.supervisor_use_llm = _env_bool("SUPERVISOR_USE_LLM", True)
        self.mcp_enabled = _env_bool("MCP_ENABLED", False)
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8040/mcp/tool-call")


SETTINGS = HarnessSettings()

