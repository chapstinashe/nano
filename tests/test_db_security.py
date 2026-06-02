import pytest

from app.core.db_security import assert_safe_connection_target, validate_db_host, validate_table_names


def test_validate_table_names_rejects_invalid():
    with pytest.raises(ValueError):
        validate_table_names(["users; drop table"])
    assert validate_table_names(["users", "orders"]) == ["users", "orders"]


def test_validate_db_host_blocks_localhost():
    with pytest.raises(ValueError):
        validate_db_host("localhost")


def test_assert_safe_connection_target_blocks_private_ip():
    with pytest.raises(ValueError):
        assert_safe_connection_target("10.0.0.5")
