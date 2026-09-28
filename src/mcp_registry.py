from __future__ import annotations

from .mcp_client import MCPClient
from .models import ToolBinding


class MCPRegistry:
    def __init__(self, clients: list[MCPClient]) -> None:
        self.clients = clients
        self.bindings: dict[str, ToolBinding] = {}
        self._client_by_server: dict[str, MCPClient] = {}

    async def connect_all(self) -> list[ToolBinding]:
        self.bindings.clear()
        self._client_by_server.clear()
        all_bindings: list[ToolBinding] = []
        for client in self.clients:
            try:
                tools = await client.connect()
            except Exception:
                if client.required:
                    raise
                continue
            self._client_by_server[client.name] = client
            for binding in tools:
                if binding.qualified_name in self.bindings:
                    raise RuntimeError(f"Duplicate qualified tool name: {binding.qualified_name}")
                self.bindings[binding.qualified_name] = binding
                all_bindings.append(binding)
        return all_bindings

    def get(self, qualified_name: str) -> ToolBinding | None:
        return self.bindings.get(qualified_name)

    def client_for(self, binding: ToolBinding) -> MCPClient:
        try:
            return self._client_by_server[binding.server_name]
        except KeyError as exc:
            raise KeyError(f"MCP server not registered: {binding.server_name}") from exc

    async def call(self, qualified_name: str, arguments: dict) -> object:
        binding = self.get(qualified_name)
        if binding is None:
            raise KeyError(f"Unknown tool: {qualified_name}")
        return await self.client_for(binding).call_tool(binding, arguments)

    async def close_all(self) -> None:
        for client in reversed(self.clients):
            await client.close()
