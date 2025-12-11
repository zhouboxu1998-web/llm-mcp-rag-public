import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

class MCPClient:
    def __init__(self, name: str, command: str, args: list[str]):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.name = name
        self.command = command
        self.args = args
        self.tools = []
    # methods will go here

    async def close(self):
        await self.exit_stack.aclose()

    async def init(self):
        await self.connect_to_server()

    def get_tools(self):
        """Get tools from the server
        """
        return self.tools

    async def call_tool(self, tool_name: str, tool_args: dict):
        """Call a tool on the server
        """
        return await self.session.call_tool(tool_name, tool_args)

    async def connect_to_server(self):
        """Connect to an MCP server
        """
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()

        tools = response.tools
        for tool in tools:
            self.tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema
            })
        print("\nConnected to server with tools:", [tool.name for tool in tools])

if __name__ == "__main__":
    async def main():
        client = MCPClient(name="fetch", command="uvx", args=["mcp-server-fetch"])
        await client.init()
        tools = client.get_tools()
        print(tools)
        await client.close()

    asyncio.run(main())