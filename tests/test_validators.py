import pytest

from app.utils.validators import validate_query, validate_top_k


def test_validate_query_strips_whitespace():
    assert validate_query("  hello  ") == "hello"


def test_validate_query_rejects_empty():
    with pytest.raises(ValueError):
        validate_query("   ")


def test_validate_top_k_bounds():
    assert validate_top_k(5) == 5
    with pytest.raises(ValueError):
        validate_top_k(0)
    with pytest.raises(ValueError):
        validate_top_k(100)
