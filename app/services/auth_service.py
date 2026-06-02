import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from flask_jwt_extended import create_access_token, create_refresh_token, decode_token
from passlib.context import CryptContext

from app.repositories.auth_repository import AuthRepository
from app.security.registration_guard import validate_registration_request

# Prefer pbkdf2_sha256 to avoid bcrypt backend/version issues.
# Keep bcrypt_sha256 for backward verification compatibility.
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt_sha256"],
    deprecated="auto",
)


class AuthService:
    def __init__(self) -> None:
        self.repo = AuthRepository()

    def register_user(self, email: str, password: str) -> dict[str, Any]:
        normalized_email = validate_registration_request(email, password)

        existing = self.repo.get_user_by_email(normalized_email)
        if existing:
            raise ValueError("Email is already registered")

        now = datetime.now(timezone.utc).isoformat()
        user = {
            "id": str(uuid.uuid4()),
            "email": normalized_email,
            "password_hash": pwd_context.hash(password),
            "role": "user",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        self.repo.create_user(user)
        return self._to_user_payload(user)

    def login(self, email: str, password: str) -> dict[str, Any]:
        normalized_email = (email or "").strip().lower()
        user = self.repo.get_user_by_email(normalized_email)
        if not user or not pwd_context.verify(password or "", user.get("password_hash", "")):
            raise ValueError("Invalid credentials")
        if user.get("status") != "active":
            raise ValueError("User is disabled")

        return self._issue_tokens(user)

    def rotate_refresh_token(self, refresh_token: str) -> dict[str, Any]:
        decoded = decode_token(refresh_token)
        jti = decoded.get("jti")
        user_id = decoded.get("sub")
        email = decoded.get("email")
        if not jti or not user_id or not email:
            raise ValueError("Invalid refresh token")

        stored = self.repo.get_refresh_token(jti, user_id=user_id)
        token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        if not stored or stored.get("revoked") or stored.get("token_hash") != token_hash:
            raise ValueError("Refresh token is invalid or revoked")

        self.repo.revoke_refresh_token(stored)
        user = self.repo.get_user_by_id(user_id=user_id, email=email)
        if not user:
            raise ValueError("User not found")

        return self._issue_tokens(user)

    def revoke_refresh_token(self, refresh_token: str) -> None:
        decoded = decode_token(refresh_token)
        jti = decoded.get("jti")
        user_id = decoded.get("sub")
        if not jti or not user_id:
            return
        stored = self.repo.get_refresh_token(jti, user_id=user_id)
        if stored and not stored.get("revoked"):
            self.repo.revoke_refresh_token(stored)

    def get_user(self, user_id: str, email: str) -> dict[str, Any] | None:
        user = self.repo.get_user_by_id(user_id=user_id, email=email)
        if not user:
            return None
        return self._to_user_payload(user)

    def _issue_tokens(self, user: dict[str, Any]) -> dict[str, Any]:
        access_token = create_access_token(
            identity=user["id"],
            additional_claims={"email": user["email"], "role": user.get("role", "user")},
        )
        refresh_token = create_refresh_token(
            identity=user["id"],
            additional_claims={"email": user["email"], "role": user.get("role", "user")},
        )

        decoded = decode_token(refresh_token)
        token_doc = {
            "id": decoded.get("jti"),
            "user_id": user["id"],
            "token_hash": hashlib.sha256(refresh_token.encode("utf-8")).hexdigest(),
            "expires_at": datetime.fromtimestamp(decoded.get("exp"), tz=timezone.utc).isoformat(),
            "revoked": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.repo.store_refresh_token(token_doc)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": self._to_user_payload(user),
        }

    @staticmethod
    def _to_user_payload(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user.get("role", "user"),
            "status": user.get("status", "active"),
            "created_at": user.get("created_at", ""),
        }
