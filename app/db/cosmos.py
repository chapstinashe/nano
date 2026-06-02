import logging
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

from app.core.config import Config

logger = logging.getLogger(__name__)

_client: CosmosClient | None = None
_database = None
_containers: dict[str, Any] = {}


def _is_enabled() -> bool:
    return bool(Config.COSMOS_ENDPOINT and Config.COSMOS_KEY)


def require_cosmos() -> None:
    if not _is_enabled():
        raise RuntimeError(
            "Cosmos DB is required. Set COSMOS_ENDPOINT and COSMOS_KEY in the environment."
        )


def get_client() -> CosmosClient:
    require_cosmos()
    global _client
    if _client is None:
        _client = CosmosClient(Config.COSMOS_ENDPOINT, credential=Config.COSMOS_KEY)
    return _client


def get_database():
    global _database
    if _database is None:
        _database = get_client().create_database_if_not_exists(id=Config.COSMOS_DATABASE)
    return _database


def is_vector_capability_error(exc: CosmosHttpResponseError) -> bool:
    text = str(exc).lower()
    return "capability has not been enabled" in text or "cosmosvectorsearch" in text


def clear_container_cache(name: str | None = None) -> None:
    if name is None:
        _containers.clear()
        return
    _containers.pop(name, None)


def _partition_key(partition_key: str) -> PartitionKey:
    return PartitionKey(path=f"/{partition_key}")


def _vector_embedding_policy(props: dict[str, Any]) -> dict[str, Any] | None:
    policy = props.get("vectorEmbeddingPolicy")
    if policy:
        return policy
    return props.get("vector_embedding_policy")


def _indexing_policy(props: dict[str, Any]) -> dict[str, Any]:
    return props.get("indexingPolicy") or props.get("indexing_policy") or {}


def _has_vector_embeddings(props: dict[str, Any]) -> bool:
    policy = _vector_embedding_policy(props)
    if not policy:
        return False
    embeddings = policy.get("vectorEmbeddings") or policy.get("vector_embeddings") or []
    return len(embeddings) > 0


def _indexing_has_vector_index(props: dict[str, Any], path: str = "/embedding") -> bool:
    indexes = _indexing_policy(props).get("vectorIndexes") or []
    return any(index.get("path") == path for index in indexes)


def _container_is_empty(container) -> bool:
    rows = list(
        container.query_items(
            query="SELECT TOP 1 c.id FROM c",
            enable_cross_partition_query=True,
            max_item_count=1,
        )
    )
    return len(rows) == 0


def _create_container(
    database,
    name: str,
    partition_key: str,
    *,
    indexing_policy: dict[str, Any] | None = None,
    vector_embedding_policy: dict[str, Any] | None = None,
    default_ttl: int | None = None,
):
    kwargs: dict[str, Any] = {
        "id": name,
        "partition_key": _partition_key(partition_key),
    }
    if indexing_policy is not None:
        kwargs["indexing_policy"] = indexing_policy
    if vector_embedding_policy is not None:
        kwargs["vector_embedding_policy"] = vector_embedding_policy
    if default_ttl is not None:
        kwargs["default_ttl"] = default_ttl

    try:
        container = database.create_container(**kwargs)
        logger.info("Created Cosmos container: %s", name)
        return container
    except CosmosHttpResponseError as exc:
        if exc.status_code != 409:
            raise
        logger.debug("Cosmos container already exists (create race): %s", name)
        return database.get_container_client(name)


def _replace_container(
    database,
    name: str,
    partition_key: str,
    *,
    indexing_policy: dict[str, Any] | None = None,
    vector_embedding_policy: dict[str, Any] | None = None,
    default_ttl: int | None = None,
) -> None:
    container = database.get_container_client(name)
    kwargs: dict[str, Any] = {"partition_key": _partition_key(partition_key)}
    if indexing_policy is not None:
        kwargs["indexing_policy"] = indexing_policy
    if vector_embedding_policy is not None:
        kwargs["vector_embedding_policy"] = vector_embedding_policy
    if default_ttl is not None:
        kwargs["default_ttl"] = default_ttl
    database.replace_container(container, **kwargs)
    logger.info("Updated Cosmos container: %s", name)


def _recreate_container(
    database,
    name: str,
    partition_key: str,
    *,
    indexing_policy: dict[str, Any] | None = None,
    vector_embedding_policy: dict[str, Any] | None = None,
    default_ttl: int | None = None,
):
    clear_container_cache(name)
    try:
        database.delete_container(name)
        logger.info("Deleted Cosmos container for recreate: %s", name)
    except CosmosResourceNotFoundError:
        pass
    container = _create_container(
        database,
        name,
        partition_key,
        indexing_policy=indexing_policy,
        vector_embedding_policy=vector_embedding_policy,
        default_ttl=default_ttl,
    )
    _containers[name] = container


def ensure_container(
    name: str,
    partition_key: str,
    *,
    indexing_policy: dict[str, Any] | None = None,
    vector_embedding_policy: dict[str, Any] | None = None,
    default_ttl: int | None = None,
):
    """
    Create the container when missing; otherwise update supported properties
    (indexing policy, TTL). Vector embedding paths are fixed at creation — if an
    existing container lacks them, it is recreated only when empty.
    """
    require_cosmos()
    database = get_database()
    container_client = database.get_container_client(name)

    try:
        props = container_client.read()
        exists = True
    except CosmosResourceNotFoundError:
        props = None
        exists = False

    if not exists:
        container = _create_container(
            database,
            name,
            partition_key,
            indexing_policy=indexing_policy,
            vector_embedding_policy=vector_embedding_policy,
            default_ttl=default_ttl,
        )
        _containers[name] = container
        return container

    needs_vector_setup = vector_embedding_policy is not None and not _has_vector_embeddings(props)
    needs_index_update = (
        indexing_policy is not None
        and not _indexing_has_vector_index(props)
        and _has_vector_embeddings(props)
    )
    needs_ttl_update = default_ttl is not None and props.get("defaultTtl") != default_ttl

    if needs_vector_setup:
        if _container_is_empty(container_client):
            logger.warning(
                "Container '%s' exists without vector search policy; recreating (empty).",
                name,
            )
            _recreate_container(
                database,
                name,
                partition_key,
                indexing_policy=indexing_policy,
                vector_embedding_policy=vector_embedding_policy,
                default_ttl=default_ttl,
            )
            return _containers[name]

        raise RuntimeError(
            f"Cosmos container '{name}' exists but is not configured for vector search. "
            f"Delete it manually in Azure Portal (database '{Config.COSMOS_DATABASE}') "
            "or empty it, then restart the app."
        )

    if needs_index_update or needs_ttl_update:
        replace_embedding = (
            _vector_embedding_policy(props) if _has_vector_embeddings(props) else None
        )
        try:
            _replace_container(
                database,
                name,
                partition_key,
                indexing_policy=indexing_policy if needs_index_update else None,
                vector_embedding_policy=replace_embedding,
                default_ttl=default_ttl if needs_ttl_update else None,
            )
        except CosmosHttpResponseError as exc:
            raise RuntimeError(
                f"Failed to update Cosmos container '{name}'. ({exc})"
            ) from exc

    _containers[name] = container_client
    return container_client


def get_container(name: str, partition_key: str, **kwargs):
    cached = _containers.get(name)
    if cached is not None:
        return cached
    return ensure_container(name, partition_key, **kwargs)


def ensure_all_containers() -> None:
    """Create or update all Cosmos containers used by the app."""
    require_cosmos()
    get_database()

    standard = [
        (Config.COSMOS_USERS_CONTAINER, "email"),
        (Config.COSMOS_TOKENS_CONTAINER, "user_id"),
        (Config.COSMOS_DOCUMENTS_CONTAINER, "owner_user_id"),
        (Config.COSMOS_CHATS_CONTAINER, "owner_user_id"),
        (Config.COSMOS_GUEST_SESSIONS_CONTAINER, "session_id"),
        (Config.COSMOS_PREFERENCES_CONTAINER, "owner_user_id"),
    ]
    for container_name, partition_key in standard:
        ensure_container(container_name, partition_key)
        logger.info("Cosmos container ready: %s", container_name)

    from app.repositories.vector_repository import ensure_vector_container

    ensure_vector_container()
