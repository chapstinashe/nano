from datetime import datetime, timezone
from typing import Any

from app.core.config import Config
from app.db.cosmos import _is_enabled, get_container
from app.utils.guest_guard import assert_not_guest_persist


class DocumentRepository:
    def __init__(self) -> None:
        self._container = None

    @property
    def enabled(self) -> bool:
        return _is_enabled()

    @property
    def container(self):
        if self._container is None:
            self._container = get_container(Config.COSMOS_DOCUMENTS_CONTAINER, partition_key="owner_user_id")
        return self._container

    def upsert(self, doc: dict[str, Any]) -> dict[str, Any]:
        assert_not_guest_persist(doc.get("owner_user_id", ""), resource="documents")
        return self.container.upsert_item(body=doc)

    def get_by_id(self, owner_user_id: str, document_id: str) -> dict[str, Any] | None:
        query = "SELECT * FROM c WHERE c.id = @id AND c.owner_user_id = @owner_user_id"
        items = list(
            self.container.query_items(
                query=query,
                parameters=[
                    {"name": "@id", "value": document_id},
                    {"name": "@owner_user_id", "value": owner_user_id},
                ],
                partition_key=owner_user_id,
            )
        )
        return items[0] if items else None

    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]:
        query = "SELECT * FROM c WHERE c.owner_user_id = @owner_user_id ORDER BY c.created_at DESC"
        return list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@owner_user_id", "value": owner_user_id}],
                partition_key=owner_user_id,
            )
        )

    def delete(self, owner_user_id: str, document_id: str) -> None:
        self.container.delete_item(item=document_id, partition_key=owner_user_id)

    def count_file_uploads_today(self, owner_user_id: str) -> int:
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        query = (
            "SELECT VALUE COUNT(1) FROM c WHERE c.owner_user_id = @owner_user_id "
            "AND c.source = 'file' AND c.created_at >= @day_start"
        )
        items = list(
            self.container.query_items(
                query=query,
                parameters=[
                    {"name": "@owner_user_id", "value": owner_user_id},
                    {"name": "@day_start", "value": day_start},
                ],
                partition_key=owner_user_id,
            )
        )
        return int(items[0]) if items else 0

    def list_expired(self, before: datetime | None = None) -> list[dict[str, Any]]:
        cutoff = (before or datetime.now(timezone.utc)).isoformat()
        query = "SELECT * FROM c WHERE IS_DEFINED(c.expires_at) AND c.expires_at < @cutoff"
        return list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@cutoff", "value": cutoff}],
                enable_cross_partition_query=True,
            )
        )
