import uuid
from datetime import datetime, timezone

from werkzeug.datastructures import FileStorage

from app.ingestion.database_ingestor import DatabaseIngestor
from app.ingestion.file_ingestor import FileIngestor
from app.models.schemas import DocumentMetadata
from app.repositories.document_repository import DocumentRepository
from app.ingestion.file_processor import process_uploaded_file
from app.services.upload_quota_service import assert_can_upload_file, file_expires_at
from app.utils.guest_guard import assert_not_guest_persist
from app.rag.chunking import split_text
from app.rag.embeddings import embed_documents
from app.rag.vector_store import add_documents


class IngestionService:
    def __init__(self) -> None:
        self.file_ingestor = FileIngestor()
        self.db_ingestor = DatabaseIngestor()
        self.document_repo = DocumentRepository()

    def ingest_file(self, file: FileStorage, owner_user_id: str) -> DocumentMetadata:
        assert_not_guest_persist(owner_user_id, resource="uploads and embeddings")
        assert_can_upload_file(owner_user_id)
        expires_at = file_expires_at(owner_user_id)
        return self.file_ingestor.ingest(
            file,
            owner_user_id=owner_user_id,
            expires_at=expires_at,
        )

    def process_file_for_client(self, file: FileStorage) -> dict:
        """Parse and embed a file without writing to blob storage or Cosmos."""
        return process_uploaded_file(file)

    def ingest_database(
        self,
        connection_string: str,
        tables: list[str],
        owner_user_id: str,
        db_type: str = "postgresql",
    ) -> DocumentMetadata:
        rows = self.db_ingestor.read_tables(connection_string, tables, db_type)
        if not rows:
            raise ValueError("No data found in specified tables")

        document_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        filename = f"db_{db_type}_{tables[0]}"
        all_chunks: list[str] = []
        all_metadatas: list[dict] = []
        chunk_index = 0

        for row in rows:
            row_text = row["text"]
            chunks = split_text(row_text)
            table = row["metadata"].get("table", "unknown")
            for chunk in chunks:
                all_chunks.append(chunk)
                all_metadatas.append(
                    {
                        "document_id": document_id,
                        "filename": filename,
                        "source_type": "database",
                        "chunk_index": chunk_index,
                        "created_at": created_at,
                        "source": "database",
                        "table": table,
                        "db_type": db_type,
                        "owner_user_id": owner_user_id,
                    }
                )
                chunk_index += 1

        embeddings = embed_documents(all_chunks)
        ids = [f"{document_id}_{i}" for i in range(len(all_chunks))]
        add_documents(ids=ids, documents=all_chunks, embeddings=embeddings, metadatas=all_metadatas)

        metadata = DocumentMetadata(
            document_id=document_id,
            filename=filename,
            source_type="database",
            chunk_count=len(all_chunks),
            created_at=created_at,
            source="database",
            owner_user_id=owner_user_id,
            extra={"tables": tables, "db_type": db_type},
        )
        self.document_repo.upsert(
            {
                "id": metadata.document_id,
                "document_id": metadata.document_id,
                "owner_user_id": metadata.owner_user_id,
                "filename": metadata.filename,
                "source_type": metadata.source_type,
                "chunk_count": metadata.chunk_count,
                "created_at": metadata.created_at,
                "source": metadata.source,
                "extra": metadata.extra,
            }
        )
        return metadata
