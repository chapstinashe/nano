import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

from app.core.secrets import apply_key_vault_secrets

apply_key_vault_secrets()

BASE_DIR = Path(__file__).resolve().parent.parent


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Config:
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    UPLOAD_PATH = os.path.abspath(os.getenv("UPLOAD_PATH", str(BASE_DIR / "storage" / "uploads")))
    METADATA_PATH = os.path.abspath(os.getenv("METADATA_PATH", str(BASE_DIR / "storage" / "metadata")))
    TEXT_PATH = os.path.abspath(os.getenv("TEXT_PATH", str(BASE_DIR / "storage" / "texts")))

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_DIMENSIONS = _get_int("EMBEDDING_DIMENSIONS", 384)

    CHUNK_SIZE = _get_int("CHUNK_SIZE", 500)
    CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 100)

    DEFAULT_TOP_K = _get_int("DEFAULT_TOP_K", 8)

    # Retrieval tuning
    RETRIEVAL_CANDIDATE_K = _get_int("RETRIEVAL_CANDIDATE_K", 24)
    RETRIEVAL_MAX_CONTEXT_CHUNKS = _get_int("RETRIEVAL_MAX_CONTEXT_CHUNKS", 8)
    RETRIEVAL_MIN_RESULTS = _get_int("RETRIEVAL_MIN_RESULTS", 2)
    RETRIEVAL_MULTI_QUERY = os.getenv("RETRIEVAL_MULTI_QUERY", "1") == "1"
    RETRIEVAL_MIN_SCORE = _get_float("RETRIEVAL_MIN_SCORE", 0.32)
    RETRIEVAL_SCORE_GAP = _get_float("RETRIEVAL_SCORE_GAP", 0.12)
    RETRIEVAL_MMR_LAMBDA = _get_float("RETRIEVAL_MMR_LAMBDA", 0.72)
    RETRIEVAL_DEDUPE_THRESHOLD = _get_float("RETRIEVAL_DEDUPE_THRESHOLD", 0.88)
    RETRIEVAL_VECTOR_WEIGHT = _get_float("RETRIEVAL_VECTOR_WEIGHT", 0.55)
    RETRIEVAL_LEXICAL_WEIGHT = _get_float("RETRIEVAL_LEXICAL_WEIGHT", 0.25)
    RETRIEVAL_PHRASE_WEIGHT = _get_float("RETRIEVAL_PHRASE_WEIGHT", 0.12)
    RETRIEVAL_FUZZY_WEIGHT = _get_float("RETRIEVAL_FUZZY_WEIGHT", 0.08)
    RETRIEVAL_ANSWER_PATTERN_WEIGHT = _get_float("RETRIEVAL_ANSWER_PATTERN_WEIGHT", 0.22)

    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = _get_int("FLASK_PORT", 5000)
    MAX_UPLOAD_BYTES = _get_int("MAX_UPLOAD_BYTES", 25 * 1024 * 1024)

    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "1") == "1"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
    JWT_ACCESS_EXPIRES_MIN = _get_int("JWT_ACCESS_EXPIRES_MIN", 30)
    JWT_REFRESH_EXPIRES_DAYS = _get_int("JWT_REFRESH_EXPIRES_DAYS", 7)
    JWT_ACCESS_COOKIE_NAME = os.getenv("JWT_ACCESS_COOKIE_NAME", "nano_access_token")
    JWT_REFRESH_COOKIE_NAME = os.getenv("JWT_REFRESH_COOKIE_NAME", "nano_refresh_token")
    COOKIE_SECURE = _get_bool("COOKIE_SECURE", not FLASK_DEBUG)
    COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "Lax")

    _allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "")
    ALLOWED_ORIGINS = [origin.strip() for origin in _allowed_origins_raw.split(",") if origin.strip()]

    RATE_LIMIT_ENABLED = _get_bool("RATE_LIMIT_ENABLED", True)
    RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "5 per minute")
    RATE_LIMIT_REGISTER = os.getenv("RATE_LIMIT_REGISTER", "3 per hour")
    RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "30 per minute")
    RATE_LIMIT_SEARCH = os.getenv("RATE_LIMIT_SEARCH", "60 per minute")
    RATE_LIMIT_INGEST_FILE = os.getenv("RATE_LIMIT_INGEST_FILE", "10 per hour")
    RATE_LIMIT_INGEST_DB = os.getenv("RATE_LIMIT_INGEST_DB", "5 per hour")
    RATE_LIMIT_REFRESH = os.getenv("RATE_LIMIT_REFRESH", "10 per minute")
    RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "")

    JWT_CSRF_ACCESS_COOKIE_NAME = os.getenv("JWT_CSRF_ACCESS_COOKIE_NAME", "csrf_access_token")
    JWT_CSRF_REFRESH_COOKIE_NAME = os.getenv("JWT_CSRF_REFRESH_COOKIE_NAME", "csrf_refresh_token")

    MAX_QUERY_LENGTH = _get_int("MAX_QUERY_LENGTH", 4000)
    MAX_CHAT_MESSAGES = _get_int("MAX_CHAT_MESSAGES", 200)
    MAX_CHAT_MESSAGE_CHARS = _get_int("MAX_CHAT_MESSAGE_CHARS", 10000)
    MAX_TEXT_EXPORT_CHARS = _get_int("MAX_TEXT_EXPORT_CHARS", 500000)

    AZURE_KEY_VAULT_URL = os.getenv("AZURE_KEY_VAULT_URL", "")

    COSMOS_ENDPOINT = os.getenv("COSMOS_ENDPOINT", "")
    COSMOS_KEY = os.getenv("COSMOS_KEY", "")
    COSMOS_DATABASE = os.getenv("COSMOS_DATABASE", "rag_system")
    COSMOS_USERS_CONTAINER = os.getenv("COSMOS_USERS_CONTAINER", "users")
    COSMOS_TOKENS_CONTAINER = os.getenv("COSMOS_TOKENS_CONTAINER", "refresh_tokens")
    COSMOS_DOCUMENTS_CONTAINER = os.getenv("COSMOS_DOCUMENTS_CONTAINER", "documents")
    COSMOS_VECTORS_CONTAINER = os.getenv("COSMOS_VECTORS_CONTAINER", "rag_chunks")
    COSMOS_CHATS_CONTAINER = os.getenv("COSMOS_CHATS_CONTAINER", "chats")
    COSMOS_PREFERENCES_CONTAINER = os.getenv("COSMOS_PREFERENCES_CONTAINER", "user_preferences")

    AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "nano-uploads")
    ANON_SESSION_TTL_HOURS = _get_int("ANON_SESSION_TTL_HOURS", 12)
    COSMOS_GUEST_SESSIONS_CONTAINER = os.getenv("COSMOS_GUEST_SESSIONS_CONTAINER", "guest_sessions")

    # Azure Vector Search container init retries (while account capability propagates)
    COSMOS_VECTOR_INIT_RETRIES = _get_int("COSMOS_VECTOR_INIT_RETRIES", 12)
    COSMOS_VECTOR_INIT_RETRY_SEC = _get_int("COSMOS_VECTOR_INIT_RETRY_SEC", 10)

    # Unauthenticated (guest) upload limits — not applied to logged-in users
    GUEST_DAILY_UPLOAD_LIMIT = _get_int(
        "GUEST_DAILY_UPLOAD_LIMIT",
        _get_int("AUTH_USER_DAILY_UPLOAD_LIMIT", 1),
    )
    GUEST_DOCUMENT_TTL_HOURS = _get_int(
        "GUEST_DOCUMENT_TTL_HOURS",
        _get_int("AUTH_USER_DOCUMENT_TTL_HOURS", 6),
    )

    @classmethod
    def ensure_storage_dirs(cls) -> None:
        """No persistent local user-data directories; uploads/text live in Azure Blob."""
        return
