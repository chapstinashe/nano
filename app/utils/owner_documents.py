from typing import Optional

from app.utils.guest_guard import is_guest_owner


def resolve_document_ids(
    owner_user_id: str,
    document_ids: list | str | None,
    *,
    require_for_guest: bool = True,
) -> list[str] | None:
    """
    Resolve document scope for search/chat (authenticated users only).

    Guest documents and embeddings live in browser IndexedDB and must not use Cosmos.
    """
    if is_guest_owner(owner_user_id):
        raise ValueError(
            "Guest documents and embeddings are stored locally in the browser. "
            "Use client-side retrieval."
        )

    from app.rag.vector_store import list_document_ids
    from app.utils.document_access import validate_document_ids

    if document_ids:
        return validate_document_ids(owner_user_id, document_ids)

    owned = list_document_ids(owner_user_id)
    if not owned:
        return None

    return None
