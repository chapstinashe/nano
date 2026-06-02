import pytest

from app.security.registration_guard import validate_registration_request


def test_validate_registration_request_blocks_disposable_email():
    with pytest.raises(ValueError):
        validate_registration_request("bot@mailinator.com", "password123")
