import os
import tempfile
import uuid
from datetime import datetime, timezone

from werkzeug.datastructures import FileStorage

from app.core.security import allowed_file, validate_upload_magic
from app.ingestion.parsers.csv_parser import parse_csv
from app.ingestion.parsers.docx_parser import parse_docx
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.parsers.txt_parser import parse_txt
from app.ingestion.parsers.xlsx_parser import parse_xlsx
from app.rag.chunking import normalize_text, split_text_with_spans
from app.rag.embeddings import embed_documents

PARSERS = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "txt": parse_txt,
    "csv": parse_csv,
    "xlsx": parse_xlsx,
}


def process_uploaded_file(file: FileStorage) -> dict:
    """Parse, chunk, and embed a file without persisting to blob storage or Cosmos."""
    if not file or not file.filename:
        raise ValueError("No file provided")

    filename = os.path.basename(file.filename)
    if not allowed_file(filename):
        raise ValueError(f"Unsupported file type: {filename}")

    source_type = filename.rsplit(".", 1)[1].lower()
    document_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    file.stream.seek(0)
    raw_bytes = file.read()

    suffix = os.path.splitext(filename)[1]
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw_bytes)
        validate_upload_magic(temp_path, source_type)
        text = PARSERS[source_type](temp_path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    if not text.strip():
        raise ValueError(f"No text extracted from {filename}")

    normalized = normalize_text(text)
    chunk_entries = split_text_with_spans(normalized)
    if not chunk_entries:
        raise ValueError(f"No chunks generated from {filename}")

    chunk_texts = [entry["text"] for entry in chunk_entries]
    embeddings = embed_documents(chunk_texts)

    chunks = []
    for index, entry in enumerate(chunk_entries):
        chunks.append(
            {
                "id": f"{document_id}_{index}",
                "text": entry["text"],
                "embedding": embeddings[index],
                "metadata": {
                    "document_id": document_id,
                    "filename": filename,
                    "source_type": source_type,
                    "chunk_index": index,
                    "chunk_start": entry["start"],
                    "chunk_end": entry["end"],
                    "created_at": created_at,
                    "source": "file",
                },
            }
        )

    return {
        "document_id": document_id,
        "filename": filename,
        "source_type": source_type,
        "chunk_count": len(chunks),
        "created_at": created_at,
        "source": "file",
        "text": normalized,
        "chunks": chunks,
    }
