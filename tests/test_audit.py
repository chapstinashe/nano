import json

import pytest

from app.core.audit import _mask_email, _sanitize_details, log_security_event


def test_mask_email():
    assert _mask_email("alice@example.com") == "a***@example.com"


def test_sanitize_details_redacts_secrets():
    sanitized = _sanitize_details({"password": "secret123", "email": "bob@test.com"})
    assert sanitized["password"] == "[redacted]"
    assert sanitized["email"] == "b***@test.com"


def test_log_security_event_emits_json(monkeypatch):
    monkeypatch.setattr("app.core.config.Config.AUTH_ENABLED", False)
    monkeypatch.setattr("app.db.cosmos.ensure_all_containers", lambda: None)

    from app import create_app

    app = create_app()
    with app.test_request_context("/api/auth/login", method="POST"):
        import logging

        audit_logger = logging.getLogger("security.audit")
        records = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = CaptureHandler()
        audit_logger.addHandler(handler)
        try:
            log_security_event(
                "login.success",
                category="auth",
                user_id="user-1",
                details={"email": "alice@example.com"},
            )
        finally:
            audit_logger.removeHandler(handler)

        assert records
        payload = json.loads(records[-1].getMessage())
        assert payload["schema"] == "nano.audit.v1"
        assert payload["event"] == "login.success"
        assert payload["category"] == "auth"
        assert payload["details"]["email"] == "a***@example.com"
        assert payload["request_id"]
