import logging
from typing import Optional
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import Config

logger = logging.getLogger(__name__)

_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", Config.EMBEDDING_MODEL)
        _model = SentenceTransformer(Config.EMBEDDING_MODEL)
    return _model


@lru_cache(maxsize=256)
def _embed_text_cached(text: str) -> tuple[float, ...]:
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
    return tuple(embedding.tolist())


def embed_text(text: str) -> list[float]:
    return list(_embed_text_cached(text.strip()))


def embed_documents(chunks: list[str]) -> list[list[float]]:
    if not chunks:
        return []
    model = get_embedding_model()
    embeddings = model.encode(chunks, convert_to_numpy=True, show_progress_bar=False)
    return embeddings.tolist()
