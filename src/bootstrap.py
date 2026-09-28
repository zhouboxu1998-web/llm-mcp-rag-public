from __future__ import annotations

from .agent import Agent
from .config import Settings, load_mcp_server_configs
from .embeddings import EmbeddingClient
from .knowledge_retriever import KnowledgeRetriever
from .llm import LLMClient
from .mcp_client import MCPClient
from .mcp_registry import MCPRegistry
from .query_understanding import QueryUnderstanding
from .tool_retriever import ToolRetriever


class Application:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
        self.query_llm = self.llm
        self.embedding_client = EmbeddingClient(
            settings.embedding_api_key,
            settings.embedding_base_url,
            settings.embedding_model,
        )
        self.knowledge_retriever = KnowledgeRetriever(settings.knowledge_dir, self.embedding_client, settings.data_dir)
        self.tool_retriever = ToolRetriever(self.embedding_client, settings.data_dir)
        self.mcp_registry: MCPRegistry | None = None
        self.agent: Agent | None = None

    async def startup(self) -> None:
        try:
            self.settings.data_dir.mkdir(parents=True, exist_ok=True)
            configs = load_mcp_server_configs(self.settings)
            clients = [MCPClient(name=item["name"], command=item["command"], args=item.get("args", []), env=item.get("env"), required=item.get("required", True)) for item in configs]
            self.mcp_registry = MCPRegistry(clients)
            bindings = await self.mcp_registry.connect_all()
            await self.knowledge_retriever.build()
            await self.tool_retriever.build(bindings)

            query_understanding = QueryUnderstanding(
                self.query_llm,
                enabled=self.settings.query_understanding_enabled,
                model=self.settings.query_understanding_model,
            )
            self.agent = Agent(
                llm=self.llm,
                query_understanding=query_understanding,
                knowledge_retriever=self.knowledge_retriever,
                tool_retriever=self.tool_retriever,
                mcp_registry=self.mcp_registry,
                top_k_documents=self.settings.top_k_documents,
                top_k_tools=self.settings.top_k_tools,
                document_min_score=self.settings.document_min_score,
                tool_min_score=self.settings.tool_min_score,
                max_tool_rounds=self.settings.max_tool_rounds,
            )
        except Exception:
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        if self.mcp_registry is not None:
            await self.mcp_registry.close_all()
        await self.embedding_client.close()
        await self.llm.close()

    async def invoke(self, prompt: str):
        if self.agent is None:
            raise RuntimeError("Application not started")
        return await self.agent.invoke(prompt)
