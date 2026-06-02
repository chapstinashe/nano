import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.core.audit import audit_action, audit_failure
from app.core.auth import auth_required, get_current_user_context
from app.core.errors import GENERIC_500
from app.core.security import validate_uuid
from app.repositories.chat_repository import ChatRepository
from app.utils.payload_validators import validate_chat_payload

logger = logging.getLogger(__name__)
bp = Blueprint("chats", __name__, url_prefix="/api/chats")
chat_repo = ChatRepository()


@bp.route("", methods=["GET"])
@auth_required(optional=True)
def list_chats():
    user = get_current_user_context()
    if not user.get("is_authenticated"):
        return jsonify({"chats": []})

    chats = chat_repo.list_by_owner(user["user_id"])
    audit_action("chat.list", user, category="data", chat_count=len(chats))
    return jsonify({"chats": chats})


@bp.route("/<chat_id>", methods=["PUT"])
@auth_required(optional=True)
def upsert_chat(chat_id: str):
    user = get_current_user_context()
    if not user.get("is_authenticated"):
        return jsonify({"error": "Guest chat history is stored locally in the browser"}), 403

    try:
        chat_id = validate_uuid(chat_id, field_name="chat_id")
        payload = validate_chat_payload(request.get_json(silent=True) or {})
    except ValueError as exc:
        audit_failure("chat.save.rejected", category="data", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    now = datetime.now(timezone.utc).isoformat()

    chat = {
        "id": chat_id,
        "owner_user_id": user["user_id"],
        "title": payload["title"],
        "messages": payload["messages"],
        "created_at": payload["created_at"] or now,
        "updated_at": now,
    }
    chat_repo.upsert_chat(chat)
    audit_action(
        "chat.saved",
        user,
        category="data",
        chat_id=chat_id,
        title=payload["title"],
        message_count=len(payload["messages"]),
    )
    return jsonify({"status": "ok"})


@bp.route("/<chat_id>", methods=["DELETE"])
@auth_required(optional=True)
def delete_chat(chat_id: str):
    user = get_current_user_context()
    if not user.get("is_authenticated"):
        return jsonify({"error": "Guest chat history is stored locally in the browser"}), 403

    try:
        chat_id = validate_uuid(chat_id, field_name="chat_id")
    except ValueError as exc:
        audit_failure("chat.delete.rejected", category="data", user_id=user.get("user_id", ""), reason=str(exc))
        return jsonify({"error": str(exc)}), 400

    try:
        chat_repo.delete_chat(owner_user_id=user["user_id"], chat_id=chat_id)
        audit_action("chat.deleted", user, category="data", chat_id=chat_id)
        return jsonify({"status": "deleted"})
    except Exception:
        logger.exception("Chat deletion failed")
        audit_failure(
            "chat.delete.error",
            category="data",
            severity="critical",
            user_id=user.get("user_id", ""),
            reason=GENERIC_500,
            chat_id=chat_id,
        )
        return jsonify({"error": GENERIC_500}), 500
