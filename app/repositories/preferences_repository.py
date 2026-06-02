from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.core.config import Config
from app.db.cosmos import get_container


class PreferencesRepository:
    PREFERENCES_ID = "preferences"

    def __init__(self) -> None:
        self._container = None

    @property
    def container(self):
        if self._container is None:
            self._container = get_container(
                Config.COSMOS_PREFERENCES_CONTAINER,
                partition_key="owner_user_id",
            )
        return self._container

    def get(self, owner_user_id: str) -> dict[str, Any]:
        defaults = {
            "id": self.PREFERENCES_ID,
            "owner_user_id": owner_user_id,
            "theme": "dark",
            "active_chat_id": "",
        }
        try:
            return self.container.read_item(
                item=self.PREFERENCES_ID,
                partition_key=owner_user_id,
            )
        except CosmosResourceNotFoundError:
            return defaults
        except Exception:
            return defaults

    def upsert(self, owner_user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        doc = {
            "id": self.PREFERENCES_ID,
            "owner_user_id": owner_user_id,
            "theme": preferences.get("theme", "dark"),
            "active_chat_id": preferences.get("active_chat_id", ""),
        }
        return self.container.upsert_item(body=doc)
