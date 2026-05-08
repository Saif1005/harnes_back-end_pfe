/** Aligné sur la réponse FastAPI `AskAgentResponse` du cerveau orchestrateur. */
export interface StockAlert {
  ingredient?: string;
  matched_inventory_key?: string;
  required_kg?: number;
  available_kg?: number;
  missing_kg?: number;
  severity?: string;
}

export interface InventoryDashboard {
  source_excel?: string;
  rows_read?: number;
  unique_articles?: number;
  top_items?: Array<{ article: string; stock_total: number }>;
  classification_errors?: number;
  error?: string;
  [key: string]: unknown;
}

export interface AskAgentResponse {
  id_article_erp: string;
  route_intent?: string;
  statut_classification: string;
  categorie_cible: string;
  resultat_agent_brut?: string;
  stock_alerts: StockAlert[];
  recipe_items?: Array<{
    ingredient?: string;
    qty_kg?: number;
    quantity_kg?: number;
    required_kg?: number;
    required_value?: number;
    required_unit?: string;
  }>;
  production_capacity?: {
    requested_tonnage?: number;
    max_producible_tonnage?: number;
    full_orders_possible?: number;
    limiting_ingredient?: string;
    limiting_available_kg?: number;
    limiting_required_per_ton_kg?: number;
  };
  stock_prediction?: {
    model?: string;
    history_points?: number;
    horizon_steps?: number;
    trained_points?: number;
    trained_at?: string;
    auto_retrained?: boolean;
    current_totals_kg?: {
      MP?: number;
      CHIMIE?: number;
      PDR?: number;
    };
    predicted_totals_kg?: {
      MP?: number;
      CHIMIE?: number;
      PDR?: number;
    };
    projected_delta_kg?: {
      MP?: number;
      CHIMIE?: number;
      PDR?: number;
    };
    depletion_risk?: {
      MP?: string;
      CHIMIE?: string;
      PDR?: string;
    };
    confidence_score?: {
      MP?: number;
      CHIMIE?: number;
      PDR?: number;
    };
  };
  final_response?: string;
  confirmation_required?: boolean;
  confirmation_token?: string;
  production_applied?: boolean;
  inventory_dashboard?: InventoryDashboard;
  reponse_agent: string;
}

export interface AskAgentPayload {
  id_article_erp: string;
  description: string;
  categorie: string;
  question_operateur: string;
  session_id?: string;
  confirm_production?: boolean;
  confirmation_token?: string;
  /** Si renseigné : le graphe saute le routeur LLM et exécute directement ce nœud. */
  preferred_route?: "classification" | "recette" | "workflow" | "human";
}
