import asyncio
import os

from dotenv import load_dotenv

from Agent import Agent
from EmbeddingRetriever import EmbeddingRetriever
from MCPClient import MCPClient
from Util import console, logTitle

if __name__ == "__main__":
    load_dotenv()
    current_dir = os.getcwd()
    knowledge_dir = os.path.join(current_dir, "knowledge")

    async def main():
        prompt = f"请根据Bret的基本信息创作一个关于他的故事，并保存到{knowledge_dir}/Bret.md文件中，要包含他的基本信息和故事"
        context = await retrieveContext(prompt)
        file_mcp = MCPClient(name="file", command="npx", args=["-y",
        "@modelcontextprotocol/server-filesystem", current_dir])
        fetch_mcp = MCPClient(name="fetch", command="uvx", args=["mcp-server-fetch"])
        agent = Agent(mcp_client=[file_mcp, fetch_mcp], model="deepseek-chat", context=context)
        await agent.init()
        res = await agent.invoke(prompt=prompt)
        print(res)
        await agent.close()

    async def retrieveContext(query: str):
        """Retrieve the most similar documents to the query"""
        embedding_retriever = EmbeddingRetriever(model=os.getenv("EMBEDDING_MODEL_NAME"))

        for file in os.listdir(knowledge_dir):
            with open(os.path.join(knowledge_dir, file), "r", encoding="utf-8") as f:
                document = f.read()
                await embedding_retriever.embedDocuments(document)
        context = await embedding_retriever.retrieve(query)
        context = "\n".join([item["document"] for item in context])
        logTitle("RETRIEVE CONTEXT")
        console.log("Retrieved context:", context)
        return context
    asyncio.run(main())
