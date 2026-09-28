from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .models import VectorHit


class VectorStore:
    """Small dependency-free vector index for a resume-scale project."""

    def __init__(self) -> None:
        self._items: list[tuple[str, str, list[float], dict[str, Any]]] = []

    def add(self, document_id: str, text: str, embedding: list[float], metadata: dict[str, Any] | None = None) -> None:
        self._items.append((document_id, text, embedding, metadata or {}))

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def search(self, query_embedding: list[float], k: int = 5, min_score: float = -1.0) -> list[VectorHit]:
        if not self._items:
            return []

        query = np.asarray(query_embedding, dtype=np.float32)
        hits: list[VectorHit] = []
        for document_id, text, embedding, metadata in self._items:
            score = self._cosine(query, np.asarray(embedding, dtype=np.float32))
            if score >= min_score:
                hits.append(VectorHit(document_id=document_id, text=text, score=score, metadata=metadata))

        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[: max(0, k)]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {"document_id": item[0], "text": item[1], "embedding": item[2], "metadata": item[3]}
            for item in self._items
        ]
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def load(self, path: Path) -> None:
        self.clear()
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload:
            self.add(item["document_id"], item["text"], item["embedding"], item.get("metadata", {}))
