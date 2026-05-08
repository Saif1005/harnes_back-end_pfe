"""Définition du state partagé par le graphe LangGraph."""
from __future__ import annotations

from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    État du workflow orchestrateur : routage (classification / recette / humain),
    puis exécution du nœud choisi et synthèse finale si besoin.

    `messages` utilise `add_messages` (historique LangGraph).
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    id_article_erp: str
    description: str
    categorie: str
    question_operateur: str
    route_intent: str
    statut_classification: str
    categorie_cible: str
    resultat_agent_brut: str
    recipe: dict[str, object]
    stock_alerts: list[dict[str, object]]
    final_response: str
    confirm_production: bool
    confirmation_token_input: str
    confirmation_token: str
    confirmation_required: bool
    production_applied: bool
    inventory: dict[str, float]
    inventory_dashboard: dict[str, object]
    production_capacity: dict[str, object]
    stock_prediction: dict[str, object]
    workflow_stage1_label: str
    workflow_stage2_label: str
