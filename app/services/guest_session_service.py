import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import Config
from app.db.cosmos import require_cosmos
from app.repositories.guest_session_repository import GuestSessionRepository
from app.services.document_cleanup_service import purge_owner_data

logger = logging.getLogger(__name__)

guest_session_repo = GuestSessionRepository()


def is_tracking_enabled() -> bool:
    return Config.AUTH_ENABLED and guest_session_repo.enabled


def validate_session_id(session_id: str) -> str:
    session_id = (session_id or "").strip()
    if not session_id:
        raise ValueError("X-Session-Id header is required for guest access")
    try:
        uuid.UUID(session_id)
    except ValueError as exc:
        raise ValueError("X-Session-Id must be a valid UUID") from exc
    return session_id


def owner_user_id_for_session(session_id: str) -> str:
    return f"anon:{session_id}"


def ensure_active(session_id: str, owner_user_id: str) -> dict[str, str]:
    session_id = validate_session_id(session_id)
    if owner_user_id != owner_user_id_for_session(session_id):
        owner_user_id = owner_user_id_for_session(session_id)

    if not is_tracking_enabled():
        if Config.AUTH_ENABLED:
            require_cosmos()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=Config.ANON_SESSION_TTL_HOURS)
        return {"session_id": session_id, "owner_user_id": owner_user_id, "expires_at": expires_at.isoformat()}

    require_cosmos()
    now = datetime.now(timezone.utc)
    existing = guest_session_repo.get(session_id)
    if existing and existing.get("expires_at", "") < now.isoformat():
        logger.info("Guest session expired: %s", session_id)
        purge_owner_data(owner_user_id)
        guest_session_repo.delete(session_id)
        existing = None

    if existing:
        expires_at = datetime.fromisoformat(existing["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        guest_session_repo.upsert(
            {
                **existing,
                "last_active_at": now.isoformat(),
            }
        )
        return {
            "session_id": session_id,
            "owner_user_id": owner_user_id,
            "expires_at": expires_at.isoformat(),
        }

    expires_at = now + timedelta(hours=Config.ANON_SESSION_TTL_HOURS)
    guest_session_repo.upsert(
        {
            "id": session_id,
            "session_id": session_id,
            "owner_user_id": owner_user_id,
            "created_at": now.isoformat(),
            "last_active_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    )
    return {"session_id": session_id, "owner_user_id": owner_user_id, "expires_at": expires_at.isoformat()}


def cleanup_expired_sessions() -> int:
    if not is_tracking_enabled():
        return 0

    expired = guest_session_repo.list_expired()
    cleaned = 0
    for session in expired:
        session_id = session.get("session_id") or session.get("id")
        owner_user_id = session.get("owner_user_id") or owner_user_id_for_session(session_id or "")
        if not session_id:
            continue
        purge_owner_data(owner_user_id)
        guest_session_repo.delete(session_id)
        cleaned += 1
        logger.info("Cleaned expired guest session: %s", session_id)
    return cleaned
