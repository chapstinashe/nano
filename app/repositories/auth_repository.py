from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.core.config import Config
from app.db.cosmos import get_container


class AuthRepository:
    def __init__(self) -> None:
        self._users = None
        self._tokens = None

    @property
    def users(self):
        if self._users is None:
            self._users = get_container(Config.COSMOS_USERS_CONTAINER, partition_key="email")
        return self._users

    @property
    def tokens(self):
        if self._tokens is None:
            self._tokens = get_container(Config.COSMOS_TOKENS_CONTAINER, partition_key="user_id")
        return self._tokens

    def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return self.users.create_item(body=user)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        query = "SELECT * FROM c WHERE c.email = @email"
        items = list(
            self.users.query_items(
                query=query,
                parameters=[{"name": "@email", "value": email.lower()}],
                enable_cross_partition_query=True,
            )
        )
        return items[0] if items else None

    def get_user_by_id(self, user_id: str, email: str) -> dict[str, Any] | None:
        try:
            return self.users.read_item(item=user_id, partition_key=email.lower())
        except CosmosResourceNotFoundError:
            return None

    def store_refresh_token(self, token_doc: dict[str, Any]) -> dict[str, Any]:
        return self.tokens.create_item(body=token_doc)

    def get_refresh_token(self, token_id: str, user_id: str) -> dict[str, Any] | None:
        try:
            return self.tokens.read_item(item=token_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None

    def revoke_refresh_token(self, token_doc: dict[str, Any]) -> dict[str, Any]:
        token_doc["revoked"] = True
        token_doc["revoked_at"] = datetime.now(timezone.utc).isoformat()
        return self.tokens.replace_item(item=token_doc["id"], body=token_doc)
