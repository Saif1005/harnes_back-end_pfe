from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    return raw in {"1", "true", "yes", "on"}


class HarnessSettings:
    def __init__(self) -> None:
        data_root = os.getenv("DATA_ROOT", "/opt/harness/data")
        models_root = os.getenv("MODELS_ROOT", "/opt/harness/models")
        db_root = os.getenv("DB_ROOT", "/opt/harness/db")
        self.app_name = "industrial-harness-backend"
        self.app_version = "0.1.0"
        self.debug = _env_bool("DEBUG", False)
        # Orchestrateur ReAct / superviseur (Ollama)
        self.orchestrator_model = os.getenv("ORCHESTRATOR_MODEL", "mistral:7b")
        # Agent recette : Qwen 7B instruct (calcul + formulation recette via LLM)
        self.recipe_llm_model = os.getenv("RECIPE_LLM_MODEL", "qwen2.5:7b-instruct")
        self.recipe_model = os.getenv("RECIPE_MODEL", self.recipe_llm_model)
        self.recipe_use_llm = _env_bool("RECIPE_USE_LLM", True)
        self.recipe_llm_postprocess_remote = _env_bool("RECIPE_LLM_POSTPROCESS_REMOTE", True)
        # Classification : XLM-RoBERTa large (checkpoint + libellés outils)
        self.classification_model_name = os.getenv("CLASSIFICATION_MODEL_NAME", "xlm-roberta-large")
        self.classifier_primary_model = os.getenv("CLASSIFIER_PRIMARY_MODEL", "xlm-roberta-large-classifier")
        self.classifier_secondary_model = os.getenv("CLASSIFIER_SECONDARY_MODEL", "xlm-roberta-large-classifier")
        # Prédiction stock : Ridge (scikit-learn)
        self.prediction_model_name = os.getenv("PREDICTION_MODEL_NAME", "ridge-regression")
        self.dataset_classification_path = os.getenv(
            "DATASET_CLASSIFICATION_PATH", f"{data_root}/dataset_classification_compatible.csv"
        )
        self.formula_exact_path = os.getenv("FORMULA_EXACT_PATH", f"{data_root}/formuleexacte.csv")
        self.recipe_correlation_path = os.getenv(
            "RECIPE_CORRELATION_PATH", f"{data_root}/correlation_qualite_ingredients_recette.csv"
        )
        self.recipe_markdown_path = os.getenv("RECIPE_MARKDOWN_PATH", f"{data_root}/formule_recette.md")
        self.legacy_url_instance_a = os.getenv("LEGACY_URL_INSTANCE_A", "http://127.0.0.1:8000/api/v1/classify")
        self.legacy_url_classification_mp_chimie = os.getenv(
            "LEGACY_URL_CLASSIFICATION_MP_CHIMIE", "http://127.0.0.1:8001/api/v1/classify"
        )
        self.legacy_url_recette_agent = os.getenv("LEGACY_URL_RECETTE_AGENT", "http://127.0.0.1:8002/api/v1/recette")
        self.training_output_dir = os.getenv("TRAINING_OUTPUT_DIR", models_root)
        self.classification_checkpoint_dir = os.getenv(
            "CLASSIFICATION_CHECKPOINT_DIR", f"{models_root}/classification_xlm_roberta_large"
        )
        self.classification_checkpoint_manifest = os.getenv(
            "CLASSIFICATION_CHECKPOINT_MANIFEST", f"{self.classification_checkpoint_dir}/checkpoint_manifest.json"
        )
        self.training_default_epochs = int(os.getenv("TRAINING_DEFAULT_EPOCHS", "3"))
        self.training_default_test_size = float(os.getenv("TRAINING_DEFAULT_TEST_SIZE", "0.2"))
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.supervisor_use_llm = _env_bool("SUPERVISOR_USE_LLM", True)
        self.orchestrator_react_enabled = _env_bool("ORCHESTRATOR_REACT_ENABLED", True)
        self.react_max_steps = int(os.getenv("REACT_MAX_STEPS", "8"))
        self.reasoning_context_max_chars = int(os.getenv("REASONING_CONTEXT_MAX_CHARS", "12000"))
        self.reasoning_mcmc_enabled = _env_bool("REASONING_MCMC_ENABLED", True)
        # Lower temperature and fewer steps to reduce over-exploration/hallucinated tool chains.
        self.reasoning_mcmc_steps = int(os.getenv("REASONING_MCMC_STEPS", "8"))
        self.reasoning_mcmc_temperature = float(os.getenv("REASONING_MCMC_TEMPERATURE", "0.15"))
        self.reasoning_backtrack_enabled = _env_bool("REASONING_BACKTRACK_ENABLED", True)
        self.reasoning_backtrack_delta = float(os.getenv("REASONING_BACKTRACK_DELTA", "0.12"))
        self.reasoning_memory_enabled = _env_bool("REASONING_MEMORY_ENABLED", True)
        self.mcp_enabled = _env_bool("MCP_ENABLED", False)
        self.mcp_transport = os.getenv("MCP_TRANSPORT", "auto")  # auto | http | sdk
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8040/mcp/tool-call")
        self.mcp_server_name = os.getenv("MCP_SERVER_NAME", "harness-tools")
        self.runtime_db_path = os.getenv("RUNTIME_DB_PATH", f"{db_root}/runtime.sqlite")
        self.stock_runtime_path = os.getenv("STOCK_RUNTIME_PATH", f"{db_root}/stock_runtime.sqlite")
        self.stock_mapped_dataset_path = os.getenv(
            "STOCK_MAPPED_DATASET_PATH", f"{data_root}/dataset_stock_mapped.csv"
        )
        self.stock_official_history_path = os.getenv(
            "STOCK_OFFICIAL_HISTORY_PATH", f"{data_root}/magasin_stock_historique_2017_2023.csv"
        )


SETTINGS = HarnessSettings()

