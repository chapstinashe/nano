from datetime import datetime, timedelta, timezone

from app.core.config import Config
from app.db.cosmos import require_cosmos
from app.repositories.document_repository import DocumentRepository
from app.utils.guest_guard import is_guest_owner

document_repo = DocumentRepository()


def assert_can_upload_file(owner_user_id: str) -> None:
    """Unauthenticated (guest) users may upload at most one file per UTC calendar day."""
    if not is_guest_owner(owner_user_id):
        return
    require_cosmos()

    count = document_repo.count_file_uploads_today(owner_user_id)
    if count >= Config.GUEST_DAILY_UPLOAD_LIMIT:
        limit = Config.GUEST_DAILY_UPLOAD_LIMIT
        unit = "file" if limit == 1 else "files"
        raise ValueError(
            f"Daily upload limit reached. You can upload only {limit} {unit} per day. "
            "Login to upload more files."
        )


def file_expires_at(owner_user_id: str) -> str | None:
    if not is_guest_owner(owner_user_id):
        return None
    expires = datetime.now(timezone.utc) + timedelta(hours=Config.GUEST_DOCUMENT_TTL_HOURS)
    return expires.isoformat()
