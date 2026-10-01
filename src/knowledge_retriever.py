from __future__ import annotations

import hashlib
import sys
import json
from pathlib import Path

from .embeddings import EmbeddingClient
from .models import VectorHit
from .vector_store import VectorStore


class KnowledgeRetriever:
    def __init__(self, knowledge_dir: Path, embedding_client: EmbeddingClient, cache_dir: Path) -> None:
        self.knowledge_dir = knowledge_dir
        self.embedding_client = embedding_client
        self.cache_dir = cache_dir
        self.store = VectorStore()
        self.index_path = cache_dir / "knowledge.index.json"
        self.manifest_path = cache_dir / "knowledge.manifest.json"

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 1400, overlap: int = 180) -> list[str]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip()
            if current and len(candidate) > chunk_size:
                chunks.append(current)
                tail = current[-overlap:] if overlap > 0 else ""
                current = f"{tail}\n\n{paragraph}".strip()
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _manifest(self) -> str:
        files = []
        if self.knowledge_dir.exists():
            for path in sorted(self.knowledge_dir.rglob("*.md")):
                stat = path.stat()
                files.append({"path": str(path.relative_to(self.knowledge_dir)), "mtime_ns": stat.st_mtime_ns, "size": stat.st_size})
        payload = {"embedding_model": self.embedding_client.model, "files": files}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _try_load_cache(self) -> bool:
        if not self.index_path.exists() or not self.manifest_path.exists():
            return False
        expected = self._manifest()
        actual = self.manifest_path.read_text(encoding="utf-8").strip()
        if expected != actual:
            return False
        self.store.load(self.index_path)
        return True

    async def build(self) -> int:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self._try_load_cache():
            return len(self.store)

        self.store.clear()
        if not self.knowledge_dir.exists():
            print(f"[WARNING] 知识库目录不存在，已创建空目录：{self.knowledge_dir}（检查 .env 里的 KNOWLEDGE_DIR）", file=sys.stderr)
            self.knowledge_dir.mkdir(parents=True, exist_ok=True)
            return 0

        texts: list[str] = []
        metadata: list[dict] = []
        for path in sorted(self.knowledge_dir.rglob("*.md")):
            raw = path.read_text(encoding="utf-8")
            for index, chunk in enumerate(self._chunk_text(raw)):
                texts.append(chunk)
                metadata.append({"source": str(path), "chunk": index})

        if not texts:
            print(f"[WARNING] 知识库目录下没有 .md 文件：{self.knowledge_dir}", file=sys.stderr)
        embeddings = await self.embedding_client.embed_many(texts)
        for index, (text, embedding, meta) in enumerate(zip(texts, embeddings, metadata, strict=True)):
            digest = hashlib.sha1(f"{meta['source']}::{meta['chunk']}".encode()).hexdigest()[:16]
            self.store.add(digest, text, embedding, meta)

        self.store.save(self.index_path)
        self.manifest_path.write_text(self._manifest(), encoding="utf-8")
        return len(texts)

    async def retrieve(self, query: str, k: int, min_score: float) -> list[VectorHit]:
        query_embedding = await self.embedding_client.embed(query)
        return self.store.search(query_embedding, k=k, min_score=min_score)
