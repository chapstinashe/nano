import pytest

from app.services.auth_service import AuthService


def test_register_user_always_assigns_user_role(monkeypatch):
    captured = {}

    def fake_create_user(user):
        captured["user"] = user

    service = AuthService()
    monkeypatch.setattr(service.repo, "get_user_by_email", lambda _email: None)
    monkeypatch.setattr(service.repo, "create_user", fake_create_user)

    service.register_user("admin@example.com", "password123")

    assert captured["user"]["role"] == "user"
