import logging

from app.db.cosmos import _is_enabled
from app.repositories.document_repository import DocumentRepository
from app.services.document_cleanup_service import delete_document_completely

logger = logging.getLogger(__name__)

document_repo = DocumentRepository()


def cleanup_expired_documents() -> int:
    """Delete guest documents past their TTL (files, chunks, metadata)."""
    if not _is_enabled():
        return 0

    expired = document_repo.list_expired()
    cleaned = 0
    for metadata in expired:
        owner_user_id = metadata.get("owner_user_id", "")
        if not owner_user_id:
            continue
        delete_document_completely(owner_user_id, metadata)
        cleaned += 1
        logger.info(
            "Expired document %s for owner %s",
            metadata.get("document_id") or metadata.get("id"),
            owner_user_id,
        )
    return cleaned
