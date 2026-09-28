from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from mcp import Client, StdioServerParameters

from .models import ToolBinding


class MCPClient:
    """MCP v2 client wrapper with a stable per-server lifecycle."""

    def __init__(self, name: str, command: str, args: list[str], env: dict[str, str] | None = None, required: bool = True) -> None:
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.required = required
        self.exit_stack = AsyncExitStack()
        self.client: Client | None = None
        self.tools: list[ToolBinding] = []

    async def connect(self) -> list[ToolBinding]:
        server_params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
        client = Client(server_params)
        self.client = await self.exit_stack.enter_async_context(client)

        response = await self.client.list_tools()
        self.tools = [
            ToolBinding(
                server_name=self.name,
                tool_name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema,
            )
            for tool in response.tools
        ]
        return self.tools

    async def call_tool(self, binding: ToolBinding, arguments: dict[str, Any]) -> Any:
        if self.client is None:
            raise RuntimeError(f"MCP client '{self.name}' is not connected")
        if binding.server_name != self.name:
            raise ValueError("Tool binding belongs to another MCP server")
        return await self.client.call_tool(binding.tool_name, arguments)

    async def close(self) -> None:
        await self.exit_stack.aclose()
        self.client = None
