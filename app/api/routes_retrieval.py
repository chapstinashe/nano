"""Rerank client-supplied chunks (guest IndexedDB retrieval)."""

import logging

from flask import Blueprint, jsonify, request

from app.core.audit import audit_action, audit_failure
from app.core.auth import auth_required, get_current_user_context, require_guest_session
from app.core.config import Config
from app.core.errors import GENERIC_500
from app.core.rate_limit import limiter
from app.models.schemas import SearchResult
from app.rag.retrieval_engine import rank_search_results
from app.rag.retrieval_scoring import score_result
from app.utils.validators import validate_query, validate_top_k

logger = logging.getLogger(__name__)
bp = Blueprint("retrieval", __name__, url_prefix="/api/retrieval")


def _validate_candidates(raw: list | None) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("candidates must be a non-empty list")

    if len(raw) > Config.RETRIEVAL_CANDIDATE_K * 2:
        raise ValueError(f"candidates cannot exceed {Config.RETRIEVAL_CANDIDATE_K * 2} items")

    normalized: list[dict] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        chunk_id = str(item.get("id", "")).strip()
        text = str(item.get("text", "")).strip()
        if not chunk_id or not text:
            raise ValueError(f"candidates[{index}] requires id and text")
        if len(text) > Config.MAX_CHAT_MESSAGE_CHARS:
            raise ValueError(f"candidates[{index}] text is too long")
        try:
            vector_score = float(item.get("vector_score", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"candidates[{index}] vector_score must be a number") from exc
        vector_score = max(0.0, min(1.0, vector_score))
        metadata = item.get("metadata", {})
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError(f"candidates[{index}] metadata must be an object")
        normalized.append(
            {
                "id": chunk_id,
                "text": text,
                "vector_score": vector_score,
                "metadata": metadata or {},
            }
        )
    return normalized


@bp.route("/rank", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_SEARCH)
@auth_required(optional=True)
def rank_candidates():
    user = get_current_user_context()
    try:
        require_guest_session(user)
    except ValueError as exc:
        audit_failure("retrieval.rank.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    data = request.get_json(silent=True) or {}
    try:
        query = validate_query(data.get("query", ""))
        top_k = validate_top_k(int(data.get("top_k", Config.DEFAULT_TOP_K)))
        candidates = _validate_candidates(data.get("candidates"))
    except (ValueError, TypeError) as exc:
        audit_failure("retrieval.rank.rejected", category="ai", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    try:
        merged: dict[str, SearchResult] = {}
        for candidate in candidates:
            score, breakdown = score_result(query, candidate["vector_score"], candidate["text"])
            metadata = dict(candidate["metadata"])
            metadata.update(breakdown)
            chunk_id = candidate["id"]
            existing = merged.get(chunk_id)
            if existing is None or score > existing.score:
                merged[chunk_id] = SearchResult(
                    id=chunk_id,
                    text=candidate["text"],
                    score=score,
                    metadata=metadata,
                )

        final = rank_search_results(query, list(merged.values()), top_k)
        audit_action(
            "retrieval.rank.success",
            user,
            category="ai",
            query_length=len(query),
            candidate_count=len(candidates),
            result_count=len(final),
        )
        return jsonify(
            {
                "query": query,
                "results": [
                    {
                        "id": result.id,
                        "text": result.text,
                        "score": result.score,
                        "metadata": result.metadata,
                    }
                    for result in final
                ],
            }
        )
    except Exception:
        logger.exception("Guest chunk rerank failed")
        audit_failure(
            "retrieval.rank.error",
            category="ai",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
        )
        return jsonify({"error": GENERIC_500}), 500
