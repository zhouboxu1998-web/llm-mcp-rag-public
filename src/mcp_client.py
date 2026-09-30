# mcp_client.py
from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .models import ToolBinding


class MCPClient:
    """MCP client using the low-level ClientSession, which performs the
    standard `initialize` handshake and does not send `server/discover`."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        required: bool = True,
    ) -> None:
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.required = required
        self.exit_stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.tools: list[ToolBinding] = []

    async def connect(self) -> list[ToolBinding]:
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
        )
        read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self.session = session

        response = await session.list_tools()
        self.tools = [
            ToolBinding(
                server_name=self.name,
                tool_name=tool.name,
                description=tool.description or "",
                input_schema=tool.input_schema,
            )
            for tool in response.tools
        ]
        return self.tools

    async def call_tool(self, binding: ToolBinding, arguments: dict[str, Any]) -> Any:
        if self.session is None:
            raise RuntimeError(f"MCP client '{self.name}' is not connected")
        if binding.server_name != self.name:
            raise ValueError("Tool binding belongs to another MCP server")
        return await self.session.call_tool(binding.tool_name, arguments)

    async def close(self) -> None:
        await self.exit_stack.aclose()
        self.session = None