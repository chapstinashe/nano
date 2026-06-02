import os
import uuid
from datetime import datetime, timezone

from werkzeug.datastructures import FileStorage

from app.core.security import allowed_file, validate_upload_magic
from app.utils.guest_guard import assert_not_guest_persist
from app.ingestion.parsers.csv_parser import parse_csv
from app.ingestion.parsers.docx_parser import parse_docx
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.parsers.txt_parser import parse_txt
from app.ingestion.parsers.xlsx_parser import parse_xlsx
from app.models.schemas import DocumentMetadata
from app.repositories.document_repository import DocumentRepository
from app.rag.chunking import normalize_text, split_text_with_spans
from app.rag.embeddings import embed_documents
from app.rag.vector_store import add_documents
from app.utils.text_storage import save_extracted_text
from app.utils.upload_storage import cleanup_parse_path, save_user_upload


PARSERS = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "txt": parse_txt,
    "csv": parse_csv,
    "xlsx": parse_xlsx,
}


class FileIngestor:
    def __init__(self) -> None:
        self.document_repo = DocumentRepository()

    def ingest(
        self,
        file: FileStorage,
        owner_user_id: str,
        expires_at: str | None = None,
    ) -> DocumentMetadata:
        assert_not_guest_persist(owner_user_id, resource="uploads and embeddings")
        if not file or not file.filename:
            raise ValueError("No file provided")

        filename = os.path.basename(file.filename)
        if not allowed_file(filename):
            raise ValueError(f"Unsupported file type: {filename}")

        source_type = filename.rsplit(".", 1)[1].lower()
        document_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        upload_info = save_user_upload(
            file,
            document_id,
            filename,
            owner_user_id=owner_user_id,
        )
        try:
            validate_upload_magic(upload_info["parse_path"], source_type)
            parser = PARSERS[source_type]
            text = parser(upload_info["parse_path"])
        finally:
            cleanup_parse_path(upload_info)

        if not text.strip():
            raise ValueError(f"No text extracted from {filename}")

        normalized = normalize_text(text)
        text_blob_path = save_extracted_text(owner_user_id, document_id, text)

        chunk_entries = split_text_with_spans(normalized)
        if not chunk_entries:
            raise ValueError(f"No chunks generated from {filename}")

        chunks = [entry["text"] for entry in chunk_entries]
        embeddings = embed_documents(chunks)
        ids = [f"{document_id}_{i}" for i in range(len(chunks))]
        metadatas = []
        for i, entry in enumerate(chunk_entries):
            metadatas.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "source_type": source_type,
                    "chunk_index": i,
                    "chunk_start": entry["start"],
                    "chunk_end": entry["end"],
                    "created_at": created_at,
                    "source": "file",
                    "owner_user_id": owner_user_id,
                }
            )

        add_documents(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)

        metadata = DocumentMetadata(
            document_id=document_id,
            filename=filename,
            source_type=source_type,
            chunk_count=len(chunks),
            created_at=created_at,
            source="file",
            owner_user_id=owner_user_id,
            extra={
                "storage_backend": upload_info["storage_backend"],
                "blob_path": upload_info.get("blob_path", ""),
                "text_blob_path": text_blob_path,
            },
        )
        self._save_metadata(metadata, expires_at=expires_at, text_blob_path=text_blob_path)
        return metadata

    def _save_metadata(
        self,
        metadata: DocumentMetadata,
        expires_at: str | None = None,
        text_blob_path: str = "",
    ) -> None:
        doc = {
            "id": metadata.document_id,
            "document_id": metadata.document_id,
            "owner_user_id": metadata.owner_user_id,
            "filename": metadata.filename,
            "source_type": metadata.source_type,
            "chunk_count": metadata.chunk_count,
            "created_at": metadata.created_at,
            "source": metadata.source,
            "storage_backend": metadata.extra.get("storage_backend", "blob"),
            "blob_path": metadata.extra.get("blob_path", ""),
            "text_blob_path": text_blob_path or metadata.extra.get("text_blob_path", ""),
        }
        if expires_at:
            doc["expires_at"] = expires_at
        self.document_repo.upsert(doc)
