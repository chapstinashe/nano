import pytest

from app.core.db_security import reject_raw_connection_string, validate_db_type
from app.core.security import validate_upload_magic
from app.utils.payload_validators import validate_chat_payload, validate_preferences_payload
from app.utils.validators import validate_query


def test_validate_query_rejects_long_input(monkeypatch):
    monkeypatch.setattr("app.utils.validators.Config.MAX_QUERY_LENGTH", 10)
    with pytest.raises(ValueError):
        validate_query("x" * 11)


def test_validate_db_type_blocks_sqlite():
    with pytest.raises(ValueError):
        validate_db_type("sqlite")


def test_reject_raw_connection_string():
    with pytest.raises(ValueError):
        reject_raw_connection_string("postgresql://user:pass@host/db")


def test_validate_preferences_payload_rejects_invalid_theme():
    with pytest.raises(ValueError):
        validate_preferences_payload({"theme": "neon"})


def test_validate_chat_payload_rejects_oversized_messages(monkeypatch):
    monkeypatch.setattr("app.utils.payload_validators.Config.MAX_CHAT_MESSAGE_CHARS", 5)
    with pytest.raises(ValueError):
        validate_chat_payload({"messages": [{"role": "user", "content": "too long"}]})


def test_validate_upload_magic_rejects_bad_pdf(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"NOTPDF")
    with pytest.raises(ValueError):
        validate_upload_magic(str(path), "pdf")
