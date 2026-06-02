import logging
from typing import Any, Optional

from app.repositories.vector_repository import VectorRepository
from app.utils.guest_guard import assert_not_guest_persist

logger = logging.getLogger(__name__)

_repo = VectorRepository()


def add_documents(
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict[str, Any]],
) -> None:
    for metadata in metadatas:
        assert_not_guest_persist(metadata.get("owner_user_id", ""), resource="embeddings")
    _repo.add_documents(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def search_similar(
    query_embedding: list[float],
    top_k: int = 5,
    where: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return _repo.search_similar(query_embedding=query_embedding, top_k=top_k, where=where)


def delete_documents(document_id: str, owner_user_id: str | None = None) -> int:
    return _repo.delete_documents(document_id=document_id, owner_user_id=owner_user_id)


def delete_all_for_owner(owner_user_id: str) -> int:
    return _repo.delete_all_for_owner(owner_user_id)


def list_document_ids(owner_user_id: str | None = None) -> list[str]:
    return _repo.list_document_ids(owner_user_id)


def count_chunks(document_id: Optional[str] = None, owner_user_id: str | None = None) -> int:
    return _repo.count_chunks(document_id=document_id, owner_user_id=owner_user_id)
