import logging
from typing import Any

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings

from app.core.config import Config

logger = logging.getLogger(__name__)

_service_client: BlobServiceClient | None = None
_container_client: Any | None = None


def is_enabled() -> bool:
    return bool(Config.AZURE_STORAGE_CONNECTION_STRING)


def _safe_path_segment(value: str) -> str:
    return value.replace("\\", "_").replace("/", "_").replace(":", "_")


def build_blob_path(owner_user_id: str, document_id: str, filename: str) -> str:
    safe_filename = filename.replace("\\", "/").split("/")[-1]
    owner = _safe_path_segment(owner_user_id)
    return f"uploads/{owner}/{document_id}_{safe_filename}"


def build_text_blob_path(owner_user_id: str, document_id: str) -> str:
    owner = _safe_path_segment(owner_user_id)
    return f"texts/{owner}/{document_id}.txt"


def require_blob_storage() -> None:
    if not is_enabled():
        raise RuntimeError(
            "Azure Blob Storage is required. Set AZURE_STORAGE_CONNECTION_STRING."
        )


def _get_container_client():
    global _service_client, _container_client
    if not is_enabled():
        raise RuntimeError(
            "Azure Blob Storage is not configured. Set AZURE_STORAGE_CONNECTION_STRING."
        )
    if _container_client is None:
        _service_client = BlobServiceClient.from_connection_string(
            Config.AZURE_STORAGE_CONNECTION_STRING
        )
        _container_client = _service_client.get_container_client(Config.AZURE_STORAGE_CONTAINER)
        if not _container_client.exists():
            _container_client.create_container()
            logger.info("Created blob container: %s", Config.AZURE_STORAGE_CONTAINER)
    return _container_client


def upload_bytes(blob_path: str, data: bytes, content_type: str | None = None) -> str:
    kwargs: dict[str, Any] = {}
    if content_type:
        kwargs["content_settings"] = ContentSettings(content_type=content_type)
    _get_container_client().upload_blob(name=blob_path, data=data, overwrite=True, **kwargs)
    logger.info("Uploaded blob: %s", blob_path)
    return blob_path


def download_bytes(blob_path: str) -> bytes:
    try:
        return _get_container_client().download_blob(blob_path).readall()
    except ResourceNotFoundError as exc:
        raise FileNotFoundError(blob_path) from exc


def delete_blob(blob_path: str) -> None:
    try:
        _get_container_client().delete_blob(blob_path)
        logger.info("Deleted blob: %s", blob_path)
    except ResourceNotFoundError:
        logger.warning("Blob not found during delete: %s", blob_path)


def blob_exists(blob_path: str) -> bool:
    return _get_container_client().get_blob_client(blob_path).exists()
