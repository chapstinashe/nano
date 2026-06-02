from typing import Any

from app.core.config import Config
from app.db.cosmos import get_container


class ChatRepository:
    def __init__(self) -> None:
        self._container = None

    @property
    def container(self):
        if self._container is None:
            self._container = get_container(Config.COSMOS_CHATS_CONTAINER, partition_key="owner_user_id")
        return self._container

    def upsert_chat(self, chat: dict[str, Any]) -> dict[str, Any]:
        return self.container.upsert_item(body=chat)

    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        query = "SELECT * FROM c WHERE c.owner_user_id = @owner_user_id ORDER BY c.created_at DESC"
        return list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@owner_user_id", "value": owner_user_id}],
                partition_key=owner_user_id,
            )
        )

    def delete_chat(self, owner_user_id: str, chat_id: str) -> None:
        self.container.delete_item(item=chat_id, partition_key=owner_user_id)
