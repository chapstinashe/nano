import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required, set_access_cookies, set_refresh_cookies, unset_jwt_cookies

from app.core.audit import audit_failure, log_security_event
from app.core.auth import auth_required
from app.core.config import Config
from app.core.errors import GENERIC_500
from app.core.rate_limit import limiter
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__, url_prefix="/api/auth")
auth_service = AuthService()


def _set_auth_cookies(response, tokens: dict) -> None:
    set_access_cookies(response, tokens["access_token"])
    set_refresh_cookies(response, tokens["refresh_token"])


def _fake_registration_response(email: str):
    return jsonify(
        {
            "user": {
                "id": "00000000-0000-0000-0000-000000000000",
                "email": (email or "").strip().lower(),
                "role": "user",
                "status": "active",
            }
        }
    ), 201


@bp.route("/register", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_REGISTER)
def register():
    if not Config.AUTH_ENABLED:
        return jsonify({"error": "Auth is disabled"}), 400
    data = request.get_json(silent=True) or {}
    if data.get("website"):
        log_security_event(
            "register.honeypot",
            category="auth",
            severity="warning",
            outcome="blocked",
            details={"email": data.get("email", "")},
        )
        return _fake_registration_response(data.get("email", ""))

    try:
        user = auth_service.register_user(
            email=data.get("email", ""),
            password=data.get("password", ""),
        )
        log_security_event(
            "register.success",
            category="auth",
            user_id=user["id"],
            details={"email": user["email"], "role": user.get("role", "user")},
        )
        return jsonify({"user": user}), 201
    except ValueError as exc:
        audit_failure(
            "register.failed",
            category="auth",
            reason=str(exc),
            email=data.get("email", ""),
        )
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Registration failed")
        audit_failure("register.error", category="auth", severity="critical", reason=GENERIC_500)
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/login", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_LOGIN)
def login():
    if not Config.AUTH_ENABLED:
        return jsonify({"error": "Auth is disabled"}), 400
    data = request.get_json(silent=True) or {}
    try:
        result = auth_service.login(email=data.get("email", ""), password=data.get("password", ""))
        response = jsonify({"user": result["user"]})
        _set_auth_cookies(response, result)
        log_security_event(
            "login.success",
            category="auth",
            user_id=result["user"]["id"],
            details={"email": result["user"]["email"], "role": result["user"].get("role", "user")},
        )
        return response
    except ValueError as exc:
        audit_failure(
            "login.failed",
            category="auth",
            reason=str(exc),
            email=data.get("email", ""),
        )
        return jsonify({"error": str(exc)}), 401
    except Exception:
        logger.exception("Login failed")
        audit_failure("login.error", category="auth", severity="critical", reason=GENERIC_500)
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/refresh", methods=["POST"])
@limiter.limit(lambda: Config.RATE_LIMIT_REFRESH)
@jwt_required(refresh=True)
def refresh():
    if not Config.AUTH_ENABLED:
        return jsonify({"error": "Auth is disabled"}), 400
    try:
        refresh_token = request.cookies.get(Config.JWT_REFRESH_COOKIE_NAME)
        if not refresh_token:
            raw = request.get_json(silent=True) or {}
            refresh_token = raw.get("refresh_token")
        if not refresh_token:
            return jsonify({"error": "refresh_token is required"}), 401
        result = auth_service.rotate_refresh_token(refresh_token)
        response = jsonify({"user": result["user"]})
        _set_auth_cookies(response, result)
        log_security_event(
            "token.refresh",
            category="auth",
            user_id=result["user"]["id"],
            details={"email": result["user"]["email"]},
        )
        return response
    except ValueError as exc:
        audit_failure("token.refresh_failed", category="auth", reason=str(exc))
        return jsonify({"error": str(exc)}), 401
    except Exception:
        logger.exception("Token refresh failed")
        audit_failure("token.refresh_error", category="auth", severity="critical", reason=GENERIC_500)
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/logout", methods=["POST"])
@jwt_required(refresh=True, optional=True)
def logout():
    if not Config.AUTH_ENABLED:
        return jsonify({"error": "Auth is disabled"}), 400
    try:
        refresh_token = request.cookies.get(Config.JWT_REFRESH_COOKIE_NAME)
        if not refresh_token:
            raw = request.get_json(silent=True) or {}
            refresh_token = raw.get("refresh_token")
        user_id = get_jwt_identity() or ""
        if refresh_token:
            auth_service.revoke_refresh_token(refresh_token)
        response = jsonify({"status": "ok"})
        unset_jwt_cookies(response)
        log_security_event("logout", category="auth", user_id=user_id)
        return response
    except Exception:
        logger.exception("Logout failed")
        audit_failure("logout.error", category="auth", severity="critical", reason=GENERIC_500)
        return jsonify({"error": GENERIC_500}), 500


@bp.route("/me", methods=["GET"])
@auth_required()
def me():
    if not Config.AUTH_ENABLED:
        return jsonify({"error": "Auth is disabled"}), 400
    try:
        identity = get_jwt_identity()
        email = get_jwt().get("email", "")
        user = auth_service.get_user(identity, email)
        if not user:
            audit_failure("profile.not_found", category="auth", user_id=identity or "", reason="User not found")
            return jsonify({"error": "User not found"}), 404
        return jsonify({"user": user})
    except Exception:
        logger.exception("Failed to load profile")
        audit_failure("profile.error", category="auth", severity="critical", reason=GENERIC_500)
        return jsonify({"error": GENERIC_500}), 500
