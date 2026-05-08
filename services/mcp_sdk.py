from __future__ import annotations

import importlib
import json
import urllib.request
from typing import Any


def load_mcp_sdk() -> tuple[Any | None, str]:
    """
    Try loading MCP SDK (Anthropic-compatible module name: 'mcp').
    Returns (module_or_none, version_or_status).
    """
    try:
        module = importlib.import_module("mcp")
        version = str(getattr(module, "__version__", "unknown"))
        return module, version
    except Exception as exc:  # noqa: BLE001
        return None, f"not_loaded: {exc}"


def call_mcp_http(server_url: str, payload: dict[str, Any], timeout_s: float = 20.0) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url=server_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def call_mcp_sdk(
    mcp_module: Any,
    server_name: str,
    tool_name: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Best-effort adapter for MCP SDK style clients.
    Supports multiple possible method names to stay compatible with SDK changes.
    """
    try:
        # Pattern 1: module-level helper
        if hasattr(mcp_module, "call_tool"):
            out = mcp_module.call_tool(server_name=server_name, tool_name=tool_name, arguments=payload)
            return out if isinstance(out, dict) else None
        # Pattern 2: client object
        if hasattr(mcp_module, "Client"):
            client = mcp_module.Client(server_name=server_name)
            if hasattr(client, "call_tool"):
                out = client.call_tool(tool_name=tool_name, arguments=payload)
                return out if isinstance(out, dict) else None
            if hasattr(client, "call"):
                out = client.call("tools/call", {"name": tool_name, "arguments": payload})
                return out if isinstance(out, dict) else None
    except Exception:
        return None
    return None

