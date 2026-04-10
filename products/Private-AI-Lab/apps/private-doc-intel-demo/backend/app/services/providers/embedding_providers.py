from __future__ import annotations

from app.core.paths import resolve_embedding_cache_root
from app.core.settings import settings


class EmbeddingProviderUnavailable(RuntimeError):
    pass


class EmbeddingProvider:
    def __init__(self, name: str, mode: str) -> None:
        self.name = name
        self.mode = mode
        self.supports_embeddings = False

    def describe(self) -> dict[str, str]:
        return {"name": self.name, "mode": self.mode}

    def ensure_available(self) -> None:
        return None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderUnavailable(f"{self.name} does not provide embeddings.")

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class FastEmbedLocalProvider(EmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(name="fastembed-local", mode="local")
        self.supports_embeddings = True
        self.model_name = settings.embedding_model_name
        self.cache_root = resolve_embedding_cache_root()
        self._model = None

    def ensure_available(self) -> None:
        if self._model is not None:
            return
        self.cache_root.mkdir(parents=True, exist_ok=True)
        try:
            from fastembed import TextEmbedding
        except Exception as exc:  # pragma: no cover - import failure depends on env
            raise EmbeddingProviderUnavailable(f"fastembed is not available: {exc}") from exc

        try:
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_root),
            )
        except Exception as exc:  # pragma: no cover - model init depends on env
            raise EmbeddingProviderUnavailable(f"embedding model could not be initialized: {exc}") from exc

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.ensure_available()
        try:
            vectors = list(self._model.embed(texts))
        except Exception as exc:  # pragma: no cover - model execution depends on env
            raise EmbeddingProviderUnavailable(f"embedding generation failed: {exc}") from exc
        return [list(map(float, vector.tolist())) for vector in vectors]


class LocalEmbeddingProviderPlaceholder(EmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(name="local-embedding-placeholder", mode="placeholder")


class ApiEmbeddingProviderPlaceholder(EmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(name="api-embedding-placeholder", mode="placeholder")


class LexicalEmbeddingPlaceholder(EmbeddingProvider):
    def __init__(self) -> None:
        super().__init__(name="lexical-placeholder", mode="not-in-use")


def build_embedding_provider(configured_name: str) -> EmbeddingProvider:
    normalized = configured_name.strip().lower()
    if normalized in {"fastembed", "fastembed-local", "local-fastembed"}:
        return FastEmbedLocalProvider()
    if normalized in {"local", "local-placeholder", "mlx-placeholder"}:
        return LocalEmbeddingProviderPlaceholder()
    if normalized in {"api", "api-placeholder", "openai-compatible"}:
        return ApiEmbeddingProviderPlaceholder()
    return LexicalEmbeddingPlaceholder()
