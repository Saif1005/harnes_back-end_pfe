# Documentation détaillée — Harness Backend (industriel)

Ce document décrit la logique, l’architecture, les flux de données et les points d’extension du backend **Harness** (`harness_backend/`), conçu pour orchestrer des workflows industriels (classification matières, stock, recette, prédiction) en lien avec un contexte type **ERP**, avec **LangGraph**, **MCP**, persistance et garde-fous.

---

## 1. Objectif métier

Le backend automatise une **chaîne de production informationnelle** :

1. **Classifier** les références (MP / PDR / CHIMIE) et alimenter une vision stock cohérente.
2. **Calculer une recette** pour un article et un tonnage, avec possibilité de **validation opérateur** (HITL) avant impact stock.
3. **Mettre à jour le stock opérationnel** après acceptation, puis **prévoir** des tendances (Ridge sur séries).

L’orchestration combine des **données tabulaires** (CSV, SQLite), des **microservices legacy** (HTTP), des **modèles ML** (checkpoint XLM-R, Ridge) et des **LLM** (Mistral pour le raisonnement d’orchestration, Qwen pour la formulation recette).

---

## 2. Stack technique

| Composant | Rôle |
|-----------|------|
| **FastAPI** | API HTTP, schémas Pydantic, routers modulaires. |
| **LangGraph** | Graphe d’état (`StateGraph`) quand la dépendance est disponible ; sinon runner séquentiel équivalent. |
| **SQLite** | `runtime.sqlite` (invocations, exécutions d’outils, mémoire raisonnement) ; `stock_runtime.sqlite` (stock agrégé + mouvements) ; `checkpoints.sqlite` (états graphe pour HITL / reprise). |
| **Ollama** | LLM locaux : orchestration (Mistral), synthèse recette (Qwen instruct). |
| **scikit-learn** | TF-IDF + régression logistique (entraînement classification fallback) ; **Ridge** (prédiction). |
| **transformers / torch** | Optionnel : fine-tuning et inférence **XLM-RoBERTa large** pour la classification (checkpoint). |
| **MCP** | Enveloppes d’appel d’outils ; serveur MCP optionnel ; mémoire raisonnement dédiée (`/mcp/reasoning-memory/*`). |

---

## 3. Pipeline métier (alignement « 7 étapes » Harness)

Le code matérialise les étapes suivantes (noms de nœuds / modules) :

| Étape | Rôle | Implémentation principale |
|-------|------|----------------------------|
| **1. Entrée (Input Gate)** | Requête HTTP validée | `api/schemas/requests.py`, `api/routers/invoke.py` |
| **2. Superviseur** | Routage vers le mode d’orchestration | `graph/nodes/supervisor.py` — si `ORCHESTRATOR_REACT_ENABLED`, route vers `react_orchestrator` ; sinon routage classique vers workers. |
| **3. Agents / workers** | Planification d’outils (mode pipeline) | `graph/nodes/workers.py`, `graph/nodes/worker_plans.py` |
| **3 bis. ReAct central** | Boucle pensée → action → observation | `graph/nodes/react_orchestrator.py` |
| **4. Guardrails** | Validation stricte des plans d’outils | `graph/nodes/guardrails.py` (`ToolCall` Pydantic) |
| **5. HITL** | Interruption avant actions sensibles | `graph/nodes/hitl_interrupt.py` — `recipe_compute` **critique** si signaux commande / tonnage (`react_orchestrator`). |
| **6. Exécution outils (sandbox)** | Appels isolés, traçabilité MCP | `graph/nodes/tool_executor.py`, `tools/registry.py`, `tools/adapters/mcp_adapter.py` |
| **7. Synthèse** | Réponse utilisateur agrégée | `graph/nodes/synthesizer.py` (table recette, alertes stock, capacité) |

---

## 4. Graphe LangGraph et catalogue de nœuds

Fichier : `graph/builder.py`.

Ordre typique en mode **ReAct** :

`START` → `supervisor` → `react_orchestrator` → `guardrails` → `hitl_interrupt` → [`tool_executor` si pas HITL] → `synthesizer` → `END`

Catalogue explicite : `graph/nodes/catalog.py` (`LANGGRAPH_NODE_CATALOG`).

Le runner de secours (`HarnessGraphRunner`) reproduit la même séquence sans dépendre de LangGraph compilé.

---

## 5. État partagé (`HarnessState`)

Fichier : `core/state.py`.

Champs notables : `run_id`, `session_id`, `user_id`, `input_query`, `normalized_query`, `route`, `tool_plan`, `tool_results`, `react_trace`, `reasoning_branch_stack`, flags HITL (`hitl_required`, `approval_id`, …), `metadata`, `errors`, `output_message`.

Les résultats d’outils s’accumulent dans `tool_results` ; le nœud `tool_executor` **concatène** avec les exécutions déjà faites dans ReAct pour ne pas les écraser.

---

## 6. Flux de données (sources → transformations → sorties)

### 6.1 Entrée utilisateur

- **`POST /invoke`** : JSON `{ "query", "session_id?", "user_id?" }` → construit un `HarnessState` → exécute le graphe → persiste `invoke_runs` (`services/persistence.py`).
- Réponse : `run_id`, `status`, `route`, `message`, `approval_id` (si interruption), `details.tool_results`, `metadata`, `errors`.

### 6.2 Données « magasin / classification »

- Fichier principal : `DATASET_CLASSIFICATION_PATH` (défaut sous `DATA_ROOT`) — colonnes attendues après normalisation : `texte`, `label`, `quantity_kg`.
- **Admin données** : `POST /admin/data/map-legacy` — mappe un export hétérogène vers un CSV harmonisé (`STOCK_MAPPED_DATASET_PATH`).
- **`POST /admin/data/rebuild-stock`** — reconstruit les tables **`stock_items`** / mouvements dans `stock_runtime.sqlite` (`services/stock_runtime.py`).

Les outils **stock** et **prédiction** lisent en priorité le **stock runtime** ; sinon ils retombent sur le CSV et peuvent déclencher un rebuild.

### 6.3 Données « recette »

- **Distant** : `LEGACY_URL_RECETTE_AGENT` — si OK, texte recette + parsing (`services/legacy_compat.parse_recipe_items`).
- **Local** : `RECIPE_CORRELATION_PATH` — ratios `ratio_kg_per_ton` par `family_pf` / ingrédient ; calcul déterministe des `required_kg`.
- **LLM Qwen** (`RECIPE_LLM_MODEL`) : reformate le texte recette en respectant les quantités imposées (voir `tools/implementations/recipe_tools.py`). Désactivation : `RECIPE_USE_LLM=false`.

### 6.4 Classification

Ordre de décision dans `classification_tools.py` :

1. **Checkpoint XLM-R** local si pipeline chargé (`services/classification_checkpoint.py` + manifest).
2. **Microservices** `legacy_url_instance_a` et `legacy_url_classification_mp_chimie`.
3. **Heuristique lexicale** de secours.

Entrée : texte ; sortie : `label`, `model_used`, `source`.

### 6.5 Prédiction

- Séries par famille (MP / CHIMIE / PDR) : priorité **séries dérivées du stock runtime + mouvements** (`get_prediction_series`) ; sinon agrégation depuis le CSV.
- Algorithme : **Ridge** (`PREDICTION_MODEL_NAME`) si `sklearn` disponible ; sinon fallback linéaire.

### 6.6 Après validation commande (HITL)

- **`POST /resume`** avec `approved: true` — recharge l’état depuis `checkpoints.sqlite`, exécute le plan d’outils restant, applique la **consommation** recette sur le stock SQLite (`apply_recipe_consumption`), puis rafraîchit stock / prédiction (voir `api/routers/resume.py`).

---

## 7. Modèles et responsabilités

| Rôle | Modèle / algorithme | Variable(s) d’environnement |
|------|---------------------|-------------------------------|
| Orchestrateur ReAct / superviseur LLM | **Mistral 7B** (Ollama) | `ORCHESTRATOR_MODEL`, `OLLAMA_BASE_URL`, `SUPERVISOR_USE_LLM` |
| Agent recette (formulation) | **Qwen 7B instruct** (Ollama) | `RECIPE_LLM_MODEL`, `RECIPE_USE_LLM`, `RECIPE_LLM_POSTPROCESS_REMOTE` |
| Classification | **XLM-RoBERTa large** (checkpoint + libellés) | `CLASSIFICATION_MODEL_NAME`, `CLASSIFIER_*`, `CLASSIFICATION_CHECKPOINT_*` |
| Prédiction stock | **Ridge regression** | `PREDICTION_MODEL_NAME` |

L’endpoint **`GET /system/protocols`** expose une vue synthétique des modèles et des capacités runtime.

---

## 8. Raisonnement avancé (couche `reasoning/`)

| Module | Fonction |
|--------|----------|
| `context_window.py` | Compression de la trace ReAct pour respecter la fenêtre de contexte LLM (`REASONING_CONTEXT_MAX_CHARS`). |
| `markov_chain.py` | Ordre de phases industrielles (suggestions d’outils voisins). |
| `reward_model.py` | Score d’intention et score d’état après outil (direction / qualité). |
| `mcmc_policy.py` | **Metropolis–Hastings** discret sur candidats d’actions. |
| `backtrack.py` | Snapshots + annulation si chute de récompense (`REASONING_BACKTRACK_*`). |

Les étapes significatives peuvent être écrites dans **`reasoning_memory`** (SQLite) via **`POST /mcp/reasoning-memory/append`** et relues avec **`/read`**.

---

## 9. API REST — inventaire

| Préfixe / chemin | Usage |
|------------------|--------|
| `GET /health` | Santé du service. |
| `POST /invoke` | Invocation principale du graphe. |
| `POST /resume` | Reprise HITL (approbation / refus). |
| `GET /approvals/pending` | Liste des approbations en attente (checkpoints). |
| `POST /admin/data/map-legacy` | Normalisation CSV legacy → dataset stock. |
| `POST /admin/data/rebuild-stock` | Reconstruction base stock runtime. |
| `POST /admin/training/classification` | Entraînement classification (TF-IDF / XLM selon config). |
| `POST /admin/training/prediction` | Entraînement prédiction Ridge. |
| `GET /system/protocols` | Protocoles, imports, nœuds LangGraph, modèles, reasoning. |
| `POST /mcp/tool-call` | Appel outil style MCP (`McpEnvelope`). |
| `POST /mcp/reasoning-memory/append` | Persistance mémoire raisonnement. |
| `POST /mcp/reasoning-memory/read` | Lecture de l’historique mémoire par `session_id`. |
| `POST /tools/classification` … | Appels directs outils. |
| `GET /admin/monitoring/*` | Métriques, tool-runs, config runtime. |

Point d’entrée application : `main.py` (`create_app()`).

Serveur MCP autonome : `mcp_server_main.py` (outil + mémoire raisonnement, avec `init_runtime_db()` au démarrage).

---

## 10. MCP et outils (`tools/contracts.py`)

Les noms d’outils typés : `classification_run`, `recipe_compute`, `stock_check`, `prediction_regression`.

Chaque appel peut porter un **`McpContext`** (run_id, session_id, user_id, trace_id, route, metadata) pour corrélation dans `tool_runs`.

Le **`MCPBridge`** (`tools/adapters/mcp_adapter.py`) peut cibler le SDK MCP, HTTP, ou le dispatcher local selon `MCP_ENABLED`, `MCP_TRANSPORT`, `MCP_SERVER_URL`.

---

## 11. Persistance SQLite (`services/persistence.py`)

Tables principales (initialisées au startup) :

- **`invoke_runs`** : une ligne par invocation (`run_id`, query, route, status, message, …).
- **`tool_runs`** : une ligne par exécution d’outil (payload + résultat JSON).
- **`reasoning_memory`** : événements de raisonnement (session, run, payload JSON).

Les chemins DB peuvent retomber sous `/tmp/harness/` si `/opt/harness` n’est pas accessible (permissions).

---

## 12. Entraînement

- **Classification** : `training/classification_trainer.py` — modes TF-IDF + régression logistique et/ou fine-tuning XLM-R selon dépendances ; artefacts sous `TRAINING_OUTPUT_DIR`.
- **Prédiction** : `training/prediction_trainer.py` — Ridge, séries issues du dataset.

Routers : `api/routers/training.py`.

Images Docker dédiées possibles sous `docker/training/` (compose séparé selon dépôt).

---

## 13. Compatibilité legacy

`services/legacy_compat.py` centralise parsing recette, normalisation de clés, matching inventaire, alertes stock, capacité de production, alias d’articles.

`tools/adapters/legacy_tools_api.py` : appels HTTP vers les anciens microservices (classification, recette).

---

## 14. Configuration — variables d’environnement (référence)

**Données et chemins** : `DATA_ROOT`, `MODELS_ROOT`, `DB_ROOT`, `DATASET_CLASSIFICATION_PATH`, `RECIPE_CORRELATION_PATH`, `FORMULA_EXACT_PATH`, `RECIPE_MARKDOWN_PATH`, `STOCK_RUNTIME_PATH`, `STOCK_MAPPED_DATASET_PATH`, `RUNTIME_DB_PATH`.

**LLM** : `OLLAMA_BASE_URL`, `ORCHESTRATOR_MODEL`, `RECIPE_LLM_MODEL`, `RECIPE_MODEL`, `SUPERVISOR_USE_LLM`, `RECIPE_USE_LLM`, `RECIPE_LLM_POSTPROCESS_REMOTE`.

**ReAct / reasoning** : `ORCHESTRATOR_REACT_ENABLED`, `REACT_MAX_STEPS`, `REASONING_CONTEXT_MAX_CHARS`, `REASONING_MCMC_*`, `REASONING_BACKTRACK_*`, `REASONING_MEMORY_ENABLED`.

**MCP** : `MCP_ENABLED`, `MCP_TRANSPORT`, `MCP_SERVER_URL`, `MCP_SERVER_NAME`.

**Legacy HTTP** : `LEGACY_URL_INSTANCE_A`, `LEGACY_URL_CLASSIFICATION_MP_CHIMIE`, `LEGACY_URL_RECETTE_AGENT`.

---

## 15. Arborescence logique (modules)

```
harness_backend/
  main.py                 # Application FastAPI
  mcp_server_main.py      # Serveur MCP léger
  config/settings.py      # Configuration centralisée
  core/state.py           # HarnessState (TypedDict)
  api/routers/            # Endpoints REST
  api/schemas/            # Pydantic request/response
  graph/
    builder.py            # LangGraph + runner fallback
    routes.py             # Heuristique de route (mots-clés)
    checkpoint/sqlite_store.py
    nodes/                # supervisor, react_orchestrator, workers, guardrails, hitl, tool_executor, synthesizer
  tools/
    contracts.py          # MCP + ToolCall / ToolResult
    registry.py           # dispatch_tool
    implementations/      # classification, recipe, stock, prediction
    adapters/             # MCP bridge, legacy HTTP
  services/
    persistence.py        # SQLite runtime + reasoning_memory
    stock_runtime.py      # Stock opérationnel + map legacy
    legacy_compat.py      # Utilitaires métier
    classification_checkpoint.py
    mcp_sdk.py
  reasoning/              # CoT, Markov, MCMC, reward, backtrack
  training/               # classification_trainer, prediction_trainer
```

---

## 16. Déploiement (rappel)

- Cibles typiques : **Docker** / **Compose** avec volumes `/opt/harness/data`, `/opt/harness/models`, `/opt/harness/db`.
- Sur l’instance : installer **Ollama** et tirer les modèles (`mistral:7b`, `qwen2.5:7b-instruct`, etc.) alignés sur les variables ci-dessus.
- Vérifier les secrets et URLs legacy en production.

Pour un guide de migration depuis l’ancien monolithe, voir aussi `ARCHITECTURE_MIGRATION_MAP.md` à la racine du module Harness.

---

## 17. Glossaire rapide

| Terme | Signification |
|-------|----------------|
| **Harness** | Cadre d’orchestration pipeline + outils + persistance. |
| **HITL** | Human-in-the-loop : pause avant exécution critique. |
| **MCP** | Model Context Protocol : enveloppes et serveur d’outils / mémoire. |
| **ReAct** | Reasoning + Acting : boucle LLM / outils / observations. |

---

*Document généré pour refléter la structure du dépôt au moment de la rédaction. En cas d’écart, la source de vérité reste le code dans `harness_backend/`.*
