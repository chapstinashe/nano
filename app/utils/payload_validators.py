from app.core.config import Config
from app.core.security import validate_uuid


ALLOWED_THEMES = frozenset({"dark", "light"})


def validate_chat_payload(data: dict) -> dict:
    messages = data.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    if len(messages) > Config.MAX_CHAT_MESSAGES:
        raise ValueError(f"Chat cannot exceed {Config.MAX_CHAT_MESSAGES} messages")

    normalized_messages = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"Message at index {index} must be an object")
        role = str(message.get("role", "")).strip()
        content = str(message.get("content", ""))
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"Invalid role in message at index {index}")
        if len(content) > Config.MAX_CHAT_MESSAGE_CHARS:
            raise ValueError(
                f"Message at index {index} exceeds {Config.MAX_CHAT_MESSAGE_CHARS} characters"
            )
        normalized_messages.append({"role": role, "content": content})

    title = str(data.get("title", "New chat")).strip() or "New chat"
    if len(title) > 200:
        raise ValueError("Chat title cannot exceed 200 characters")

    return {
        "title": title,
        "messages": normalized_messages,
        "created_at": data.get("createdAt", data.get("created_at", "")),
    }


def validate_preferences_payload(data: dict) -> dict:
    theme = str(data.get("theme", "dark")).strip().lower() or "dark"
    if theme not in ALLOWED_THEMES:
        raise ValueError("theme must be 'dark' or 'light'")

    active_chat_id = str(data.get("active_chat_id", "")).strip()
    if active_chat_id:
        active_chat_id = validate_uuid(active_chat_id, field_name="active_chat_id")

    return {"theme": theme, "active_chat_id": active_chat_id}


def validate_context_chunks(chunks: list | None) -> list[dict]:
    if chunks is None:
        return []
    if not isinstance(chunks, list):
        raise ValueError("context_chunks must be a list")
    if not chunks:
        raise ValueError("context_chunks cannot be empty")
    if len(chunks) > Config.RETRIEVAL_MAX_CONTEXT_CHUNKS:
        raise ValueError(f"context_chunks cannot exceed {Config.RETRIEVAL_MAX_CONTEXT_CHUNKS} items")

    normalized = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"context_chunks[{index}] must be an object")
        text = str(chunk.get("text", "")).strip()
        if not text:
            raise ValueError(f"context_chunks[{index}] text is required")
        if len(text) > Config.MAX_CHAT_MESSAGE_CHARS:
            raise ValueError(f"context_chunks[{index}] text is too long")
        chunk_id = str(chunk.get("id", f"chunk_{index}")).strip() or f"chunk_{index}"
        score = float(chunk.get("score", 0.0))
        metadata = chunk.get("metadata", {})
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError(f"context_chunks[{index}] metadata must be an object")
        normalized.append(
            {
                "id": chunk_id,
                "text": text,
                "score": score,
                "metadata": metadata or {},
            }
        )
    return normalized
