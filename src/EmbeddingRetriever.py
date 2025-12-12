import json
import os

from dotenv import load_dotenv
from openai import OpenAI, embeddings

from Util import console
from VectorStore import VectorStore, VectorStoreItem

load_dotenv()

class EmbeddingRetriever:
    def __init__(self, model: str):
        self.model = model
        self.vector_store = VectorStore()

    async def embedQuery(self, query: str) -> list[float]:
        """Embed a query string into a vector"""
        embedding = await self.embed(query)
        return embedding

    async def embedDocuments(self, documents: str) -> list[float]:
        """Embed a list of documents into vectors"""
        embedding = await self.embed(documents)
        await self.vector_store.add(VectorStoreItem
                                    (embedding=embedding,
                                     document=documents))
        return embedding

    async def embed(self, document: str) -> list[float]:
        client = OpenAI(
            base_url=os.getenv("EMBEDDING_BASE_URL"),
            api_key=os.getenv("EMBEDDING_KEY"),  # ModelScope Token
        )
        response = client.embeddings.create(
            model=self.model,  # ModelScope Model-Id, required
            input=document,
            encoding_format="float"
        )
        data = response.model_dump_json()
        data = json.loads(data)
        console.log(data)
        return data["data"][0]["embedding"]

    async def retrieve(self, query: str, k: int = 5) -> list[VectorStoreItem]:
        """Retrieve the most similar documents to the query"""
        query_embedding = await self.embedQuery(query)
        return await self.vector_store.search(query_embedding, k)
