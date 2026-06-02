from unittest.mock import MagicMock, patch

import pytest

from app.utils.document_access import validate_document_ids


def test_validate_document_ids_none():
    assert validate_document_ids("owner-1", None) is None
    assert validate_document_ids("owner-1", []) is None


@patch("app.utils.document_access.require_cosmos")
@patch("app.utils.document_access.document_repo")
def test_validate_document_ids_rejects_foreign(mock_repo, _mock_cosmos):
    mock_repo.get_by_id.side_effect = lambda owner, doc_id: {"id": doc_id} if doc_id == "owned" else None

    with pytest.raises(ValueError, match="not in your library"):
        validate_document_ids("owner-1", ["owned", "foreign"])

    result = validate_document_ids("owner-1", ["owned"])
    assert result == ["owned"]
