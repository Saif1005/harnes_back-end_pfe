from __future__ import annotations

import json
import urllib.request
from typing import Callable

from harness_backend.config.settings import SETTINGS
from harness_backend.tools.contracts import McpEnvelope, ToolResult


class MCPBridge:
    """
    In-process MCP-like bridge.
    Keeps communication between agent decisions and tool execution structured.
    """

    def __init__(self, tool_dispatcher: Callable[[McpEnvelope], ToolResult]) -> None:
        self.tool_dispatcher = tool_dispatcher

    def send(self, envelope: McpEnvelope) -> ToolResult:
        if SETTINGS.mcp_enabled:
            remote = self._send_to_remote_mcp(envelope)
            if remote is not None:
                return remote
        return self.tool_dispatcher(envelope)

    def _send_to_remote_mcp(self, envelope: McpEnvelope) -> ToolResult | None:
        payload = envelope.model_dump()
        req = urllib.request.Request(
            url=SETTINGS.mcp_server_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20.0) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            return ToolResult(
                tool_name=str(data.get("tool_name", envelope.target_tool)),
                ok=bool(data.get("ok", False)),
                model=str(data.get("model", "")),
                data=dict(data.get("data", {})),
                error=str(data.get("error", "")),
            )
        except Exception:
            return None

