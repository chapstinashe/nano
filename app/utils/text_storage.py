from app.db import blob_storage


def save_extracted_text(owner_user_id: str, document_id: str, text: str) -> str:
    blob_storage.require_blob_storage()
    blob_path = blob_storage.build_text_blob_path(owner_user_id, document_id)
    blob_storage.upload_bytes(blob_path, text.encode("utf-8"), content_type="text/plain; charset=utf-8")
    return blob_path


def load_extracted_text(owner_user_id: str, document_id: str, metadata: dict) -> str | None:
    blob_path = metadata.get("text_blob_path") or blob_storage.build_text_blob_path(
        owner_user_id, document_id
    )
    if not blob_storage.is_enabled() or not blob_storage.blob_exists(blob_path):
        return None
    return blob_storage.download_bytes(blob_path).decode("utf-8")


def delete_extracted_text(metadata: dict) -> None:
    blob_path = metadata.get("text_blob_path", "")
    if blob_path and blob_storage.is_enabled():
        blob_storage.delete_blob(blob_path)
