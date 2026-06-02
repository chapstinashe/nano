from flask import Blueprint, jsonify, request

from app.core.audit import audit_action, audit_failure
from app.core.auth import auth_required, get_current_user_context, require_guest_session
from app.repositories.preferences_repository import PreferencesRepository
from app.utils.payload_validators import validate_preferences_payload

bp = Blueprint("preferences", __name__, url_prefix="/api/preferences")
preferences_repo = PreferencesRepository()


@bp.route("", methods=["GET"])
@auth_required(optional=True)
def get_preferences():
    user = get_current_user_context()
    try:
        require_guest_session(user)
    except ValueError as exc:
        audit_failure("preferences.read.rejected", category="data", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    prefs = preferences_repo.get(user["user_id"])
    audit_action("preferences.read", user, category="data", theme=prefs.get("theme", "dark"))
    return jsonify(
        {
            "theme": prefs.get("theme", "dark"),
            "active_chat_id": prefs.get("active_chat_id", ""),
        }
    )


@bp.route("", methods=["PUT"])
@auth_required(optional=True)
def save_preferences():
    user = get_current_user_context()
    try:
        require_guest_session(user)
        payload = validate_preferences_payload(request.get_json(silent=True) or {})
    except ValueError as exc:
        audit_failure("preferences.save.rejected", category="data", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    prefs = preferences_repo.upsert(user["user_id"], payload)
    audit_action(
        "preferences.saved",
        user,
        category="data",
        theme=prefs.get("theme", "dark"),
        active_chat_id=prefs.get("active_chat_id", ""),
    )
    return jsonify(
        {
            "theme": prefs.get("theme", "dark"),
            "active_chat_id": prefs.get("active_chat_id", ""),
        }
    )
