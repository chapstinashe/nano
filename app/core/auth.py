from functools import wraps
from typing import Any, Callable

from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from app.core.config import Config
from app.core.audit import log_security_event

SESSION_HEADER = "X-Session-Id"


def get_session_id() -> str:
    cookie = (request.cookies.get("nano_session_id", "") or "").strip()
    if cookie:
        return cookie
    return (request.headers.get(SESSION_HEADER, "") or "").strip()


def _should_track_guest_session() -> bool:
    if not Config.AUTH_ENABLED:
        return False
    if not request.path.startswith("/api/"):
        return False
    if request.path in ("/api/health",):
        return False
    return True


def auth_required(optional: bool = False):
    def decorator(fn: Callable[..., Any]):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not Config.AUTH_ENABLED:
                return fn(*args, **kwargs)
            verify_jwt_in_request(optional=optional)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def role_required(*allowed_roles: str):
    def decorator(fn: Callable[..., Any]):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not Config.AUTH_ENABLED:
                return fn(*args, **kwargs)
            verify_jwt_in_request()
            claims = get_jwt()
            role = claims.get("role")
            if role not in allowed_roles:
                log_security_event(
                    "access.denied",
                    category="auth",
                    severity="warning",
                    user_id=get_jwt_identity() or "",
                    outcome="failure",
                    status_code=403,
                    details={
                        "required_roles": list(allowed_roles),
                        "actual_role": role,
                    },
                )
                return jsonify({"error": "Forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_guest_session(user: dict[str, Any]) -> None:
    if not Config.AUTH_ENABLED or user.get("is_authenticated"):
        return
    if not user.get("session_id"):
        raise ValueError("Session is required for guest access")


def get_current_user_context(touch_guest_session: bool = True) -> dict[str, Any]:
    session_id = get_session_id()
    anonymous_user_id = f"anon:{session_id}" if session_id else ""

    if not Config.AUTH_ENABLED:
        return {
            "user_id": anonymous_user_id,
            "session_id": session_id,
            "email": "",
            "role": "anonymous",
            "is_authenticated": False,
        }

    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    if identity:
        claims = get_jwt()
        return {
            "user_id": identity,
            "session_id": session_id,
            "email": claims.get("email", ""),
            "role": claims.get("role", "user"),
            "is_authenticated": True,
        }

    if touch_guest_session and _should_track_guest_session() and session_id:
        from app.services.guest_session_service import ensure_active

        ensure_active(session_id, anonymous_user_id)

    return {
        "user_id": anonymous_user_id,
        "session_id": session_id,
        "email": "",
        "role": "anonymous",
        "is_authenticated": False,
    }
