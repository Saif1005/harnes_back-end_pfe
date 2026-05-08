from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from harness_backend.config.settings import SETTINGS
from harness_backend.core.state import HarnessState
from harness_backend.graph.nodes.worker_plans import static_tool_plan_for_route
from harness_backend.graph.routes import detect_route
from harness_backend.reasoning.backtrack import restore_snapshot, snapshot_branch
from harness_backend.reasoning.context_window import compress_trace_for_prompt
from harness_backend.reasoning.markov_chain import markov_phase_label, markov_suggest_tools
from harness_backend.reasoning.mcmc_policy import build_action_candidates, metropolis_hastings_discrete
from harness_backend.reasoning.reward_model import score_action_intent, score_incumbent_state
from harness_backend.services.persistence import append_reasoning_memory
from harness_backend.tools.contracts import McpContext, McpEnvelope, ToolName, ToolPayload
from harness_backend.tools.registry import dispatch_tool

logger = logging.getLogger(__name__)

try:
    from langchain_ollama import ChatOllama  # type: ignore
except Exception:  # noqa: BLE001
    ChatOllama = None

REACT_TOOLS: frozenset[str] = frozenset(
    {"classification_run", "recipe_compute", "stock_check", "prediction_regression", "FINISH"}
)


def _requires_recipe_hitl(query: str) -> bool:
    q = (query or "").lower()
    if re.search(r"\b(commande|confirmer|passer\s+commande|valider\s+production)\b", q, re.IGNORECASE):
        return True
    if re.search(r"\b(\d+(?:[.,]\d+)?)\s*(t\b|tonne|tonnes|kg)\b", q, re.IGNORECASE):
        return True
    return False


def _truncate_obs(raw: dict, limit: int = 1200) -> str:
    try:
        s = json.dumps(raw, ensure_ascii=True, default=str)
    except Exception:  # noqa: BLE001
        s = str(raw)
    if len(s) > limit:
        return s[:limit] + "…"
    return s


def _parse_react_payload(content: str) -> dict[str, str] | None:
    raw = content or ""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    thought = str(obj.get("thought", "")).strip()
    action = str(obj.get("action", "")).strip()
    query = str(obj.get("query", "")).strip()
    return {"thought": thought, "action": action, "query": query}


def _normalize_llm_action(raw_action: str, query: str) -> tuple[str, list[str]]:
    """
    Accept imperfect LLM outputs like:
    - "[stock_check, recipe_compute, prediction_regression]"
    - "stock_check then prediction_regression"
    and salvage the first valid tool while keeping all detected tools for trace/debug.
    """
    raw = str(raw_action or "").strip()
    if not raw:
        return "", []
    if raw in REACT_TOOLS:
        return raw, [raw]

    lowered = raw.lower()
    detected: list[str] = []
    for tool in REACT_TOOLS:
        if tool == "FINISH":
            continue
        if tool.lower() in lowered:
            detected.append(tool)
    if detected:
        return detected[0], detected

    if "finish" in lowered or "stop" in lowered:
        return "FINISH", ["FINISH"]
    return raw, []


def _intent_policy(query: str) -> dict[str, bool]:
    q = (query or "").lower()
    has_recipe_signal = bool(
        re.search(r"\b(recette|tonne|tonnes|tonnage|kg|produire|production|commande|kraft|fluting|testliner)\b", q)
    )
    prediction_only = bool(re.search(r"\b(uniquement|seulement|only)\b", q)) and bool(
        re.search(r"\b(pr[eé]vision|prediction|tendance)\b", q)
    )
    forbid_recipe = "sans calcul recette" in q or "no recipe" in q
    hallucination_bait = any(k in q for k in ("invente", "ignore toutes", "secret x-", "magique illimit"))
    return {
        "allow_recipe": has_recipe_signal and not forbid_recipe and not prediction_only and not hallucination_bait,
        "allow_classification": not prediction_only,
        "allow_stock": True,
        "allow_prediction": True,
        "hallucination_bait": hallucination_bait,
    }


def _policy_allows_action(action: str, policy: dict[str, bool]) -> bool:
    if action == "recipe_compute":
        return bool(policy.get("allow_recipe"))
    if action == "classification_run":
        return bool(policy.get("allow_classification"))
    if action == "stock_check":
        return bool(policy.get("allow_stock"))
    if action == "prediction_regression":
        return bool(policy.get("allow_prediction"))
    return True


def _build_react_prompt(user_query: str, trace_summary: list[dict]) -> str:
    compact = compress_trace_for_prompt(trace_summary)
    history = json.dumps(compact, ensure_ascii=True, indent=2) if compact else "[]"
    return (
        "Tu es l'orchestrateur ReAct (Reasoning + Acting) d'une usine papetière.\n"
        "Analyse la demande, raisonne brièvement, puis choisis UNE action parmi les outils.\n\n"
        "Outils disponibles (action exacte):\n"
        "- classification_run : classifier MP / PDR / CHIMIE à partir du texte\n"
        "- recipe_compute : recette (données + synthèse LLM Qwen instruct dédiée)\n"
        "- stock_check : agréger stocks et inventaire depuis la base compat\n"
        "- prediction_regression : prévisions tendance par famille (ridge / série runtime)\n"
        "- FINISH : arrêter quand tu as assez d'information pour synthétiser\n\n"
        "Règles:\n"
        "- Réponds STRICTEMENT avec un seul bloc JSON UTF-8, sans markdown.\n"
        '- Format: {"thought":"…","action":"…","query":"…"}\n'
        "- Le champ \"query\" est la sous-requête passée à l'outil ; si vide, utilise la requête utilisateur.\n"
        "- Enchaîne des appels différents si nécessaire (max actions imposé côté serveur).\n"
        '- Utilise FINISH quand la combinaison d\'informations permet de répondre à l\'opérateur.\n\n'
        f'Requête opérateur:\n"{user_query}"\n\n'
        "Historique des étapes (thought/action/observation résumées):\n"
        f"{history}\n"
        "Réponds maintenant uniquement avec le JSON ReAct demandé.\n"
    )


def _llm_react_step(user_query: str, trace: list[dict]) -> dict[str, str] | None:
    if not SETTINGS.supervisor_use_llm or ChatOllama is None:
        return None
    llm = ChatOllama(
        base_url=SETTINGS.ollama_base_url,
        model=SETTINGS.orchestrator_model,
        temperature=0.05,
    )
    prompt = _build_react_prompt(user_query, trace)
    try:
        resp = llm.invoke(prompt)
        content = str(getattr(resp, "content", resp) or "")
        return _parse_react_payload(content)
    except Exception as exc:
        logger.warning("ReAct LLM step failed: %s", exc)
        return None


def _execute_tool(state: HarnessState, tool_name: str, tool_query: str) -> dict:
    envelope = McpEnvelope(
        source_agent="react_orchestrator",
        target_tool=cast(ToolName, tool_name),
        payload=ToolPayload(query=tool_query),
        context=McpContext(
            run_id=str(state.get("run_id", "")),
            session_id=str(state.get("session_id", "")),
            user_id=str(state.get("user_id", "")),
            trace_id=f"react-{uuid4()}",
            route="react_orchestrator",
            metadata={
                **dict(state.get("metadata") or {}),
                "react": True,
            },
        ),
    )
    result = dispatch_tool(envelope)
    return result.model_dump()


def _persist_reasoning_step(state: HarnessState, payload: dict[str, Any]) -> None:
    if not SETTINGS.reasoning_memory_enabled:
        return
    append_reasoning_memory(
        session_id=str(state.get("session_id", "") or "default"),
        run_id=str(state.get("run_id", "")),
        user_id=str(state.get("user_id", "")),
        kind="react_step",
        payload=payload,
    )


def node_react_orchestrator(state: HarnessState) -> HarnessState:
    """
    Reasoning loop: Thought → Tool call → Observation appended to react_trace.

    Déclenche HITL: si une étape doit exécuter recipe_compute avec signaux de commande/production,
    l'outil n'est pas exécuté ici ; une entrée `critical` arrive dans ``tool_plan`` pour la suite pipeline.
    """
    state.setdefault("react_trace", [])
    tool_buf: list[dict[str, Any]] = state.setdefault("tool_results", [])  # type: ignore[typeddict-item]
    md = state.setdefault("metadata", {})
    state["tool_plan"] = []
    md["orchestration_mode"] = "react"
    md["markov_phase"] = markov_phase_label(set())
    md.setdefault("reasoning_rewards", [])

    query = str(state.get("input_query", "") or "")
    policy = _intent_policy(query)
    if policy.get("hallucination_bait"):
        md["hallucination_guard"] = True
    trace: list[dict[str, Any]] = list(state.get("react_trace") or [])
    max_steps = max(2, SETTINGS.react_max_steps)
    executed_tools: set[str] = set()

    for step_idx in range(max_steps):
        step = _llm_react_step(query, trace)
        if step is None:
            break

        thought = step.get("thought", "")
        raw_llm_action = step.get("action", "").strip()
        llm_action, detected_actions = _normalize_llm_action(raw_llm_action, query)
        sub_q = step.get("query", "").strip() or query
        action = llm_action

        if action == "FINISH":
            trace.append({"step": step_idx, "thought": thought, "action": "FINISH", "observation": ""})
            break

        if not action:
            trace.append({"step": step_idx, "thought": thought, "action": "", "observation": "missing_action"})
            break

        if action not in REACT_TOOLS:
            trace.append(
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": raw_llm_action or action,
                    "observation": f"unknown_or_invalid_action: {raw_llm_action or action}",
                }
            )
            break

        if SETTINGS.reasoning_mcmc_enabled and action != "FINISH":
            candidates = build_action_candidates(action, query, executed_tools, markov_suggest_tools)
            if not trace:
                candidates = [c for c in candidates if c != "FINISH"]
            candidates = [c for c in candidates if c == "FINISH" or _policy_allows_action(c, policy)]
            if not candidates:
                candidates = ["FINISH"]

            def _score(c: str) -> float:
                base = score_action_intent(c, query, trace)
                if c == llm_action:
                    base += 0.08
                return base

            picked = metropolis_hastings_discrete(
                candidates,
                _score,
                steps=SETTINGS.reasoning_mcmc_steps,
                temperature=SETTINGS.reasoning_mcmc_temperature,
                seed=hash((state.get("run_id", ""), step_idx)) % (2**31),
            )
            action = picked
            if picked != llm_action:
                sub_q = query

        if action == "FINISH":
            trace.append(
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": "FINISH",
                    "observation": "mcmc_or_manual_finish",
                    "detected_actions": detected_actions,
                }
            )
            break

        if not _policy_allows_action(action, policy):
            trace.append(
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": action,
                    "observation": "blocked_by_intent_policy",
                    "detected_actions": detected_actions,
                    "llm_action_raw": raw_llm_action,
                }
            )
            continue

        if action == "recipe_compute" and _requires_recipe_hitl(sub_q):
            state["tool_plan"] = [
                {
                    "tool_name": "recipe_compute",
                    "critical": True,
                    "payload": {"query": sub_q},
                },
            ]
            trace.append(
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": action,
                    "observation": "deferred_critical_recipe awaits HITL approval",
                    "defer_hitl": True,
                    "detected_actions": detected_actions,
                },
            )
            _persist_reasoning_step(
                state,
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": action,
                    "defer_hitl": True,
                    "reward": score_action_intent(action, query, trace),
                },
            )
            break

        if action in executed_tools:
            trace.append(
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": action,
                    "observation": "skipped_duplicate_same_tool_turn",
                    "detected_actions": detected_actions,
                }
            )
            continue

        reward_before = score_incumbent_state(state)
        snap = snapshot_branch(state, action)
        dumped = _execute_tool(state, action, sub_q)
        tool_buf.append(dumped)
        reward_after = score_incumbent_state(state)
        rewards = md.setdefault("reasoning_rewards", [])
        rewards.append(round(reward_after, 4))
        md["markov_phase"] = markov_phase_label(set(executed_tools) | {action})

        if SETTINGS.reasoning_backtrack_enabled and reward_after + SETTINGS.reasoning_backtrack_delta < reward_before:
            restore_snapshot(state, snap)
            rewards.pop()
            trace.append(
                {
                    "step": step_idx,
                    "thought": thought,
                    "action": action,
                    "observation": "backtracked_low_reward",
                    "reward_before": reward_before,
                    "reward_after": reward_after,
                }
            )
            _persist_reasoning_step(
                state,
                {
                    "step": step_idx,
                    "action": action,
                    "event": "backtrack",
                    "reward_before": reward_before,
                    "reward_after": reward_after,
                },
            )
            continue

        executed_tools.add(action)
        observation = {"ok": dumped.get("ok"), "tool_name": dumped.get("tool_name"), "data": dumped.get("data")}
        trace.append(
            {
                "step": step_idx,
                "thought": thought,
                "action": action,
                "observation": _truncate_obs(observation),
                "detected_actions": detected_actions,
                "llm_action_raw": raw_llm_action,
            }
        )
        md["last_reward"] = reward_after
        _persist_reasoning_step(
            state,
            {
                "step": step_idx,
                "thought": thought,
                "action": action,
                "reward": reward_after,
                "markov_phase": md.get("markov_phase"),
            },
        )

    if not tool_buf and not state.get("tool_plan"):
        fb_route = detect_route(query)
        plan = static_tool_plan_for_route(fb_route, query)
        react_parts: list[dict[str, Any]] = []
        for i, pc in enumerate(plan):
            pname = str(pc.get("tool_name", ""))
            if not _policy_allows_action(pname, policy):
                continue
            pq = str((pc.get("payload") or {}).get("query", query))
            defer = pname == "recipe_compute" and _requires_recipe_hitl(pq)
            react_parts.append(
                {
                    "step": i,
                    "thought": "deterministic_fallback",
                    "action": pname,
                    "defer_hitl": defer,
                }
            )
            if defer:
                state["tool_plan"] = [{"tool_name": "recipe_compute", "critical": True, "payload": {"query": pq}}]
                break
            dumped = _execute_tool(state, pname, pq)
            observation = {"ok": dumped.get("ok"), "tool_name": pname, "data": dumped.get("data")}
            react_parts[-1]["observation"] = _truncate_obs(observation)
            tool_buf.append(dumped)
        trace.extend(react_parts)

    state["react_trace"] = trace
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(
        "ReAct orchestrator finished run_id=%s steps=%s defer_hitl=%s",
        state.get("run_id", ""),
        len(trace),
        bool(state.get("tool_plan")),
    )
    return state
