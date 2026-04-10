from __future__ import annotations

from typing import Optional, Sequence

from app.services.providers.embedding_providers import EmbeddingProviderUnavailable
from app.services.repository import DocumentRepository


class RetrievalService:
    def __init__(self, repository: DocumentRepository, embedding_provider) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.backend_name = self._configured_backend_name()

    def index_chunks(self, chunks):
        if not self.embedding_provider.supports_embeddings:
            self.backend_name = self.repository.retrieval_backend
            return chunks

        try:
            vectors = self.embedding_provider.embed_texts([chunk.text for chunk in chunks])
            for chunk, vector in zip(chunks, vectors):
                chunk.embedding = vector
            self.backend_name = self._configured_backend_name()
            return chunks
        except EmbeddingProviderUnavailable:
            self.backend_name = self.repository.retrieval_backend
            return chunks

    def search(self, question: str, document_ids: Optional[Sequence[str]], top_k: int):
        if self.embedding_provider.supports_embeddings:
            try:
                query_embedding = self.embedding_provider.embed_query(question)
                hits = self.repository.search_chunks_by_embedding(query_embedding, document_ids, top_k)
                if hits:
                    self.backend_name = self._configured_backend_name()
                    return hits
            except EmbeddingProviderUnavailable:
                self.backend_name = self.repository.retrieval_backend
        return self.repository.search_chunks(question, document_ids, top_k)

    def _configured_backend_name(self) -> str:
        if self.embedding_provider.supports_embeddings:
            return f"embedding-cosine/{self.embedding_provider.name}"
        return self.repository.retrieval_backend
