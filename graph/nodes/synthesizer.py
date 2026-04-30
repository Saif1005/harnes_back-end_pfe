from __future__ import annotations

from datetime import datetime, timezone

from harness_backend.core.state import HarnessState
from harness_backend.services.legacy_compat import build_stock_alerts, estimate_production_capacity, format_recipe_table


def node_synthesizer(state: HarnessState) -> HarnessState:
    if state.get("route") == "error":
        state["output_message"] = "Execution failed. Check errors."
    elif state.get("hitl_required"):
        state["output_message"] = "Approval required before executing critical action."
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
        tonnage = float(recipe_data.get("tonnage", 1.0) or 1.0)

        text_parts = [f"Harness route executed: {route}. Tools: {', '.join(used)}"]
        if recipe_items:
            text_parts.append("")
            text_parts.append(format_recipe_table(recipe_items))
            alerts = build_stock_alerts(recipe_items, inventory_map)
            if alerts:
                text_parts.append("")
                text_parts.append("Alertes stock:")
                for alert in alerts[:20]:
                    text_parts.append(
                        f"- {alert['ingredient']}: requis={alert['required_kg']:.2f} kg, "
                        f"disponible={alert['available_kg']:.2f} kg, manquant={alert['missing_kg']:.2f} kg"
                    )
            capacity = estimate_production_capacity(recipe_items, inventory_map, tonnage)
            if capacity:
                text_parts.append("")
                text_parts.append(
                    "Capacite estimee: "
                    f"{capacity.get('max_producible_tonnage', 0.0):.3f} t, "
                    f"ingredient limitant={capacity.get('limiting_ingredient', '-')}, "
                    f"ordres complets={capacity.get('full_orders_possible', 0)}"
                )
            state.setdefault("metadata", {})["stock_alerts"] = alerts
            state["metadata"]["production_capacity"] = capacity

        state["output_message"] = "\n".join(text_parts)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return state

