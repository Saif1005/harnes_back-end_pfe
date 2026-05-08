from __future__ import annotations

from typing import Callable

from harness_backend.config.settings import SETTINGS
from harness_backend.services.mcp_sdk import call_mcp_http, call_mcp_sdk, load_mcp_sdk
from harness_backend.tools.contracts import McpEnvelope, ToolResult


class MCPBridge:
    """
    In-process MCP-like bridge.
    Keeps communication between agent decisions and tool execution structured.
    """

    def __init__(self, tool_dispatcher: Callable[[McpEnvelope], ToolResult]) -> None:
        self.tool_dispatcher = tool_dispatcher
        self.mcp_module, self.mcp_version = load_mcp_sdk()

    def send(self, envelope: McpEnvelope) -> ToolResult:
        if SETTINGS.mcp_enabled:
            remote = self._send_to_remote_mcp(envelope)
            if remote is not None:
                return remote
        return self.tool_dispatcher(envelope)

    def _send_to_remote_mcp(self, envelope: McpEnvelope) -> ToolResult | None:
        payload = envelope.model_dump()
        data = None
        transport = str(SETTINGS.mcp_transport).lower().strip()
        if transport in {"auto", "sdk"} and self.mcp_module is not None:
            data = call_mcp_sdk(
                mcp_module=self.mcp_module,
                server_name=SETTINGS.mcp_server_name,
                tool_name=str(envelope.target_tool),
                payload=payload,
            )
        if data is None and transport in {"auto", "http"}:
            data = call_mcp_http(server_url=SETTINGS.mcp_server_url, payload=payload, timeout_s=20.0)
        if not isinstance(data, dict):
            return None
        return ToolResult(
            tool_name=str(data.get("tool_name", envelope.target_tool)),
            ok=bool(data.get("ok", False)),
            model=str(data.get("model", "")),
            data=dict(data.get("data", {})),
            error=str(data.get("error", "")),
        )

