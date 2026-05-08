"""Schémas d'entrée/sortie FastAPI pour l'orchestrateur."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AskAgentRequest(BaseModel):
    """Payload d'entrée opérateur."""

    id_article_erp: str = Field(..., description="Identifiant ERP article")
    description: str = Field(..., description="Description article")
    categorie: str = Field(default="", description="Contexte machine/zone")
    question_operateur: str = Field(default="", description="Question libre de l'opérateur")
    confirm_production: bool = Field(
        default=False,
        description="Confirme l'exécution de la commande recette et autorise la décrémentation stock.",
    )
    confirmation_token: str = Field(
        default="",
        description="Token de confirmation renvoyé par l'étape précédente, requis pour appliquer la production.",
    )
    preferred_route: str = Field(
        default="",
        description="classification | recette | workflow | human — vide = routage automatique (LLM). Si renseigné, exécution directe du nœud correspondant.",
    )
    session_id: str = Field(
        default="",
        description="Identifiant de session conversationnelle (mémoire court terme).",
    )


class AskAgentResponse(BaseModel):
    """Réponse finale de l'orchestrateur."""

    id_article_erp: str
    route_intent: str = Field(default="", description="Route choisie : classification | recette | human")
    statut_classification: str
    categorie_cible: str
    resultat_agent_brut: str = Field(
        default="",
        description="Sortie brute de l'agent spécialisé (classification ou recette) avant reformulation.",
    )
    stock_alerts: list[dict] = Field(
        default_factory=list,
        description="Alertes de stock calculées au nœud de contrôle stock (nœud 3).",
    )
    recipe_items: list[dict] = Field(
        default_factory=list,
        description="Recette structurée (ingredient, qty_kg) pour affichage tableau/histogramme.",
    )
    production_capacity: dict = Field(
        default_factory=dict,
        description="Estimation capacité basée stock réel (tonnage max et nombre de commandes possibles).",
    )
    stock_prediction: dict = Field(
        default_factory=dict,
        description="Prédiction ML-like des stocks (MP/CHIMIE/PDR) basée sur l'historique des consommations.",
    )
    final_response: str = Field(
        default="",
        description="Réponse finale supervisée (validation production ou alerte).",
    )
    confirmation_required: bool = Field(
        default=False,
        description="True si une confirmation explicite est attendue avant décrémentation stock.",
    )
    confirmation_token: str = Field(
        default="",
        description="Token à renvoyer avec confirm_production=true pour exécuter la consommation.",
    )
    production_applied: bool = Field(
        default=False,
        description="True si la consommation recette a été appliquée et déduite du stock.",
    )
    inventory_dashboard: dict = Field(
        default_factory=dict,
        description="Tableau de bord consolidé du stock injecté dans le state.",
    )
    reponse_agent: str


class ProductionPoint(BaseModel):
    period: str
    quantity_ton: float


class ProductionArticleTrend(BaseModel):
    article: str
    points: list[ProductionPoint]


class ProductionTopArticle(BaseModel):
    article: str
    quantity_ton: float


class ProductionSummary(BaseModel):
    unique_articles: int
    total_quantity_ton: float
    active_lines: int


class ProductionDashboardResponse(BaseModel):
    start_year: int
    summary: ProductionSummary
    article_options: list[str]
    monthly_totals: list[ProductionPoint]
    top_articles: list[ProductionTopArticle]
    article_trends: list[ProductionArticleTrend]


class FileClassificationRow(BaseModel):
    id_article_erp: str
    description: str
    categorie: str
    stage1_mp_pdr: str
    stage2_mp_chimie: str
    final_label: str
    error: str = ""


class FileClassificationJobResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    total_rows: int
    processed_rows: int
    progress_pct: float
    counts: dict[str, int]
    error: str = ""
    recent_results: list[FileClassificationRow] = Field(default_factory=list)


class AuthRegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthGoogleLoginRequest(BaseModel):
    id_token: str


class AuthAdminBootstrapRequest(BaseModel):
    email: str
    bootstrap_key: str


class AuthAdminRegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    bootstrap_key: str = ""


class AuthAdminRegistrationStatusResponse(BaseModel):
    admin_exists: bool


class AuthAdminForgotPasswordRequest(BaseModel):
    email: str
    new_password: str
    bootstrap_key: str


class AuthUserResponse(BaseModel):
    id: str
    email: str
    name: str = ""
    role: str = "operator"


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class AdminSessionResponse(BaseModel):
    session_id: str
    user: AuthUserResponse
    permissions: list[str] = Field(default_factory=list)


class ShortTermMemoryCreateRequest(BaseModel):
    session_id: str = ""
    role: str = "user"
    content: str
    metadata: dict = Field(default_factory=dict)


class ShortTermMemoryItem(BaseModel):
    id: int
    session_id: str
    turn_index: int
    role: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: str


class ShortTermMemoryListResponse(BaseModel):
    session_id: str
    items: list[ShortTermMemoryItem] = Field(default_factory=list)


class LongTermMemoryUpsertRequest(BaseModel):
    namespace: str = "global"
    memory_key: str
    memory_value: str
    score: float = 1.0
    metadata: dict = Field(default_factory=dict)


class LongTermMemoryItem(BaseModel):
    id: int
    namespace: str
    memory_key: str
    memory_value: str
    score: float
    metadata: dict = Field(default_factory=dict)
    updated_at: str


class LongTermMemoryListResponse(BaseModel):
    items: list[LongTermMemoryItem] = Field(default_factory=list)


class ERPConfigUpsertRequest(BaseModel):
    db_type: str = "postgresql"
    host: str = ""
    port: int = 5432
    db_name: str = ""
    username: str = ""
    password: str = ""
    enabled: bool = False


class ERPConfigResponse(BaseModel):
    db_type: str
    host: str
    port: int
    db_name: str
    username: str
    password_masked: str = ""
    enabled: bool
    updated_at: str
    updated_by_user_id: str = ""


class ERPConnectionTestResponse(BaseModel):
    ok: bool
    detail: str = ""


class AdminMonitoringOverviewResponse(BaseModel):
    app_uptime_seconds: int
    users_count: int
    short_memories_count: int
    long_memories_count: int
    classification_jobs_total: int
    classification_jobs_running: int
    classification_jobs_done: int
    classification_jobs_error: int
    request_type_counts: dict[str, int] = Field(default_factory=dict)
    recent_executions: list[dict] = Field(default_factory=list)
    instance_performance: dict = Field(default_factory=dict)
    subagent_traces: list[dict] = Field(default_factory=list)


class SelfLearningRetrainRequest(BaseModel):
    target_model: str = "mistral:7b-instruct"
    max_memories: int = 500


class SelfLearningJobResponse(BaseModel):
    job_id: str
    status: str
    detail: str = ""
    target_model: str = ""
    dataset_path: str = ""
    output_path: str = ""
    memories_used: int = 0
    started_at: str = ""
    updated_at: str = ""


class WarehouseIngestionJobResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    total_rows: int
    processed_rows: int
    progress_pct: float
    counts: dict[str, int]
    qty_by_label_kg: dict[str, float] = Field(default_factory=dict)
    cancel_requested: bool = False
    error: str = ""
    batch_id: str = ""


class WarehouseDatabaseSummaryResponse(BaseModel):
    total_records: int
    latest_batch_id: str = ""
    latest_source_file: str = ""
    latest_snapshot_date: str = ""
    total_stock_kg: float = 0.0
    labels: dict[str, int] = Field(default_factory=dict)
    qty_by_label_kg: dict[str, float] = Field(default_factory=dict)
    top_ingredients_kg: list[dict] = Field(
        default_factory=list,
        description="Top ingrédients (description article) avec quantité totale en kg.",
    )
