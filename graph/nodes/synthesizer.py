from __future__ import annotations

from datetime import datetime, timezone

from harness_backend.core.state import HarnessState
from harness_backend.services.legacy_compat import build_stock_alerts, estimate_production_capacity, format_recipe_table


def node_synthesizer(state: HarnessState) -> HarnessState:
    if state.get("route") == "error":
        state["output_message"] = "Execution failed. Check errors."
    elif state.get("hitl_required"):
        pending_lines = ["Approval required before executing critical action."]
        rt = state.get("react_trace") or []
        if rt:
            pending_lines.append("")
            pending_lines.append(f"Étapes ReAct avant blocage approb.: {len(rt)}")
            last = rt[-1]
            th = str(last.get("thought", "")).strip().replace("\n", " ")
            if len(th) > 200:
                th = th[:200] + "…"
            if th:
                pending_lines.append(f"Dernière intention: {th}")
        state["output_message"] = "\n".join(pending_lines)
    else:
        route = state.get("route", "unknown")
        tool_results = state.get("tool_results", [])
        used = [r.get("tool_name", "") for r in tool_results]

        recipe_data = {}
        stock_data = {}
        for result in tool_results:
            if result.get("tool_name") == "recipe_compute" and bool(result.get("ok")):
                recipe_data = dict(result.get("data") or {})
            if result.get("tool_name") == "stock_check" and bool(result.get("ok")):
                stock_data = dict(result.get("data") or {})

        recipe_items = list(recipe_data.get("recipe_items") or [])
        inventory_map = dict(stock_data.get("inventory_map") or {})
        inventory_displays = dict(stock_data.get("inventory_displays") or {})
        inventory_labels = dict(stock_data.get("inventory_labels") or {})
        tonnage = float(recipe_data.get("tonnage", 1.0) or 1.0)
        prediction_data = {}
        for result in tool_results:
            if result.get("tool_name") == "prediction_regression" and bool(result.get("ok")):
                prediction_data = dict(result.get("data") or {})
                break

        text_parts = [
            "## Execution Overview",
            f"- Route: `{route}`",
            f"- Mode: `{state.get('metadata', {}).get('orchestration_mode', 'pipeline')}`",
            f"- Tools executed: {', '.join(used) if used else 'none'}",
        ]
        react_steps = state.get("react_trace") or []
        if react_steps:
            text_parts.append("")
            text_parts.append("## ReAct Trace")
            text_parts.append(f"- Steps: {len(react_steps)}")
            for row in react_steps[:10]:
                th = str(row.get("thought", "")).strip().replace("\n", " ")
                if len(th) > 140:
                    th = th[:140] + "…"
                obs = row.get("observation", "")
                if isinstance(obs, str) and len(obs) > 160:
                    obs = obs[:160] + "…"
                elif not isinstance(obs, str):
                    obs = str(obs)[:160]
                text_parts.append(
                    f"- `{row.get('action','?')}` | thought: {th or '-'}"
                    f"{' | observation: ' + obs if obs else ''}"
                )
        if recipe_items:
            text_parts.append("")
            text_parts.append("## Recipe Output")
            text_parts.append(
                f"- Engine: `{recipe_data.get('recipe_engine', 'unknown')}` | Source: `{recipe_data.get('source', 'unknown')}`"
            )
            text_parts.append(
                f"- Article: `{recipe_data.get('article', '-')}` | Tonnage: `{tonnage}` | Items: `{len(recipe_items)}`"
            )
            text_parts.append("")
            text_parts.append(format_recipe_table(recipe_items))
            alerts = build_stock_alerts(recipe_items, inventory_map, inventory_displays, inventory_labels)
            if alerts:
                text_parts.append("")
                text_parts.append("## Stock Alerts")
                for alert in alerts[:20]:
                    text_parts.append(
                        f"- `{alert['ingredient']}`: required={alert['required_kg']:.2f} kg, "
                        f"available={alert['available_kg']:.2f} kg, missing={alert['missing_kg']:.2f} kg"
                    )
            capacity = estimate_production_capacity(
                recipe_items, inventory_map, tonnage, inventory_displays, inventory_labels
            )
            if capacity:
                text_parts.append("")
                text_parts.append("## Capacity Estimate")
                text_parts.append(f"- Max producible: `{capacity.get('max_producible_tonnage', 0.0):.3f} t`")
                text_parts.append(f"- Limiting ingredient: `{capacity.get('limiting_ingredient', '-')}`")
                text_parts.append(f"- Full orders possible: `{capacity.get('full_orders_possible', 0)}`")
            state.setdefault("metadata", {})["stock_alerts"] = alerts
            state["metadata"]["production_capacity"] = capacity
        if prediction_data:
            forecast = dict(prediction_data.get("forecast_next_kg") or {})
            if forecast:
                text_parts.append("")
                text_parts.append("## Prediction Update")
                for fam in ("MP", "CHIMIE", "PDR"):
                    if fam in forecast:
                        text_parts.append(f"- `{fam}` next forecast: `{float(forecast[fam]):.3f}`")

        state["output_message"] = "\n".join(text_parts)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

