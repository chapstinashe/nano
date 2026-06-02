"""Retriever facade — delegates to the retrieval engine."""

from typing import Optional

from app.models.schemas import SearchResult
from app.rag.retrieval_engine import retrieve


def retrieve_context(
    query: str,
    owner_user_id: str,
    top_k: int = 5,
    document_ids: Optional[list[str]] = None,
) -> list[SearchResult]:
    return retrieve(
        query=query,
        owner_user_id=owner_user_id,
        top_k=top_k,
        document_ids=document_ids,
    )
