from __future__ import annotations

from typing import Any

from harness_backend.core.state import HarnessState


def snapshot_branch(state: HarnessState, action: str) -> dict[str, Any]:
    """Point de restauration minimal pour backtracking sur une décision d'outil."""
    return {
        "action": action,
        "tool_results_len": len(state.get("tool_results") or []),
        "react_trace_len": len(state.get("react_trace") or []),
    }


def restore_snapshot(state: HarnessState, snap: dict[str, Any]) -> None:
    """Tronque les listes en place pour conserver les références utilisées par l'orchestrateur."""
    tl = int(snap.get("tool_results_len", 0))
    rl = int(snap.get("react_trace_len", 0))
    tr = state.get("tool_results")
    if isinstance(tr, list) and len(tr) > tl:
        del tr[tl:]
    rr = state.get("react_trace")
    if isinstance(rr, list) and len(rr) > rl:
        del rr[rl:]
