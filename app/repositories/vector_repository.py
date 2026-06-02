"""
Cosmos DB vector store using Azure Vector Search for NoSQL (VectorDistance + vector index).
"""

import logging
import time
from typing import Any, Optional

from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from app.core.config import Config
from app.db import cosmos as cosmos_db
from app.db.cosmos import (
    _container_is_empty,
    _has_vector_embeddings,
    _recreate_container,
    clear_container_cache,
    ensure_container,
    get_database,
    is_vector_capability_error,
)
from app.utils.guest_guard import assert_not_guest_persist

logger = logging.getLogger(__name__)

_METADATA_KEYS = (
    "document_id",
    "filename",
    "source_type",
    "chunk_index",
    "chunk_start",
    "chunk_end",
    "created_at",
    "source",
    "owner_user_id",
    "table",
    "db_type",
)


def _vector_indexing_policy() -> dict[str, Any]:
    return {
        "indexingMode": "consistent",
        "automatic": True,
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [
            {"path": "/_etag/?"},
            {"path": "/embedding/*"},
        ],
        "vectorIndexes": [{"path": "/embedding", "type": "flat"}],
    }


def _vector_embedding_policy() -> dict[str, Any]:
    return {
        "vectorEmbeddings": [
            {
                "path": "/embedding",
                "dataType": "float32",
                "dimensions": Config.EMBEDDING_DIMENSIONS,
                "distanceFunction": "cosine",
            }
        ]
    }


def _cosmos_account_name() -> str:
    endpoint = (Config.COSMOS_ENDPOINT or "").rstrip("/")
    if not endpoint:
        return "<your-cosmos-account>"
    host = endpoint.split("//", 1)[-1].split(":")[0]
    return host.split(".", 1)[0]


def _vector_search_setup_error(exc: CosmosHttpResponseError | None = None) -> str:
    account = _cosmos_account_name()
    base = (
        f"Azure Cosmos DB Vector Search is required for container '{Config.COSMOS_VECTORS_CONTAINER}'.\n"
        f"Account: {account} | Database: {Config.COSMOS_DATABASE}\n\n"
        "Enable the feature:\n"
        f"  Portal: {account} → Settings → Features → Vector Search for NoSQL API → Enable\n"
        f"  CLI: az cosmosdb update --resource-group nano-rg --name {account} "
        "--capabilities EnableNoSQLVectorSearch\n\n"
        "Wait ~15 minutes after enabling, then restart the app.\n"
        "If you previously ran without vector search, delete container 'rag_chunks' in Data Explorer "
        "and restart so it can be recreated with a vector index.\n"
        "Docs: https://aka.ms/CosmosVectorSearch"
    )
    if exc:
        return f"{base}\n\nDetails: {exc}"
    return base


def _ensure_native_vector_container():
    """Create rag_chunks with vector embedding + flat vector index (Azure Vector Search)."""
    database = get_database()
    name = Config.COSMOS_VECTORS_CONTAINER
    client = database.get_container_client(name)

    try:
        props = client.read()
        if _has_vector_embeddings(props):
            cosmos_db._containers[name] = client
            return client
        # Container exists but was created without vector policies — recreate when empty.
        if _container_is_empty(client):
            logger.warning(
                "Container '%s' lacks vector policy; recreating with Azure Vector Search.",
                name,
            )
            clear_container_cache(name)
            _recreate_container(
                database,
                name,
                "owner_user_id",
                indexing_policy=_vector_indexing_policy(),
                vector_embedding_policy=_vector_embedding_policy(),
            )
            return cosmos_db._containers[name]

        raise RuntimeError(
            f"Container '{name}' exists without Azure Vector Search configuration. "
            f"Delete it in Azure Portal (database '{Config.COSMOS_DATABASE}') and restart the app."
        )
    except CosmosResourceNotFoundError:
        pass

    return ensure_container(
        name,
        "owner_user_id",
        indexing_policy=_vector_indexing_policy(),
        vector_embedding_policy=_vector_embedding_policy(),
    )


def ensure_vector_container():
    """Initialize Cosmos vector container with Azure native VectorDistance search."""
    if not cosmos_db._is_enabled():
        raise RuntimeError("Cosmos DB is not configured. Set COSMOS_ENDPOINT and COSMOS_KEY.")

    retries = max(0, Config.COSMOS_VECTOR_INIT_RETRIES)
    delay = max(1, Config.COSMOS_VECTOR_INIT_RETRY_SEC)
    last_error: CosmosHttpResponseError | None = None

    for attempt in range(retries + 1):
        try:
            container = _ensure_native_vector_container()
            logger.info(
                "Azure Vector Search ready: %s (VectorDistance, %d-dim cosine, flat index)",
                Config.COSMOS_VECTORS_CONTAINER,
                Config.EMBEDDING_DIMENSIONS,
            )
            return container
        except CosmosHttpResponseError as exc:
            if is_vector_capability_error(exc):
                last_error = exc
                if attempt < retries:
                    logger.info(
                        "Azure Vector Search not active yet (%d/%d); retry in %ds...",
                        attempt + 1,
                        retries + 1,
                        delay,
                    )
                    time.sleep(delay)
                    clear_container_cache(Config.COSMOS_VECTORS_CONTAINER)
                    continue
                raise RuntimeError(_vector_search_setup_error(last_error)) from exc
            raise RuntimeError(_vector_search_setup_error(exc)) from exc
        except RuntimeError:
            raise

    raise RuntimeError(_vector_search_setup_error(last_error))


def get_vector_container():
    cached = cosmos_db._containers.get(Config.COSMOS_VECTORS_CONTAINER)
    if cached is not None:
        return cached
    return ensure_vector_container()


def _coerce_metadata_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _build_chunk_item(
    chunk_id: str,
    text: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    owner_user_id = metadata.get("owner_user_id", "")
    if not owner_user_id:
        raise ValueError("owner_user_id is required for vector chunks")

    item: dict[str, Any] = {
        "id": chunk_id,
        "owner_user_id": owner_user_id,
        "text": text,
        "embedding": [float(v) for v in embedding],
    }
    for key in _METADATA_KEYS:
        if key in metadata and metadata[key] is not None:
            item[key] = _coerce_metadata_value(metadata[key])
    return item


def _parse_where_filter(where: Optional[dict[str, Any]]) -> tuple[str, list[str]]:
    if not where:
        return "", []

    owner_user_id = ""
    document_ids: list[str] = []

    if "$and" in where:
        clauses = where["$and"]
    else:
        clauses = [where]

    for clause in clauses:
        if "owner_user_id" in clause:
            owner_user_id = str(clause["owner_user_id"])
        if "document_id" in clause:
            doc = clause["document_id"]
            if isinstance(doc, dict) and "$in" in doc:
                document_ids.extend(str(d) for d in doc["$in"])
            else:
                document_ids.append(str(doc))

    return owner_user_id, document_ids


def _document_filter_sql(document_ids: list[str], parameters: list[dict[str, Any]]) -> str:
    if not document_ids:
        return ""
    if len(document_ids) == 1:
        parameters.append({"name": "@document_id", "value": document_ids[0]})
        return " AND c.document_id = @document_id"
    clauses = []
    for idx, doc_id in enumerate(document_ids):
        param_name = f"@document_id_{idx}"
        parameters.append({"name": param_name, "value": doc_id})
        clauses.append(f"c.document_id = {param_name}")
    return " AND (" + " OR ".join(clauses) + ")"


def _row_to_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in _METADATA_KEYS if row.get(key) is not None}


class VectorRepository:
    """Azure Cosmos DB vector store — native VectorDistance queries only."""

    @property
    def enabled(self) -> bool:
        return cosmos_db._is_enabled()

    @property
    def container(self):
        return get_vector_container()

    def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        for metadata in metadatas:
            assert_not_guest_persist(metadata.get("owner_user_id", ""), resource="embeddings")
        for chunk_id, text, embedding, metadata in zip(ids, documents, embeddings, metadatas):
            item = _build_chunk_item(chunk_id, text, embedding, metadata)
            self.container.upsert_item(body=item)
        logger.info("Upserted %d chunks to Azure Vector Search (%s)", len(ids), Config.COSMOS_VECTORS_CONTAINER)

    def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        owner_user_id, document_ids = _parse_where_filter(where)
        if not owner_user_id:
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

        top_k = max(1, min(int(top_k), 100))
        parameters: list[dict[str, Any]] = [
            {"name": "@embedding", "value": [float(v) for v in query_embedding]},
            {"name": "@owner_user_id", "value": owner_user_id},
        ]
        doc_filter = _document_filter_sql(document_ids, parameters)

        query = f"""
            SELECT TOP {top_k}
                c.id,
                c.text,
                c.document_id,
                c.filename,
                c.source_type,
                c.chunk_index,
                c.chunk_start,
                c.chunk_end,
                c.created_at,
                c.source,
                c.owner_user_id,
                c.table,
                c.db_type,
                VectorDistance(c.embedding, @embedding) AS distance
            FROM c
            WHERE c.owner_user_id = @owner_user_id{doc_filter}
            ORDER BY VectorDistance(c.embedding, @embedding)
        """

        rows = list(
            self.container.query_items(
                query=query,
                parameters=parameters,
                partition_key=owner_user_id,
            )
        )

        ids: list[str] = []
        texts: list[str] = []
        distances: list[float] = []
        metadatas: list[dict[str, Any]] = []

        for row in rows:
            ids.append(row.get("id", ""))
            texts.append(row.get("text", ""))
            distances.append(float(row.get("distance", 1.0)))
            metadatas.append(_row_to_metadata(row))

        return {
            "ids": [ids],
            "documents": [texts],
            "distances": [distances],
            "metadatas": [metadatas],
        }

    def delete_documents(self, document_id: str, owner_user_id: str | None = None) -> int:
        if not owner_user_id:
            return 0

        parameters = [
            {"name": "@document_id", "value": document_id},
            {"name": "@owner_user_id", "value": owner_user_id},
        ]
        query = (
            "SELECT c.id FROM c WHERE c.owner_user_id = @owner_user_id "
            "AND c.document_id = @document_id"
        )
        rows = list(
            self.container.query_items(
                query=query,
                parameters=parameters,
                partition_key=owner_user_id,
            )
        )
        for row in rows:
            self.container.delete_item(item=row["id"], partition_key=owner_user_id)
        if rows:
            logger.info("Deleted %d chunks for document %s", len(rows), document_id)
        return len(rows)

    def delete_all_for_owner(self, owner_user_id: str) -> int:
        query = "SELECT c.id FROM c WHERE c.owner_user_id = @owner_user_id"
        rows = list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@owner_user_id", "value": owner_user_id}],
                partition_key=owner_user_id,
            )
        )
        for row in rows:
            self.container.delete_item(item=row["id"], partition_key=owner_user_id)
        if rows:
            logger.info("Deleted %d chunks for owner %s", len(rows), owner_user_id)
        return len(rows)

    def list_document_ids(self, owner_user_id: str | None = None) -> list[str]:
        if not owner_user_id:
            return []

        query = "SELECT DISTINCT VALUE c.document_id FROM c WHERE c.owner_user_id = @owner_user_id"
        values = list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@owner_user_id", "value": owner_user_id}],
                partition_key=owner_user_id,
            )
        )
        return sorted({str(value) for value in values if value})

    def count_chunks(
        self,
        document_id: Optional[str] = None,
        owner_user_id: str | None = None,
    ) -> int:
        if not owner_user_id:
            return 0

        parameters: list[dict[str, Any]] = [
            {"name": "@owner_user_id", "value": owner_user_id},
        ]
        doc_filter = ""
        if document_id:
            parameters.append({"name": "@document_id", "value": document_id})
            doc_filter = " AND c.document_id = @document_id"

        query = f"SELECT VALUE COUNT(1) FROM c WHERE c.owner_user_id = @owner_user_id{doc_filter}"
        rows = list(
            self.container.query_items(
                query=query,
                parameters=parameters,
                partition_key=owner_user_id,
            )
        )
        return int(rows[0]) if rows else 0
