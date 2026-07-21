"""Тонкая обёртка над LiteLLM для эмбеддингов — Voyage AI (адаптировано из NX
core/embeddings/client.py). DedupService зависит от этого интерфейса, а не от
litellm/voyage напрямую.

В отличие от NX, где дедуп был реализован, но не подключён к пайплайну — здесь
он используется на каждом кандидате до рерайта (см. ARCHITECTURE.md §5):
одна и та же вирусная новость почти всегда приходит из нескольких
source_channels одной темы одновременно, и дедуп сворачивает такие дубли
в одного representative ДО того, как на кандидата тратится дорогой LLM-вызов.
"""

from core.config import Settings, get_settings
from core.logging import get_logger
from core.models.candidate_post import EMBEDDING_DIM

logger = get_logger(__name__)

EMBEDDING_MODEL = "voyage/voyage-3"


class EmbeddingsClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        """Дедуп (core/services/dedup.py) и анти-плагиат метрика рерайта
        (core/services/rewrite.py._similarity) не критичны для работы пайплайна
        на малом числе source_channels/при ручном одобрении — обе стороны
        должны сами проверять этот флаг и пропускать шаг, а не падать, если
        Voyage-ключ ещё не заведён."""
        return bool(self.settings.voyage_api_key)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        import litellm

        response = await litellm.aembedding(
            model=EMBEDDING_MODEL,
            input=texts,
            api_key=self.settings.voyage_api_key,
        )
        vectors = [item["embedding"] for item in response.data]
        for vector in vectors:
            assert len(vector) == EMBEDDING_DIM, (
                f"embedding dim {len(vector)} != EMBEDDING_DIM {EMBEDDING_DIM}"
            )

        logger.info("embeddings.computed", model=EMBEDDING_MODEL, count=len(vectors))
        return vectors

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
