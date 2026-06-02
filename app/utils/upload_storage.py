import mimetypes
import os
import tempfile
from typing import Any

from werkzeug.datastructures import FileStorage

from app.db import blob_storage


def save_user_upload(
    file: FileStorage,
    document_id: str,
    filename: str,
    owner_user_id: str,
) -> dict[str, Any]:
    blob_storage.require_blob_storage()
    blob_path = blob_storage.build_blob_path(owner_user_id, document_id, filename)
    file.stream.seek(0)
    data = file.read()
    content_type = mimetypes.guess_type(filename)[0]
    blob_storage.upload_bytes(blob_path, data, content_type=content_type)

    suffix = os.path.splitext(filename)[1]
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)

    return {
        "storage_backend": "blob",
        "blob_path": blob_path,
        "parse_path": temp_path,
        "cleanup_parse_path": True,
    }


def cleanup_parse_path(upload_info: dict[str, Any]) -> None:
    if not upload_info.get("cleanup_parse_path"):
        return
    path = upload_info.get("parse_path", "")
    if path and os.path.isfile(path):
        os.remove(path)


def resolve_upload_path(
    document_id: str,
    filename: str,
    owner_user_id: str,
    metadata: dict[str, Any],
) -> str | None:
    blob_storage.require_blob_storage()
    blob_path = metadata.get("blob_path") or blob_storage.build_blob_path(
        owner_user_id, document_id, filename
    )
    if not blob_storage.blob_exists(blob_path):
        return None
    suffix = os.path.splitext(filename)[1]
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(temp_path, "wb") as handle:
        handle.write(blob_storage.download_bytes(blob_path))
    return temp_path


def delete_user_upload(document_id: str, metadata: dict[str, Any]) -> None:
    blob_path = metadata.get("blob_path")
    if blob_path:
        blob_storage.delete_blob(blob_path)


def download_user_upload(metadata: dict[str, Any]) -> tuple[bytes, str]:
    blob_storage.require_blob_storage()
    filename = metadata.get("filename", "download")
    blob_path = metadata.get("blob_path", "")
    if not blob_path:
        raise FileNotFoundError("Missing blob_path in document metadata")
    return blob_storage.download_bytes(blob_path), filename
