from datetime import datetime, timezone
from typing import Any

from app.core.config import Config
from app.db.cosmos import get_container, _is_enabled


class GuestSessionRepository:
    def __init__(self) -> None:
        self._container = None

    @property
    def enabled(self) -> bool:
        return _is_enabled()

    @property
    def container(self):
        if self._container is None:
            self._container = get_container(
                Config.COSMOS_GUEST_SESSIONS_CONTAINER,
                partition_key="session_id",
            )
        return self._container

    def upsert(self, session: dict[str, Any]) -> dict[str, Any]:
        return self.container.upsert_item(body=session)

    def get(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self.container.read_item(item=session_id, partition_key=session_id)
        except Exception:
            return None

    def delete(self, session_id: str) -> None:
        try:
            self.container.delete_item(item=session_id, partition_key=session_id)
        except Exception:
            pass

    def list_expired(self, before: datetime | None = None) -> list[dict[str, Any]]:
        cutoff = (before or datetime.now(timezone.utc)).isoformat()
        query = "SELECT * FROM c WHERE c.expires_at < @cutoff"
        return list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@cutoff", "value": cutoff}],
                enable_cross_partition_query=True,
            )
        )
