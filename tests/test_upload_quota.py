from datetime import datetime, timezone

from app.services.upload_quota_service import (
    assert_can_upload_file,
    file_expires_at,
    is_guest_owner,
)


def test_is_guest_owner():
    assert is_guest_owner("anon:abc-123")
    assert not is_guest_owner("user-123")
    assert not is_guest_owner("")


def test_file_expires_at_only_for_guests():
    assert file_expires_at("user-123") is None
    expires = file_expires_at("anon:session-id")
    assert expires is not None
    parsed = datetime.fromisoformat(expires)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    assert parsed > datetime.now(timezone.utc)


def test_assert_can_upload_skips_logged_in_users():
    assert_can_upload_file("user-00000000-0000-0000-0000-000000000001")
