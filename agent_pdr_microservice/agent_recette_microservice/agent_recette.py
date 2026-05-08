from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Importations LangChain modernes (plus stables pour la production)
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOllama

from .calculer_recette_exacte_function import calculer_recette_exacte
# --- NOUVEAUTÉ : Importation de votre prompt optimisé ---
from .prompts import SYSTEM_PROMPT_RECETTE

app = FastAPI(title="Agent Recettes API")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Configuration du LLM
llm = ChatOllama(
    model="qwen2.5-coder:7b",
    temperature=0.0,
    base_url=OLLAMA_BASE_URL,
)
tools = [calculer_recette_exacte]

# ------------------------------------------------------------------------
# LE CERVEAU DE L'AGENT : Prompt ReAct Personnalisé
# On injecte ici le template importé depuis prompts.py
# ------------------------------------------------------------------------
prompt = PromptTemplate.from_template(SYSTEM_PROMPT_RECETTE)

# Création de l'agent avec la nouvelle architecture LangChain
agent = create_react_agent(llm, tools, prompt)

# AgentExecutor protège l'application des crashs si le modèle fait une erreur de syntaxe
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    verbose=True,                # Permet de voir la chaîne de pensée (Thought/Action) dans votre terminal
    handle_parsing_errors=True   # Essentiel : Qwen s'auto-corrigera au lieu de faire crasher l'API
)

class RecetteRequest(BaseModel):
    texte: str

@app.post("/api/v1/recette")
async def recette(request: RecetteRequest) -> dict:
    try:
        # Exécution de la requête via le nouvel exécuteur
        agent_output = agent_executor.invoke({"input": request.texte})
        output_text = str(agent_output.get("output", "Pas de réponse générée."))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erreur agent recette: {exc}") from exc

    return {"status": "success", "result": output_text}