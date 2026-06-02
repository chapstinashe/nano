from app.models.schemas import SearchResult
from app.rag.pipeline import run_search_pipeline


class RetrievalService:
    def search(
        self,
        query: str,
        owner_user_id: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
    ) -> list[SearchResult]:
        return run_search_pipeline(query, owner_user_id=owner_user_id, top_k=top_k, document_ids=document_ids)
