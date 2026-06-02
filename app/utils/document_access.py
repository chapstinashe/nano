from app.db.cosmos import require_cosmos
from app.repositories.document_repository import DocumentRepository

document_repo = DocumentRepository()


def validate_document_ids(owner_user_id: str, document_ids: list | str | None) -> list[str] | None:
    """Ensure every requested document belongs to the current owner (Cosmos DB)."""
    if document_ids is None:
        return None

    if isinstance(document_ids, str):
        document_ids = [document_ids]

    normalized = [str(doc_id).strip() for doc_id in document_ids if str(doc_id).strip()]
    if not normalized:
        return None

    require_cosmos()
    missing: list[str] = []
    for doc_id in normalized:
        if not document_repo.get_by_id(owner_user_id, doc_id):
            missing.append(doc_id)

    if missing:
        raise ValueError(
            "One or more documents are not in your library: " + ", ".join(sorted(missing))
        )
    return normalized
