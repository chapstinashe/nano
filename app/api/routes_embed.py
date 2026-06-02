import logging

from flask import Blueprint, jsonify, request

from app.core.audit import audit_action, audit_failure
from app.core.auth import auth_required, get_current_user_context, require_guest_session
from app.core.config import Config
from app.core.errors import GENERIC_500
from app.core.rate_limit import limiter
from app.rag.embeddings import embed_text
from app.utils.validators import validate_query

logger = logging.getLogger(__name__)
bp = Blueprint("embed", __name__, url_prefix="/api/embed")


@bp.route("", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_SEARCH)
@auth_required(optional=True)
def embed():
    user = get_current_user_context()
    try:
        require_guest_session(user)
    except ValueError as exc:
        audit_failure("embed.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    data = request.get_json(silent=True) or {}
    try:
        text = validate_query(data.get("text", ""))
    except ValueError as exc:
        audit_failure("embed.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    try:
        embedding = embed_text(text)
        audit_action(
            "embed.success",
            user,
            category="ai",
            text_length=len(text),
        )
        return jsonify({"embedding": embedding})
    except Exception:
        logger.exception("Embedding failed")
        audit_failure(
            "embed.error",
            category="ai",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
        )
        return jsonify({"error": GENERIC_500}), 500
