from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DocumentMetadata:
    document_id: str
    filename: str
    source_type: str
    chunk_count: int = 0
    created_at: str = ""
    source: str = "file"
    owner_user_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkMetadata:
    document_id: str
    filename: str
    source_type: str
    chunk_index: int
    created_at: str
    source: str = "file"


@dataclass
class SearchResult:
    id: str
    text: str
    score: float
    metadata: dict[str, Any]


@dataclass
class ChatRequest:
    query: str
    top_k: int = 5
    document_ids: Optional[list[str]] = None


@dataclass
class DatabaseIngestRequest:
    connection_string: str
    tables: list[str]
    db_type: str = "postgresql"
