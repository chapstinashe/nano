import logging

from flask import Blueprint, jsonify, request

from app.core.audit import audit_action, audit_failure
from app.core.auth import auth_required, get_current_user_context, require_guest_session
from app.core.config import Config
from app.core.errors import GENERIC_500
from app.core.rate_limit import limiter
from app.services.retrieval_service import RetrievalService
from app.utils.owner_documents import resolve_document_ids
from app.utils.validators import validate_query, validate_top_k

logger = logging.getLogger(__name__)
bp = Blueprint("search", __name__, url_prefix="/api/search")
retrieval_service = RetrievalService()


@bp.route("", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_SEARCH)
@auth_required(optional=True)
def search():
    user = get_current_user_context()
    if not user.get("is_authenticated"):
        return jsonify({"error": "Guest search uses locally stored embeddings in the browser"}), 403

    try:
        require_guest_session(user)
    except ValueError as exc:
        audit_failure("search.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    data = request.get_json(silent=True) or {}
    try:
        query = validate_query(data.get("query", ""))
        top_k = validate_top_k(int(data.get("top_k", Config.DEFAULT_TOP_K)))
        document_ids = resolve_document_ids(user["user_id"], data.get("document_ids"))
    except (ValueError, TypeError) as exc:
        audit_failure("search.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    try:
        results = retrieval_service.search(
            query=query,
            owner_user_id=user["user_id"],
            top_k=top_k,
            document_ids=document_ids,
        )
        audit_action(
            "search.success",
            user,
            category="ai",
            query_length=len(query),
            query_preview=query[:120],
            top_k=top_k,
            result_count=len(results),
            document_count=len(document_ids) if document_ids else 0,
        )
        return jsonify(
            {
                "query": query,
                "results": [
                    {
                        "id": r.id,
                        "text": r.text,
                        "score": r.score,
                        "metadata": r.metadata,
                    }
                    for r in results
                ],
            }
        )
    except Exception:
        logger.exception("Search failed")
        audit_failure(
            "search.error",
            category="ai",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
            query_length=len(query),
        )
        return jsonify({"error": GENERIC_500}), 500
