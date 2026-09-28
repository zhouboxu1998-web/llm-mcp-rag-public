from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .embeddings import EmbeddingClient
from .models import ToolBinding, VectorHit
from .vector_store import VectorStore


class ToolRetriever:
    """Semantic index over MCP tool metadata."""

    def __init__(self, embedding_client: EmbeddingClient, cache_dir: Path) -> None:
        self.embedding_client = embedding_client
        self.cache_dir = cache_dir
        self.store = VectorStore()
        self.bindings: dict[str, ToolBinding] = {}
        self.index_path = cache_dir / "tool.index.json"
        self.manifest_path = cache_dir / "tool.manifest.json"

    @staticmethod
    def _fingerprint(bindings: list[ToolBinding], model: str) -> str:
        payload = {
            "embedding_model": model,
            "tools": [
                {
                    "name": binding.qualified_name,
                    "description": binding.description,
                    "input_schema": binding.input_schema,
                }
                for binding in sorted(bindings, key=lambda item: item.qualified_name)
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    async def build(self, bindings: list[ToolBinding]) -> int:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bindings = {binding.qualified_name: binding for binding in bindings}
        fingerprint = self._fingerprint(bindings, self.embedding_client.model)

        if (
            self.index_path.exists()
            and self.manifest_path.exists()
            and self.manifest_path.read_text(encoding="utf-8").strip() == fingerprint
        ):
            self.store.load(self.index_path)
            return len(bindings)

        self.store.clear()
        texts = [binding.searchable_text for binding in bindings]
        embeddings = await self.embedding_client.embed_many(texts)
        for binding, embedding in zip(bindings, embeddings, strict=True):
            self.store.add(
                document_id=binding.qualified_name,
                text=binding.searchable_text,
                embedding=embedding,
                metadata={"server": binding.server_name, "tool": binding.tool_name},
            )

        self.store.save(self.index_path)
        self.manifest_path.write_text(fingerprint, encoding="utf-8")
        return len(bindings)

    async def retrieve_hits(self, query: str, k: int, min_score: float) -> list[VectorHit]:
        if k <= 0 or not self.store:
            return []
        query_embedding = await self.embedding_client.embed(query)
        return self.store.search(query_embedding, k=k, min_score=min_score)

    async def retrieve(self, query: str, k: int, min_score: float) -> list[ToolBinding]:
        hits = await self.retrieve_hits(query, k, min_score)
        return [self.bindings[hit.document_id] for hit in hits if hit.document_id in self.bindings]
