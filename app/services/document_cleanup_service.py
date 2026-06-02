import logging

from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.rag.vector_store import delete_all_for_owner, delete_documents
from app.repositories.preferences_repository import PreferencesRepository
from app.utils.text_storage import delete_extracted_text
from app.utils.upload_storage import delete_user_upload

logger = logging.getLogger(__name__)

document_repo = DocumentRepository()
chat_repo = ChatRepository()
preferences_repo = PreferencesRepository()


def delete_document_completely(owner_user_id: str, metadata: dict) -> int:
    document_id = metadata.get("document_id") or metadata.get("id", "")
    if not document_id:
        return 0

    deleted_chunks = delete_documents(document_id, owner_user_id=owner_user_id)
    delete_user_upload(document_id, metadata)
    delete_extracted_text(metadata)
    document_repo.delete(owner_user_id=owner_user_id, document_id=document_id)
    logger.info(
        "Deleted document %s for owner %s (%d chunks)",
        document_id,
        owner_user_id,
        deleted_chunks,
    )
    return deleted_chunks


def purge_owner_data(owner_user_id: str) -> dict[str, int]:
    """Remove all Cosmos + Blob data for a user or guest session (including vector chunks)."""
    documents = document_repo.list_by_owner(owner_user_id)
    deleted_chunks = 0
    deleted_documents = 0

    for metadata in documents:
        deleted_chunks += delete_document_completely(owner_user_id, metadata)
        deleted_documents += 1

    remaining_chunks = delete_all_for_owner(owner_user_id)
    deleted_chunks += remaining_chunks

    chats = chat_repo.list_by_owner(owner_user_id)
    deleted_chats = 0
    for chat in chats:
        chat_id = chat.get("id")
        if chat_id:
            chat_repo.delete_chat(owner_user_id, chat_id)
            deleted_chats += 1

    try:
        preferences_repo.container.delete_item(
            item=PreferencesRepository.PREFERENCES_ID,
            partition_key=owner_user_id,
        )
    except Exception:
        pass

    logger.info(
        "Purged owner %s: %d documents, %d vector chunks, %d chats",
        owner_user_id,
        deleted_documents,
        deleted_chunks,
        deleted_chats,
    )
    return {
        "deleted_documents": deleted_documents,
        "deleted_chunks": deleted_chunks,
        "deleted_chats": deleted_chats,
    }
