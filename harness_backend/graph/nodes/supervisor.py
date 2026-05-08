from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from harness_backend.config.settings import SETTINGS
from harness_backend.core.state import HarnessState
from harness_backend.graph.routes import detect_route

logger = logging.getLogger(__name__)

try:
    from langchain_ollama import ChatOllama  # type: ignore
except Exception:  # noqa: BLE001
    ChatOllama = None


def _llm_route(query: str) -> str:
    if not SETTINGS.supervisor_use_llm or ChatOllama is None:
        return ""
    llm = ChatOllama(base_url=SETTINGS.ollama_base_url, model=SETTINGS.orchestrator_model, temperature=0.0)
    prompt = (
        "Return ONLY JSON: {\"route\":\"classification_worker|recipe_worker|stock_worker|synthesizer\"}. "
        f"Query: {query}"
    )
    try:
        resp = llm.invoke(prompt)
        content = str(getattr(resp, "content", resp) or "")
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(content[start : end + 1])
            route = str(obj.get("route", "")).strip()
            if route in {"classification_worker", "recipe_worker", "stock_worker", "synthesizer"}:
                return route
    except Exception:
        return ""
    return ""


def node_supervisor(state: HarnessState) -> HarnessState:
    """
    Central router: en mode ReAct, délègue l'orchestration à ``react_orchestrator``.
    Sinon routage classique (LLM one-shot + heuristique) vers un worker spécialisé.
    """
    try:
        query = state.get("normalized_query") or state.get("input_query", "")
        if SETTINGS.orchestrator_react_enabled:
            route: str = "react_orchestrator"
            state.setdefault("metadata", {})["orchestration_mode"] = "react"
        else:
            route = _llm_route(query) or detect_route(query)
            state.setdefault("metadata", {})["orchestration_mode"] = "pipeline"
        state["route"] = route  # type: ignore[assignment]
        state.setdefault("metadata", {})["orchestrator_model"] = SETTINGS.orchestrator_model
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Supervisor routed run_id=%s to route=%s", state.get("run_id", ""), route)
    except Exception as exc:  # defensive path for graph stability
        logger.exception("Supervisor routing failed: %s", exc)
        state.setdefault("errors", []).append(f"supervisor_error: {exc}")
        state["route"] = "error"
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

