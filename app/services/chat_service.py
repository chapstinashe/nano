from app.models.schemas import SearchResult
from app.rag.citations import format_citations
from app.rag.llm import sse_generator
from app.rag.pipeline import run_chat_completion, run_chat_pipeline


class ChatService:
    def get_response(
        self,
        query: str,
        owner_user_id: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
        context_results: list[SearchResult] | None = None,
    ) -> tuple[str, list[dict]]:
        answer, results = run_chat_completion(
            query,
            owner_user_id=owner_user_id,
            top_k=top_k,
            document_ids=document_ids,
            context_results=context_results,
        )
        return answer, format_citations(results, answer, query=query)

    def stream_response(
        self,
        query: str,
        owner_user_id: str,
        top_k: int = 5,
        document_ids: list[str] | None = None,
        context_results: list[SearchResult] | None = None,
    ):
        token_stream, results = run_chat_pipeline(
            query,
            owner_user_id=owner_user_id,
            top_k=top_k,
            document_ids=document_ids,
            context_results=context_results,
        )
        return sse_generator(
            token_stream,
            results=results,
            format_sources=lambda res, ans: format_citations(res, ans, query=query),
        )
