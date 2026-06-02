import io

import pytest

from app.ingestion.file_ingestor import FileIngestor


def test_ingest_txt_file(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_PATH", str(tmp_path / "uploads"))
    monkeypatch.setenv("METADATA_PATH", str(tmp_path / "metadata"))
    monkeypatch.setenv("CHROMA_DB_PATH", str(tmp_path / "chroma"))

    from app.core.config import Config
    Config.UPLOAD_PATH = str(tmp_path / "uploads")
    Config.METADATA_PATH = str(tmp_path / "metadata")
    Config.CHROMA_DB_PATH = str(tmp_path / "chroma")

    from app.rag import vector_store
    vector_store._client = None

    content = b"This is a test document for RAG ingestion pipeline."
    file_storage = _make_file_storage("test.txt", content)

    ingestor = FileIngestor()
    metadata = ingestor.ingest(file_storage)

    assert metadata.document_id
    assert metadata.filename == "test.txt"
    assert metadata.source_type == "txt"
    assert metadata.chunk_count >= 1


def test_rejects_unsupported_file():
    ingestor = FileIngestor()
    file_storage = _make_file_storage("bad.exe", b"binary")
    with pytest.raises(ValueError, match="Unsupported"):
        ingestor.ingest(file_storage)


def _make_file_storage(filename: str, content: bytes):
    from werkzeug.datastructures import FileStorage

    return FileStorage(stream=io.BytesIO(content), filename=filename)
