import logging
import uuid

from flask import Blueprint, jsonify, make_response

from app.core.audit import audit_action, audit_failure
from app.core.auth import get_current_user_context
from app.core.config import Config
from app.core.errors import GENERIC_500
from app.repositories.guest_session_repository import GuestSessionRepository
from app.services.document_cleanup_service import purge_owner_data
from app.services.guest_session_service import (
    ensure_active,
    is_tracking_enabled,
    owner_user_id_for_session,
    validate_session_id,
)

logger = logging.getLogger(__name__)
guest_session_repo = GuestSessionRepository()

bp = Blueprint("session", __name__, url_prefix="/api")


def _set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        "nano_session_id",
        session_id,
        max_age=Config.ANON_SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=Config.COOKIE_SECURE,
        samesite=Config.COOKIE_SAMESITE,
        path="/",
    )


@bp.route("/session", methods=["GET"])
def get_session():
    user = get_current_user_context(touch_guest_session=False)
    if user["is_authenticated"]:
        return jsonify(
            {
                "authenticated": True,
                "user_id": user["user_id"],
            }
        )

    session_id = user.get("session_id", "")
    if not session_id:
        session_id = str(uuid.uuid4())

    info = ensure_active(session_id, owner_user_id_for_session(session_id))
    payload = {
        "authenticated": False,
        "session_id": session_id,
        "user_id": owner_user_id_for_session(session_id),
        "expires_at": info["expires_at"],
        "ttl_hours": Config.ANON_SESSION_TTL_HOURS,
        "guest_upload_limit": Config.GUEST_DAILY_UPLOAD_LIMIT,
        "fixed_expiry": True,
        "tracking_enabled": is_tracking_enabled(),
    }
    response = make_response(jsonify(payload))
    _set_session_cookie(response, session_id)
    audit_action(
        "session.created",
        {
            "user_id": owner_user_id_for_session(session_id),
            "session_id": session_id,
            "role": "anonymous",
            "is_authenticated": False,
            "email": "",
        },
        category="session",
        expires_at=info["expires_at"],
    )
    return response


@bp.route("/session", methods=["DELETE"])
def delete_session():
    """
    Purge all guest data for the current session cookie or X-Session-Id header.
    """
    user = get_current_user_context(touch_guest_session=False)
    if user["is_authenticated"]:
        return jsonify({"error": "Authenticated users cannot purge guest session data"}), 400

    session_id = user.get("session_id", "")
    if not session_id:
        return jsonify({"error": "Session is required"}), 400

    try:
        session_id = validate_session_id(session_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    owner_user_id = owner_user_id_for_session(session_id)
    try:
        stats = purge_owner_data(owner_user_id)
        if guest_session_repo.enabled:
            guest_session_repo.delete(session_id)
        audit_action(
            "session.purged",
            {
                "user_id": owner_user_id,
                "session_id": session_id,
                "role": "anonymous",
                "is_authenticated": False,
                "email": "",
            },
            category="session",
            **stats,
        )
        response = make_response(jsonify({"status": "purged", "session_id": session_id, **stats}))
        response.set_cookie(
            "nano_session_id",
            "",
            max_age=0,
            httponly=True,
            secure=Config.COOKIE_SECURE,
            samesite=Config.COOKIE_SAMESITE,
            path="/",
        )
        return response
    except Exception:
        logger.exception("Session purge failed")
        audit_failure("session.purge_error", category="session", severity="critical", reason=GENERIC_500)
        return jsonify({"error": GENERIC_500}), 500
