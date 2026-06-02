import logging

from flask import Blueprint, jsonify, request

from app.core.audit import audit_action, audit_failure
from app.core.auth import auth_required, get_current_user_context, role_required
from app.core.config import Config
from app.core.db_security import (
    assert_safe_connection_target,
    reject_raw_connection_string,
    validate_db_host,
    validate_db_type,
    validate_table_names,
)
from app.core.errors import GENERIC_500
from app.core.rate_limit import limiter
from app.core.security import validate_uuid
from app.ingestion.database_ingestor import DatabaseIngestor
from app.services.guest_session_service import validate_session_id
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)
bp = Blueprint("ingest", __name__, url_prefix="/api/ingest")
ingestion_service = IngestionService()
db_ingestor = DatabaseIngestor()


@bp.route("/files", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_INGEST_FILE)
@auth_required(optional=True)
def ingest_files():
    user = get_current_user_context()
    if not user["is_authenticated"]:
        audit_failure(
            "ingest.file.rejected",
            category="ingest",
            reason="Guest uploads are stored locally in the browser",
            user_id=user.get("user_id", ""),
        )
        return jsonify({"error": "Guest uploads are stored locally in the browser. Use client-side upload."}), 403

    if "file" not in request.files:
        audit_failure("ingest.file.rejected", category="ingest", reason="No file part", user_id=user.get("user_id", ""))
        return jsonify({"error": "No file part in request. Use 'file' field."}), 400

    file = request.files["file"]
    filename = file.filename or "unknown"
    try:
        metadata = ingestion_service.ingest_file(file, owner_user_id=user["user_id"])
        audit_action(
            "ingest.file.success",
            user,
            category="ingest",
            document_id=metadata.document_id,
            filename=metadata.filename,
            source_type=metadata.source_type,
            chunk_count=metadata.chunk_count,
        )
        return jsonify(
            {
                "document_id": metadata.document_id,
                "filename": metadata.filename,
                "source_type": metadata.source_type,
                "chunk_count": metadata.chunk_count,
                "created_at": metadata.created_at,
            }
        ), 201
    except ValueError as exc:
        message = str(exc)
        audit_failure(
            "ingest.file.failed",
            category="ingest",
            user_id=user.get("user_id", ""),
            reason=message,
            filename=filename,
        )
        if "Daily upload limit" in message:
            return jsonify({"error": message}), 429
        return jsonify({"error": message}), 400
    except Exception:
        logger.exception("File ingestion failed")
        audit_failure(
            "ingest.file.error",
            category="ingest",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
            filename=filename,
        )
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/process", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_INGEST_FILE)
@auth_required(optional=True)
def process_file():
    """Stateless parse/chunk/embed for guest uploads (nothing persisted server-side)."""
    user = get_current_user_context()
    if user["is_authenticated"]:
        return jsonify({"error": "Authenticated users should use /api/ingest/files"}), 403

    try:
        validate_session_id(user.get("session_id", ""))
    except ValueError as exc:
        audit_failure("ingest.process.rejected", category="ingest", reason=str(exc), user_id=user.get("user_id", ""))
        return jsonify({"error": str(exc)}), 400

    if "file" not in request.files:
        audit_failure(
            "ingest.process.rejected",
            category="ingest",
            reason="No file part",
            user_id=user.get("user_id", ""),
        )
        return jsonify({"error": "No file part in request. Use 'file' field."}), 400

    file = request.files["file"]
    filename = file.filename or "unknown"
    try:
        payload = ingestion_service.process_file_for_client(file)
        audit_action(
            "ingest.process.success",
            user,
            category="ingest",
            document_id=payload["document_id"],
            filename=payload["filename"],
            source_type=payload["source_type"],
            chunk_count=payload["chunk_count"],
        )
        return jsonify(payload), 200
    except ValueError as exc:
        audit_failure(
            "ingest.process.failed",
            category="ingest",
            user_id=user.get("user_id", ""),
            reason=str(exc),
            filename=filename,
        )
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Guest file processing failed")
        audit_failure(
            "ingest.process.error",
            category="ingest",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
            filename=filename,
        )
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/database", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_INGEST_DB)
@auth_required()
@role_required("admin")
def ingest_database():
    user = get_current_user_context()
    data = request.get_json(silent=True) or {}
    tables = data.get("tables", [])

    try:
        reject_raw_connection_string(data.get("connection_string", ""))
        db_type = validate_db_type(data.get("db_type", "postgresql"))
        tables = validate_table_names(tables)
        host = validate_db_host(data.get("host", ""))
        connection_string = db_ingestor.build_connection_string(
            db_type=db_type,
            host=host,
            port=int(data.get("port", 0)),
            database=data.get("database", ""),
            username=data.get("username", ""),
            password=data.get("password", ""),
            connection_string="",
        )
        assert_safe_connection_target(host, connection_string)
    except ValueError as exc:
        audit_failure(
            "ingest.database.rejected",
            category="ingest",
            user_id=user.get("user_id", ""),
            reason=str(exc),
        )
        return jsonify({"error": str(exc)}), 400
    except TypeError as exc:
        audit_failure(
            "ingest.database.rejected",
            category="ingest",
            user_id=user.get("user_id", ""),
            reason=str(exc),
        )
        return jsonify({"error": str(exc)}), 400

    try:
        metadata = ingestion_service.ingest_database(
            connection_string=connection_string,
            tables=tables,
            owner_user_id=user["user_id"],
            db_type=db_type,
        )
        audit_action(
            "ingest.database.success",
            user,
            category="ingest",
            document_id=metadata.document_id,
            db_type=db_type,
            tables=tables,
            chunk_count=metadata.chunk_count,
            host=host,
            database=data.get("database", ""),
        )
        return jsonify(
            {
                "document_id": metadata.document_id,
                "filename": metadata.filename,
                "source_type": metadata.source_type,
                "chunk_count": metadata.chunk_count,
                "created_at": metadata.created_at,
                "tables": tables,
            }
        ), 201
    except ValueError as exc:
        audit_failure(
            "ingest.database.failed",
            category="ingest",
            user_id=user.get("user_id", ""),
            reason=str(exc),
            db_type=db_type,
            tables=tables,
        )
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Database ingestion failed")
        audit_failure(
            "ingest.database.error",
            category="ingest",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
            db_type=db_type,
        )
        return jsonify({"error": GENERIC_500}), 500
