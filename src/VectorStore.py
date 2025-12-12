import numpy as np
from matplotlib.mlab import magnitude_spectrum
from seaborn.external.husl import dot_product


class VectorStoreItem:
    def __init__(self, embedding: list[float], document: str):
        self.embedding = embedding
        self.document = document

class VectorStore:
    def __init__(self):
        self.items = []

    async def add(self, item: VectorStoreItem):
        self.items.append(item)

    async def search(self, query_embedding: list[float], k: int = 5):
        """Search for the most similar documents to the query
        """
        scored = []
        for item in self.items:
            similarity = self.similarity(query_embedding, item.embedding)
            scored.append({"document": item.document, "score": similarity})
            return sorted(scored, key=lambda x: x["score"], reverse=True)[:k]

    def similarity(self, query_embedding: list[float], item_embedding: list[float]):
        """Calculate the similarity between two embeddings
        """
        dot_product = np.dot(query_embedding, item_embedding)
        norm_vec1 = np.linalg.norm(query_embedding)
        norm_vec2 = np.linalg.norm(item_embedding)
        return dot_product / (norm_vec1 * norm_vec2)