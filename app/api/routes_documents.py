import logging
import os
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

from app.core.audit import audit_action, audit_failure, log_security_event
from app.core.auth import auth_required, get_current_user_context, require_guest_session
from app.core.config import Config
from app.core.errors import GENERIC_500
from app.core.security import validate_uuid
from app.repositories.document_repository import DocumentRepository
from app.rag.vector_store import count_chunks, list_document_ids
from app.services.document_cleanup_service import delete_document_completely
from app.utils.text_storage import load_extracted_text, save_extracted_text
from app.utils.upload_storage import delete_user_upload, download_user_upload, resolve_upload_path

logger = logging.getLogger(__name__)
bp = Blueprint("documents", __name__, url_prefix="/api/documents")
document_repo = DocumentRepository()


@bp.route("", methods=["GET"])
@auth_required(optional=True)
def list_documents():
    user = get_current_user_context()
    if not user.get("is_authenticated"):
        return jsonify({"documents": []})

    try:
        require_guest_session(user)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    document_ids = list_document_ids(owner_user_id=user["user_id"])
    documents = []
    for doc_id in document_ids:
        meta = _load_metadata(user["user_id"], doc_id)
        documents.append(
            {
                "document_id": doc_id,
                "filename": meta.get("filename", "unknown"),
                "source_type": meta.get("source_type", "unknown"),
                "chunk_count": count_chunks(doc_id, owner_user_id=user["user_id"]),
                "created_at": meta.get("created_at", ""),
                "source": meta.get("source", "file"),
            }
        )
    audit_action(
        "document.list",
        user,
        category="data",
        document_count=len(documents),
    )
    return jsonify({"documents": documents, "count": len(documents)})


@bp.route("/<document_id>/download", methods=["GET"])
@auth_required(optional=True)
def download_document(document_id: str):
    user = get_current_user_context()
    if not user.get("is_authenticated"):
        return jsonify({"error": "Guest documents are stored locally in the browser"}), 403

    try:
        require_guest_session(user)
        document_id = validate_uuid(document_id, field_name="document_id")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    meta = _load_metadata(user["user_id"], document_id)
    if not meta:
        return jsonify({"error": "Document not found"}), 404

    if meta.get("source") == "database":
        return jsonify({"error": "Database-ingested documents cannot be downloaded"}), 400

    try:
        data, filename = download_user_upload(meta)
    except FileNotFoundError:
        return jsonify({"error": "File not found in storage"}), 404

    audit_action(
        "document.download",
        user,
        category="data",
        document_id=document_id,
        filename=meta.get("filename", filename),
        bytes=len(data),
    )
    return send_file(BytesIO(data), as_attachment=True, download_name=filename)


@bp.route("/<document_id>", methods=["DELETE"])
@auth_required(optional=True)
def delete_document(document_id: str):
    user = get_current_user_context()
    if not user.get("is_authenticated"):
        return jsonify({"error": "Guest documents are stored locally in the browser"}), 403

    try:
        require_guest_session(user)
        document_id = validate_uuid(document_id, field_name="document_id")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        meta = _load_metadata(user["user_id"], document_id)
        if not meta:
            return jsonify({"error": "Document not found"}), 404
        deleted_chunks = delete_document_completely(user["user_id"], meta)
        audit_action(
            "document.delete",
            user,
            category="data",
            document_id=document_id,
            filename=meta.get("filename", ""),
            deleted_chunks=deleted_chunks,
        )
        return jsonify(
            {
                "document_id": document_id,
                "deleted_chunks": deleted_chunks,
                "status": "deleted",
            }
        )
    except Exception:
        logger.exception("Document deletion failed")
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/<document_id>/text", methods=["GET"])
@auth_required(optional=True)
def view_document_text(document_id: str):
    """
    Return extracted text with optional highlight window.

    Query params:
      - full: 1/true to return full extracted text
      - start: int (absolute char start in normalized doc text coordinates)
      - end: int (absolute char end in normalized doc text coordinates)
      - window: int (optional, default 900 chars around highlight)
    """
    user = get_current_user_context()
    try:
        require_guest_session(user)
        document_id = validate_uuid(document_id, field_name="document_id")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    meta = _load_metadata(user["user_id"], document_id)
    if not meta:
        return jsonify({"error": "Document not found"}), 404

    if meta.get("source") == "database":
        return jsonify({"error": "Database-ingested documents cannot be viewed as a document"}), 400

    filename = meta.get("filename", "")
    file_path = None
    if filename:
        file_path = resolve_upload_path(document_id, filename, user["user_id"], meta)

    text = load_extracted_text(user["user_id"], document_id, meta)
    if text is None:
        if not file_path:
            return jsonify({"error": "File not found in storage"}), 404

        from app.ingestion.file_ingestor import PARSERS

        source_type = (meta.get("source_type") or "").lower()
        parser = PARSERS.get(source_type)
        if not parser:
            return jsonify({"error": f"Unsupported source type: {source_type}"}), 400
        try:
            text = parser(file_path)
        finally:
            if file_path and os.path.isfile(file_path):
                os.remove(file_path)
        text_blob_path = save_extracted_text(user["user_id"], document_id, text)
        meta["text_blob_path"] = text_blob_path
        document_repo.upsert(meta)

    full = str(request.args.get("full", "")).lower() in {"1", "true", "yes"}

    try:
        start = int(request.args.get("start", "0"))
        end = int(request.args.get("end", str(start)))
        window = int(request.args.get("window", "900"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid start/end/window"}), 400

    if start < 0:
        start = 0
    if end < start:
        end = start
    if window < 200:
        window = 200

    n = len(text)
    start = min(start, n)
    end = min(end, n)

    if full:
        if len(text) > Config.MAX_TEXT_EXPORT_CHARS:
            return jsonify(
                {
                    "error": f"Document exceeds export limit of {Config.MAX_TEXT_EXPORT_CHARS} characters"
                }
            ), 400
        win_start = 0
        win_end = n
        window_text = text
    else:
        win_start = max(0, start - window)
        win_end = min(n, end + window)
        window_text = text[win_start:win_end]

    audit_action(
        "document.text_view",
        user,
        category="data",
        document_id=document_id,
        filename=filename,
        full=full,
        doc_length=n,
        window_start=win_start,
        window_end=win_end,
    )

    return jsonify(
        {
            "document_id": document_id,
            "filename": filename,
            "source_type": meta.get("source_type", ""),
            "text": window_text,
            "window_start": win_start,
            "window_end": win_end,
            "highlight_start": start - win_start,
            "highlight_end": end - win_start,
            "doc_length": n,
        }
    )


def _load_metadata(owner_user_id: str, document_id: str) -> dict:
    return document_repo.get_by_id(owner_user_id, document_id) or {}
