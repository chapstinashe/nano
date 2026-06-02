import re

from app.core.config import Config

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def validate_query(query: str) -> str:
    query = (query or "").strip()
    if not query:
        raise ValueError("Query cannot be empty")
    if len(query) > Config.MAX_QUERY_LENGTH:
        raise ValueError(f"Query cannot exceed {Config.MAX_QUERY_LENGTH} characters")
    query = _CONTROL_CHARS.sub("", query)
    if not query:
        raise ValueError("Query cannot be empty")
    return query


def validate_top_k(top_k: int, max_k: int = 20) -> int:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if top_k > max_k:
        raise ValueError(f"top_k cannot exceed {max_k}")
    return top_k
