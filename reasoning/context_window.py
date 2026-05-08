from __future__ import annotations

import json
from typing import Any

from harness_backend.config.settings import SETTINGS


def compress_trace_for_prompt(trace: list[dict[str, Any]], max_chars: int | None = None) -> list[dict[str, Any]]:
    """
    Réduit la trace ReAct / CoT pour tenir dans la fenêtre de contexte du LLM orchestrateur.
    Garde les N dernières étapes et tronque les champs longs (observation, pensée).
    """
    limit = int(max_chars if max_chars is not None else SETTINGS.reasoning_context_max_chars)
    per_obs = min(400, max(120, limit // 20))
    per_thought = min(320, max(80, limit // 24))
    raw = trace[-12:] if len(trace) > 12 else list(trace)
    out: list[dict[str, Any]] = []
    for row in raw:
        item = {
            "step": row.get("step"),
            "action": row.get("action"),
            "thought": _clip(str(row.get("thought", "")), per_thought),
            "observation": _clip_obs(row.get("observation"), per_obs),
        }
        out.append(item)
    while _json_len(out) > limit and len(out) > 1:
        out = out[1:]
    return out


def _clip(text: str, max_len: int) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _clip_obs(obs: Any, max_len: int) -> str:
    if obs is None:
        return ""
    if isinstance(obs, str):
        return _clip(obs, max_len)
    try:
        s = json.dumps(obs, ensure_ascii=True, default=str)
    except Exception:  # noqa: BLE001
        s = str(obs)
    return _clip(s, max_len)


def _json_len(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=True, default=str))
    except Exception:  # noqa: BLE001
        return len(str(obj))
