import logging

from flask import Blueprint, jsonify, request, Response, stream_with_context

from app.core.audit import audit_action, audit_failure
from app.core.auth import auth_required, get_current_user_context, require_guest_session
from app.core.config import Config
from app.core.errors import GENERIC_500, client_error
from app.core.rate_limit import limiter
from app.services.chat_service import ChatService
from app.utils.owner_documents import resolve_document_ids
from app.utils.payload_validators import validate_context_chunks
from app.utils.validators import validate_query, validate_top_k
from app.rag.pipeline import results_from_context_chunks

logger = logging.getLogger(__name__)
bp = Blueprint("chat", __name__, url_prefix="/api/chat")
chat_service = ChatService()


def _parse_chat_request(user: dict):
    data = request.get_json(silent=True) or {}
    query = validate_query(data.get("query", ""))
    top_k = validate_top_k(int(data.get("top_k", Config.DEFAULT_TOP_K)))

    if not user.get("is_authenticated"):
        context_chunks = validate_context_chunks(data.get("context_chunks"))
        return query, top_k, None, results_from_context_chunks(context_chunks)

    document_ids = resolve_document_ids(user["user_id"], data.get("document_ids"))
    return query, top_k, document_ids, None


def _chat_audit_details(query: str, top_k: int, document_ids, **extra):
    return {
        "query_length": len(query),
        "query_preview": query[:120],
        "top_k": top_k,
        "document_count": len(document_ids) if document_ids else 0,
        **extra,
    }


@bp.route("", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_CHAT)
@auth_required(optional=True)
def chat():
    user = get_current_user_context()
    try:
        require_guest_session(user)
        query, top_k, document_ids, context_results = _parse_chat_request(user)
    except (ValueError, TypeError) as exc:
        audit_failure("chat.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    try:
        answer, sources = chat_service.get_response(
            query=query,
            owner_user_id=user["user_id"],
            top_k=top_k,
            document_ids=document_ids,
            context_results=context_results,
        )
        audit_action(
            "chat.success",
            user,
            category="ai",
            mode="sync",
            source_count=len(sources),
            answer_length=len(answer or ""),
            **_chat_audit_details(query, top_k, document_ids),
        )
        return jsonify({"query": query, "answer": answer, "sources": sources})
    except RuntimeError as exc:
        audit_failure(
            "chat.unavailable",
            category="ai",
            user_id=user.get("user_id", ""),
            reason=client_error(exc),
            **_chat_audit_details(query, top_k, document_ids, mode="sync"),
        )
        return jsonify({"error": client_error(exc)}), 503
    except Exception:
        logger.exception("Chat failed")
        audit_failure(
            "chat.error",
            category="ai",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
            **_chat_audit_details(query, top_k, document_ids, mode="sync"),
        )
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/stream", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_CHAT)
@auth_required(optional=True)
def stream_chat():
    user = get_current_user_context()
    try:
        require_guest_session(user)
        query, top_k, document_ids, context_results = _parse_chat_request(user)
    except (ValueError, TypeError) as exc:
        audit_failure("chat.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    try:
        generator = chat_service.stream_response(
            query=query,
            owner_user_id=user["user_id"],
            top_k=top_k,
            document_ids=document_ids,
            context_results=context_results,
        )
        audit_action(
            "chat.started",
            user,
            category="ai",
            mode="stream",
            **_chat_audit_details(query, top_k, document_ids),
        )
        return Response(
            stream_with_context(generator),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    except RuntimeError as exc:
        audit_failure(
            "chat.unavailable",
            category="ai",
            user_id=user.get("user_id", ""),
            reason=client_error(exc),
            **_chat_audit_details(query, top_k, document_ids, mode="stream"),
        )
        return jsonify({"error": client_error(exc)}), 503
    except Exception:
        logger.exception("Chat stream failed")
        audit_failure(
            "chat.error",
            category="ai",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
            **_chat_audit_details(query, top_k, document_ids, mode="stream"),
        )
        return jsonify({"error": GENERIC_500}), 500
