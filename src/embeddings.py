from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI


class EmbeddingClient:
    def __init__(self, api_key: str, base_url: str | None, model: str) -> None:
        from openai import AsyncOpenAI

        self.model = model
        self.client: AsyncOpenAI = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
            encoding_format="float",
        )
        return response.data[0].embedding

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float",
        )
        data = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in data]

    async def close(self) -> None:
        await self.client.close()
